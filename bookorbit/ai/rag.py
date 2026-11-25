"""RAGRetriever - retrieval for the chatbot and the Reading Companion (SRS 4.21).

RAG = "retrieval-augmented generation": before the language model answers, we look up
the most relevant pieces ("chunks") of our own data and give only those to the model, so
it answers from store facts and book text instead of its memory.

1. Indexing (start-up): store policies, one catalog line per book and the book texts are
   cut into chunks of ~250 words (40 words overlap, so a sentence cut at a border is
   still whole in one of the two chunks). Each chunk is turned into a vector by
   LLMClient.embed and saved as data/rag/<chunk_id>.npy; the record goes to rag_chunks.txt.
2. Retrieval: the question is embedded the same way; the chunks whose vectors point in the
   most similar direction (cosine similarity) are returned, best first, if they are
   similar enough (MIN_SIM).
"""
import threading

import numpy as np

from bookorbit.ai.texts import read_chapters
from bookorbit.errors import ModelUnavailable

CHUNK_WORDS = 250            # SRS 4.21
OVERLAP = 40                 # SRS 4.21
# Minimum cosine similarity for a chunk to count as relevant. 0.45 is the SRS value for
# nomic-embed-text. The MOCK's word-count vectors give much lower numbers for the same
# relevance (a 6-word question shares only a few words with a 250-word chunk), so it has
# its own threshold, chosen by measuring the seeded data (ASSUMPTIONS A-29).
MIN_SIM_REAL = 0.45
MIN_SIM_MOCK = 0.15

POLICY, CATALOG, BOOK = "POLICY", "CATALOG", "BOOK"      # RAG_CHUNK.source
PUBLIC = "PUBLIC"                                        # RAG_CHUNK.scope (C-05: the only one used)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))                           # both are unit vectors


class RAGRetriever:
    def __init__(self, fs, llm):
        self.fs = fs
        self.llm = llm
        self.vectors: dict[str, np.ndarray] = {}
        self.ready = False                               # True once build_index has finished
        self.error = ""                                  # why the index could not be built
        self._lock = threading.Lock()

    @property
    def min_sim(self) -> float:
        return MIN_SIM_MOCK if self.llm.is_mock else MIN_SIM_REAL

    # ---------------------------------------------------------------- indexing
    def build_index(self) -> None:
        """Start-up (background thread, SRS 4.24): load existing vectors, create missing ones.

        Differences from the SRS pseudo-code (ASSUMPTIONS A-30):
        * vectors made by another embedding model (e.g. MOCK -> real Ollama) are useless,
          so the whole index is rebuilt when the model changes;
        * books with a text and indexed = false are indexed at every start, not only when
          the index is empty (UC-15 E4: "indexed the next time the app starts");
        * a book without a CATALOG chunk (added after the first build) gets one."""
        try:
            with self._lock:
                self._rebuild_if_model_changed()
                chunks = self.fs.load("rag_chunks")
                if not chunks:
                    for paragraph in self._policy_paragraphs():
                        self.add_chunk(POLICY, None, PUBLIC, paragraph)
                have_catalog = {c["book_id"] for c in chunks if c["source"] == CATALOG}
                for b in self.fs.load("books"):
                    if b["book_id"] not in have_catalog:
                        self.add_chunk(CATALOG, b["book_id"], PUBLIC, self.catalog_text(b))
                    if b.get("text_path") and not b.get("indexed"):
                        self.index_book(b)
                self.vectors = {}
                for c in self.fs.load("rag_chunks"):
                    self.vectors[c["chunk_id"]] = np.load(self.fs.resolve(c["vector_path"]))
                self.ready, self.error = True, ""
        except ModelUnavailable as e:                    # offline: the companion can still show text
            self.ready, self.error = False, str(e)

    def _rebuild_if_model_changed(self) -> None:
        chunks = self.fs.load("rag_chunks")
        if chunks and any(c.get("embed_model") != self.llm.embed_model_id for c in chunks):
            for c in chunks:
                path = self.fs.resolve(c["vector_path"])
                if path.exists():
                    path.unlink()
            self.fs.save_all("rag_chunks", [])
            with self.fs.lock:
                books = self.fs.load("books")
                for b in books:
                    b["indexed"] = False
                self.fs.save_all("books", books)

    def _policy_paragraphs(self) -> list[str]:
        path = self.fs.dir / "policies.txt"
        if not path.exists():
            return []
        return [p.strip().replace("\n", " ") for p in path.read_text(encoding="utf-8").split("\n\n") if p.strip()]

    @staticmethod
    def catalog_text(b: dict) -> str:
        """SRS 4.21: title by author, category, $price. description (+ keywords, A-30)."""
        return (f"{b['title']} by {b['author']}, {b['category']}, ${b['price']:.2f}. "
                f"{b['description']} Keywords: {b['keywords']}.")

    @staticmethod
    def chunk(text: str) -> list[str]:
        words = text.split()
        out, i = [], 0
        while i < len(words):
            out.append(" ".join(words[i:i + CHUNK_WORDS]))
            if i + CHUNK_WORDS >= len(words):
                break                                    # last piece reached the end
            i += CHUNK_WORDS - OVERLAP
        return out

    def index_book(self, book: dict) -> int:
        """Chunk and embed a book's text, chapter by chapter (C-05: chunks keep their chapter)."""
        n = 0
        for chapter_no, _title, body in read_chapters(self.fs.resolve(book["text_path"])):
            for piece in self.chunk(body):
                self.add_chunk(BOOK, book["book_id"], PUBLIC, piece, chapter=chapter_no)
                n += 1
        self.fs.update("books", "book_id", book["book_id"], {"indexed": True})
        return n

    def add_chunk(self, source: str, book_id, scope: str, text: str, chapter=None) -> dict:
        v = self.llm.embed(text)                         # ModelUnavailable when offline
        with self.fs.lock:
            cid = self.fs.next_id("rag_chunks", "C")
            rel = f"rag/{cid}.npy"
            self.fs.resolve(rel).parent.mkdir(parents=True, exist_ok=True)
            np.save(self.fs.resolve(rel), v)
            rec = self.fs.append("rag_chunks", {
                "chunk_id": cid, "book_id": book_id, "source": source, "scope": scope,
                "chapter": chapter, "text": text, "vector_path": rel,
                "embed_model": self.llm.embed_model_id})
        self.vectors[cid] = v
        return rec

    # ---------------------------------------------------------------- retrieval
    def retrieve(self, query: str, scopes, k: int = 4, book_id=None, chapter=None,
                 min_sim: float | None = None) -> list[str]:
        """Up to k chunk texts, most similar first.

        The chatbot (book_id None) never sees full book texts, only POLICY and CATALOG
        chunks. min_sim=0 turns the relevance cut-off off: the Reading Companion uses it
        to get "the chunks of chapter n" for summaries and quizzes (deviation D-18)."""
        if not self.ready or not query.strip():
            return []
        qv = self.llm.embed(query)
        cands = [c for c in self.fs.load("rag_chunks")
                 if c["scope"] in scopes
                 and (book_id is None or c["book_id"] == book_id)
                 and (chapter is None or c.get("chapter") == chapter)]
        if book_id is None:
            cands = [c for c in cands if c["source"] != BOOK]
        threshold = self.min_sim if min_sim is None else min_sim
        scored = [(cosine(qv, self.vectors[c["chunk_id"]]), c) for c in cands if c["chunk_id"] in self.vectors]
        scored.sort(key=lambda sc: (-sc[0], sc[1]["chunk_id"]))
        return [c["text"] for s, c in scored[:k] if s >= threshold]

    def retrieve_scored(self, query: str, scopes, k: int = 4, book_id=None):
        """Same as retrieve but with scores and no cut-off (used to tune MIN_SIM and in tests)."""
        qv = self.llm.embed(query)
        cands = [c for c in self.fs.load("rag_chunks") if c["scope"] in scopes
                 and (book_id is None or c["book_id"] == book_id) and (book_id or c["source"] != BOOK)]
        scored = sorted(((cosine(qv, self.vectors[c["chunk_id"]]), c) for c in cands), key=lambda x: -x[0])
        return scored[:k]
