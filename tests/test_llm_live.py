"""Live tests against a REAL local Ollama (SRS 4.22). They are skipped automatically
unless Ollama is running at OLLAMA_URL with both models (OLLAMA_MODEL, OLLAMA_EMBED_MODEL)
pulled. See docs/PROGRESS.md "Switching to real Ollama".

    .venv/bin/python -m unittest tests.test_llm_live -v
"""
import shutil
import tempfile
import unittest

import numpy as np

from bookorbit.ai.llm import OllamaLLM
from bookorbit.config import load_config

CFG = load_config()
LIVE = OllamaLLM(CFG["OLLAMA_URL"], CFG["OLLAMA_MODEL"], CFG["OLLAMA_EMBED_MODEL"])
READY = LIVE.is_available()
WHY = (f"Ollama not running at {CFG['OLLAMA_URL']} or models "
       f"{CFG['OLLAMA_MODEL']} / {CFG['OLLAMA_EMBED_MODEL']} not pulled")


@unittest.skipUnless(READY, WHY)
class LiveOllamaTests(unittest.TestCase):
    def test_generate_answers(self):
        out = LIVE.generate("Reply with the single word: hello", max_tokens=10)
        self.assertTrue(out.strip())

    def test_embeddings_are_unit_vectors_and_semantic(self):
        car, auto, soup = (LIVE.embed(t) for t in ("I drive my car to work.",
                                                    "An automobile is my way to commute.",
                                                    "Tomato soup needs basil and salt."))
        self.assertGreater(len(car), 100)
        self.assertAlmostEqual(float(np.linalg.norm(car)), 1.0, places=5)
        self.assertGreater(float(car @ auto), float(car @ soup))     # meaning, not shared words

    def test_chatbot_store_answer_end_to_end(self):
        """UC-12 with the real models: a policy chunk is retrieved above MIN_SIM_REAL and
        llama answers from it."""
        from bookorbit.app_context import build_context
        from bookorbit.services.session import Session
        tmp = tempfile.mkdtemp(prefix="bookorbit_live_")
        try:
            ctx = build_context(dict(CFG, DATA_DIR=tmp, LLM_MODE="real"))
            self.assertIsInstance(ctx.llm, OllamaLLM)
            (ctx.fs.dir / "policies.txt").write_text(
                "VIP Customers pay 90 percent of the list price, a 10 percent discount.", encoding="utf-8")
            ctx.rag.build_index()
            r = ctx.chatbot.ask(Session(ctx.fs), "How much discount do VIP customers get?")
            self.assertEqual(r.source, "RAG", "no policy chunk above MIN_SIM_REAL - see ASSUMPTIONS A-29")
            self.assertIn("10", r.text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
