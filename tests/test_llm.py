"""LLMClient (SRS 4.22): MOCK behaviour, offline switch, and the real Ollama client
tested against a small fake Ollama server on localhost (Ollama is not installed)."""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

from bookorbit.ai import mock_llm
from bookorbit.ai.llm import MockLLM, OfflineLLM, OllamaLLM, get_llm
from bookorbit.config import DEFAULTS
from bookorbit.errors import LLMUnavailable, ModelUnavailable

CHAPTER = ("The dragon Pellinore collected maps in a cave beneath the mountains. "
           "Tamsin Reed was an apprentice cartographer who wanted the map of the Unwritten Coast. "
           "The map had been stolen forty years ago by a thief who left a feather drawing. "
           "Ilsa Quill had copied the map many times and given the copies to sailors. "
           "Each sailor added new bays, reefs and villages to the growing map.")


class MockLLMTests(unittest.TestCase):
    def setUp(self):
        self.llm = MockLLM()

    def test_mock_is_available_and_labelled(self):
        self.assertTrue(self.llm.is_available())
        self.assertTrue(self.llm.is_mock)
        self.assertIn("MOCK", self.llm.mode_label)

    def test_embed_is_unit_length_and_deterministic(self):
        a, b = self.llm.embed("Glass moons that sing"), self.llm.embed("Glass moons that sing")
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0)
        np.testing.assert_array_equal(a, b)
        self.assertAlmostEqual(float(np.linalg.norm(self.llm.embed("the and of"))), 1.0)  # no content words

    def test_embed_similar_texts_score_higher(self):
        q = self.llm.embed("who stole the dragon's map")
        related = self.llm.embed(CHAPTER)
        unrelated = self.llm.embed("Steel cables and stone towers carried the Brooklyn Bridge deck.")
        self.assertGreater(float(q @ related), float(q @ unrelated))

    def test_answer_quotes_the_best_fact(self):
        out = self.llm.generate("prompt", task="answer", question="Who copied the map for sailors?",
                                context=[CHAPTER])
        self.assertIn("Ilsa Quill", out)

    def test_answer_without_facts_says_mock(self):
        self.assertIn("MOCK", self.llm.generate("p", task="answer", question="What is the capital of France?"))

    def test_summary_has_bullets_from_the_text(self):
        out = self.llm.generate("p", task="summarize", context=[CHAPTER])
        self.assertTrue(out.startswith("• "))
        self.assertTrue(all(line[2:] in CHAPTER for line in out.splitlines()))

    def test_define_finds_the_word_in_context(self):
        self.assertIn("cartographer", self.llm.generate("p", task="define", question="cartographer", context=[CHAPTER]))
        self.assertIn("does not appear", self.llm.generate("p", task="define", question="zebra", context=[CHAPTER]))

    def test_quiz_is_valid_srs_json(self):
        qs = json.loads(self.llm.generate("p", task="quiz", context=[CHAPTER]))
        self.assertEqual(len(qs), 3)
        for q in qs:
            self.assertEqual(len(q["options"]), 4)
            self.assertTrue(0 <= q["answer_index"] < 4)
            self.assertIn("_____", q["q"])
            answer = q["options"][q["answer_index"]]
            self.assertIn(q["q"].replace("Fill in the blank: ", "").replace("_____", answer), CHAPTER)

    def test_classify_uses_store_context(self):
        self.assertEqual(self.llm.generate("p", 3, task="classify", question="tell me a joke"), "GENERAL")
        self.assertEqual(self.llm.generate("p", 3, task="classify", question="dragon books?",
                                           context=["The Dragon Who Collected Maps by ..."]), "STORE")

    def test_short_facts_can_be_the_answer(self):
        out = self.llm.generate("p", task="answer", question="What is my balance?",
                                context=["Role: RC", "Balance: $50.00", "Warnings: 0"])
        self.assertEqual(out, "Balance: $50.00")

    def test_chunk_border_fragment_is_not_quoted_twice(self):
        # two overlapping chunks: the first ends mid-sentence, the second has it whole
        a = "The clocks were slow. If the museum clocks were twelve minutes slow, Brandt could"
        b = "If the museum clocks were twelve minutes slow, Brandt could not have stopped the tower clock."
        self.assertEqual(mock_llm.unique_sentences([a, b]), ["The clocks were slow.", b])
        out = self.llm.generate("p", task="answer", question="Why were the museum clocks slow?", context=[a, b])
        self.assertEqual(out.count("If the museum clocks"), 1)

    def test_poem_lines_are_sentences(self):
        stanza = "The puddle in the schoolyard\nkeeps a copy of the sky.\nClouds pass through it carefully,\na bird goes upside down,"
        self.assertEqual(len(mock_llm.sentences(stanza)), 4)


class OfflineTests(unittest.TestCase):
    def test_offline_behaves_like_stopped_ollama(self):
        llm = get_llm(dict(DEFAULTS, LLM_MODE="offline"))
        self.assertIsInstance(llm, OfflineLLM)
        self.assertFalse(llm.is_available())
        with self.assertRaises(LLMUnavailable):
            llm.generate("hi")
        with self.assertRaises(ModelUnavailable):
            llm.embed("hi")


# ---------------------------------------------------------------- fake Ollama server
class FakeOllama(BaseHTTPRequestHandler):
    models = ["llama3.2:3b", "nomic-embed-text:latest"]
    delay = 0.0
    requests: list = []

    def log_message(self, *_args):            # keep test output quiet
        pass

    def _send(self, body: dict, status=200):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": m} for m in type(self).models]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((self.path, body))
        time.sleep(type(self).delay)
        if self.path == "/api/generate":
            self._send({"response": "  Hello from the fake model.  "})
        elif self.path == "/api/embeddings":
            self._send({"embedding": [3.0, 4.0]})
        else:
            self._send({"error": "not found"}, 404)


class OllamaClientTests(unittest.TestCase):
    def setUp(self):
        FakeOllama.models = ["llama3.2:3b", "nomic-embed-text:latest"]
        FakeOllama.delay = 0.0
        FakeOllama.requests = []
        self.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.llm = OllamaLLM(self.url, "llama3.2:3b", "nomic-embed-text")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_available_when_both_models_pulled(self):
        self.assertTrue(self.llm.is_available())          # ":latest" tag matches the bare name
        FakeOllama.models = ["llama3.2:3b"]
        self.assertFalse(self.llm.is_available())         # embedding model not pulled

    def test_generate_sends_srs_payload(self):
        self.assertEqual(self.llm.generate("Say hi", max_tokens=7), "Hello from the fake model.")
        path, body = FakeOllama.requests[-1]
        self.assertEqual(path, "/api/generate")
        self.assertEqual((body["model"], body["stream"], body["options"]["num_predict"]), ("llama3.2:3b", False, 7))
        self.assertEqual(body["options"]["temperature"], 0.3)

    def test_embed_is_normalised(self):
        np.testing.assert_allclose(self.llm.embed("x"), [0.6, 0.8])
        self.assertEqual(FakeOllama.requests[-1][1]["model"], "nomic-embed-text")

    def test_timeout_raises_offline(self):                # UC-12 E3: no reply in time
        FakeOllama.delay = 1.0
        with self.assertRaises(LLMUnavailable):
            self.llm.generate("slow", timeout=0.2)

    def test_get_llm_real_uses_ollama_when_ready(self):
        llm = get_llm(dict(DEFAULTS, LLM_MODE="real", OLLAMA_URL=self.url))
        self.assertIsInstance(llm, OllamaLLM)
        self.assertNotIn("MOCK", llm.mode_label)


class NoOllamaTests(unittest.TestCase):
    URL = "http://127.0.0.1:9"                            # nothing listens on port 9

    def test_unreachable_server(self):
        llm = OllamaLLM(self.URL, "llama3.2:3b", "nomic-embed-text")
        self.assertFalse(llm.is_available())
        with self.assertRaises(LLMUnavailable):
            llm.generate("hi", timeout=1)
        with self.assertRaises(ModelUnavailable):
            llm.embed("hi")

    def test_real_mode_falls_back_to_labelled_mock(self):  # CLAUDE.md: missing service -> MOCK
        llm = get_llm(dict(DEFAULTS, LLM_MODE="real", OLLAMA_URL=self.URL))
        self.assertIsInstance(llm, MockLLM)
        self.assertIn("MOCK", llm.mode_label)
        self.assertIn("Ollama", llm.mode_label)


if __name__ == "__main__":
    unittest.main()
