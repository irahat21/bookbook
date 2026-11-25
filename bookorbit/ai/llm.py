"""LLMClient - the only door to a language model (SRS 4.22).

Three implementations with one interface (is_available / generate / embed), picked by
LLM_MODE in .env:

* OllamaLLM   (real)    - local Ollama HTTP API, Python standard library only (urllib).
* MockLLM     (mock)    - MOCK, see bookorbit/ai/mock_llm.py. Always "available".
* OfflineLLM  (offline) - demo switch: behaves like Ollama that is not running, so the
                          offline paths (UC-12 E3, UC-13 E2, UC-14 E4) can be shown.

LLM_MODE=real with Ollama unreachable (or the models not pulled) falls back to the MOCK
and says so in its label (CLAUDE.md: "if a model or service is missing, use the mock and
label it MOCK"). If Ollama stops later, generate() raises LLMUnavailable and the screens
show the offline message.

The services build the same prompts in every mode. Because the mock cannot understand a
prompt, generate() also takes keyword "hints" (task, context, question) that only the mock
reads; Ollama ignores them because the same information is already inside the prompt.
"""
import json
import urllib.error
import urllib.request

import numpy as np

from bookorbit.ai import mock_llm
from bookorbit.errors import LLMUnavailable, ModelUnavailable

GENERATE_TIMEOUT = 30        # seconds; UC-12 E3 "no reply within 30 s"
EMBED_TIMEOUT = 15           # SRS 4.22 embed
PROBE_TIMEOUT = 2            # SRS 4.22 is_available
TEMPERATURE = 0.3            # SRS 4.22 generate options


class LLMClient:
    is_mock = False
    mode = ""
    mode_label = ""
    embed_model_id = ""      # stored with every vector; a change forces a re-index

    def is_available(self) -> bool:
        raise NotImplementedError

    def generate(self, prompt: str, max_tokens: int = 300, timeout: float = GENERATE_TIMEOUT, *,
                 task: str = "answer", context: list[str] | None = None, question: str = "") -> str:
        """Return the model's reply. task/context/question are hints for the MOCK only."""
        raise NotImplementedError

    def embed(self, text: str) -> np.ndarray:
        """Unit-length embedding vector of the text."""
        raise NotImplementedError


class MockLLM(LLMClient):
    is_mock = True
    mode = "mock"
    embed_model_id = mock_llm.EMBED_MODEL_ID

    def __init__(self, reason: str = "LLM_MODE=mock"):
        self.mode_label = f"MOCK AI ({reason})"

    def is_available(self) -> bool:
        return True

    def generate(self, prompt, max_tokens=300, timeout=GENERATE_TIMEOUT, *, task="answer",
                 context=None, question=""):
        context = context or []
        if task == "classify":
            return mock_llm.classify(question, context)
        if task == "summarize":
            return mock_llm.summarize(context)
        if task == "explain":
            return mock_llm.explain(question, context)
        if task == "define":
            return mock_llm.define(question, context)
        if task == "quiz":
            return mock_llm.quiz(context)
        return mock_llm.answer(question, context)         # "answer" / "ask"

    def embed(self, text):
        return mock_llm.embed(text)


class OfflineLLM(LLMClient):
    """LLM_MODE=offline: acts exactly like an Ollama server that is not running."""
    mode = "offline"
    mode_label = "AI OFFLINE (LLM_MODE=offline)"
    embed_model_id = "offline"

    def is_available(self):
        return False

    def generate(self, prompt, max_tokens=300, timeout=GENERATE_TIMEOUT, **_hints):
        raise LLMUnavailable("The assistant is offline - please try again later.")

    def embed(self, text):
        raise ModelUnavailable("The embedding model is offline.")


class OllamaLLM(LLMClient):
    """Real mode: http://localhost:11434 by default (OLLAMA_URL), no paid API, no internet."""
    mode = "real"

    def __init__(self, url: str, model: str, embed_model: str):
        self.url = url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.mode_label = f"Local AI: Ollama {model}"
        self.embed_model_id = f"ollama:{embed_model}"

    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def installed_models(self) -> set[str] | None:
        """Names of the pulled models, or None when Ollama does not answer."""
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=PROBE_TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                data = json.loads(resp.read().decode())
        except (OSError, ValueError):            # connection refused, timeout, bad JSON
            return None
        names = set()
        for m in data.get("models", []):
            name = m.get("name", "")
            names.add(name)
            if name.endswith(":latest"):         # "nomic-embed-text:latest" == "nomic-embed-text"
                names.add(name[: -len(":latest")])
        return names

    def is_available(self) -> bool:
        """SRS 4.22 checks that /api/tags answers. We also check that both configured
        models are pulled (ASSUMPTIONS A-28); otherwise every call would fail."""
        names = self.installed_models()
        return names is not None and {self.model, self.embed_model} <= names

    def generate(self, prompt, max_tokens=300, timeout=GENERATE_TIMEOUT, **_hints):
        try:
            data = self._post("/api/generate", {
                "model": self.model, "prompt": prompt, "stream": False,
                "options": {"num_predict": max_tokens, "temperature": TEMPERATURE}}, timeout)
        except (OSError, ValueError) as exc:     # refused, HTTP error, timeout, bad JSON
            raise LLMUnavailable("The assistant is offline - please try again later.") from exc
        return str(data.get("response", "")).strip()

    def embed(self, text):
        try:
            data = self._post("/api/embeddings", {"model": self.embed_model, "prompt": text}, EMBED_TIMEOUT)
            v = np.asarray(data["embedding"], dtype=float)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ModelUnavailable("The embedding model is not available.") from exc
        norm = np.linalg.norm(v)
        if norm == 0:
            raise ModelUnavailable("The embedding model returned an empty vector.")
        return v / norm


def get_llm(cfg: dict) -> LLMClient:
    """Pick the client from LLM_MODE; a missing Ollama falls back to the labelled MOCK."""
    mode = cfg.get("LLM_MODE", "mock").strip().lower()
    if mode == "offline":
        return OfflineLLM()
    if mode == "real":
        client = OllamaLLM(cfg["OLLAMA_URL"], cfg["OLLAMA_MODEL"], cfg["OLLAMA_EMBED_MODEL"])
        if client.is_available():
            return client
        return MockLLM("Ollama or its models not found at " + client.url)
    return MockLLM()
