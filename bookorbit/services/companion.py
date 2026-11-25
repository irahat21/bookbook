"""ReadingCompanion - the Smart Reading Companion (SRS 4.23, UC-14, R15).

An AI reading assistant grounded in the book's own text: every answer is generated from
excerpts of this book (retrieved by RAGRetriever), not from the language model's memory.

R15: Registered and VIP Customers, books with a text. Owned books are fully readable;
other books only chapter 1 (rules.FREE_CHAPTERS). ASSUMPTIONS A-10: the limit applies to
EVERY action, so for a non-owned book even "Ask" and "Explain" only see chapter 1.
"""
import json
import re
from dataclasses import dataclass

from bookorbit import clock, rules
from bookorbit.ai.rag import PUBLIC
from bookorbit.ai.texts import read_chapters
from bookorbit.errors import CompanionError, LLMUnavailable, ModelUnavailable

OFFLINE = "The assistant is offline - the chapter text is still readable."      # UC-14 E4
NO_TEXT = "The Reading Companion isn't available for this book"                  # UC-14 E1
BUY_TO_READ = "Buy the book to keep reading"                                     # UC-14 E2


@dataclass
class CompanionState:
    book: dict
    user_id: str
    chapters: list          # [(number, title)]
    chapter: int            # the chapter being read
    owned: bool

    def readable(self, n: int) -> bool:
        """R15: every chapter of an owned book, otherwise only the free ones."""
        return self.owned or n <= rules.FREE_CHAPTERS


class ReadingCompanion:
    def __init__(self, fs, rag, llm, purchases):
        self.fs = fs
        self.rag = rag
        self.llm = llm
        self.purchases = purchases

    # ---------------------------------------------------------------- reading
    def open(self, session, book_id: str) -> CompanionState:
        session.require(rules.RC, rules.VC)
        book = self.fs.find("books", "book_id", book_id)
        if book is None or not book.get("text_path") or not self.fs.resolve(book["text_path"]).exists():
            raise CompanionError(NO_TEXT)                                # E1
        uid = session.user["user_id"]
        owned = self.purchases.already_owned(uid, book_id)
        chapters = [(n, title) for n, title, _body in self._chapters(book)]
        p = self._progress(uid, book_id)
        chapter = p["chapter"] if p else 1
        if not owned or chapter > len(chapters):                         # R15: back to the free chapter
            chapter = 1
        return CompanionState(book, uid, chapters, chapter, owned)

    def load_chapter(self, state: CompanionState, n: int) -> str:
        self._check_chapter(state, n)
        text = self._chapters(state.book)[n - 1][2]
        self.save_progress(state, n, "read")
        return text

    # ---------------------------------------------------------------- AI actions
    def summarize(self, state: CompanionState, n: int) -> str:
        self._check_chapter(state, n)
        self._require_llm()
        chunks = self._chunks(state, "summary of chapter " + str(n), k=6, chapter=n, whole_chapter=True)
        return self._ask_llm("Summarize this chapter in 5 bullet points for a student.", chunks, state,
                             "summarize", task="summarize")

    def explain(self, state: CompanionState, selection: str) -> str:
        if not (selection or "").strip():
            raise CompanionError("Select a passage first")               # E3
        self._require_llm()
        chunks = self._chunks(state, selection, k=3, chapter=self._limit(state))
        return self._ask_llm("Explain this passage in plain modern English, with its context: \""
                             + selection.strip() + "\"", chunks, state, "explain", task="explain",
                             question=selection.strip())

    def define(self, state: CompanionState, word: str) -> str:
        word = (word or "").strip().strip(".,;:!?\"'")
        if not word:
            raise CompanionError("Select a word first")
        self._require_llm()
        chunks = self._chunks(state, word, k=2, chapter=state.chapter, whole_chapter=True)
        return self._ask_llm(f"Define '{word}' as it is used here (the book's era and meaning).", chunks, state,
                             "define", task="define", question=word)

    def quiz(self, state: CompanionState, n: int, count: int = 3) -> list[dict]:
        """Up to `count` questions {q, options[4], answer_index}; answers hidden by the screen."""
        self._check_chapter(state, n)
        self._require_llm()
        chunks = self._chunks(state, "key events of chapter " + str(n), k=6, chapter=n, whole_chapter=True)
        instruction = (f"Write {count} multiple-choice questions as JSON [{{q, options[4], answer_index}}] "
                       "using only the text.")
        for _attempt in range(2):                                        # SRS: retry once if invalid
            qs = self.parse_quiz(self._ask_llm(instruction, chunks, state, "quiz", task="quiz"))
            if qs:
                return qs[:count]
        raise CompanionError("Couldn't make a quiz from this chapter - try again")

    def ask(self, state: CompanionState, question: str) -> str:
        if not (question or "").strip():
            raise CompanionError("Type a question first")
        self._require_llm()
        chunks = self._chunks(state, question, k=4, chapter=self._limit(state))
        return self._ask_llm(question.strip(), chunks, state, "ask", task="ask", question=question.strip())

    def save_progress(self, state: CompanionState, n: int, action: str) -> None:
        """One READING_PROGRESS row per user and book (UC-14 step 6)."""
        with self.fs.lock:
            row = self._progress(state.user_id, state.book["book_id"])
            if row:
                self.fs.update("reading_progress", "progress_id", row["progress_id"],
                               {"chapter": n, "last_action": action, "updated_at": clock.now()})
            else:
                self.fs.append("reading_progress", {
                    "progress_id": self.fs.next_id("reading_progress", "RP"), "user_id": state.user_id,
                    "book_id": state.book["book_id"], "chapter": n, "last_action": action,
                    "updated_at": clock.now()})
        state.chapter = n

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def parse_quiz(raw: str) -> list[dict]:
        """SRS: keep questions with 4 options and 0 <= answer_index < 4. Real models often
        wrap the JSON in text or a code fence, so we take the outermost [...]."""
        m = re.search(r"\[.*\]", raw or "", re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return []
        out = []
        for q in data if isinstance(data, list) else []:
            if not isinstance(q, dict):
                continue
            text, options, idx = q.get("q") or q.get("question"), q.get("options"), q.get("answer_index")
            if (isinstance(text, str) and isinstance(options, list) and len(options) == 4
                    and isinstance(idx, int) and 0 <= idx < 4):
                out.append({"q": text, "options": [str(o) for o in options], "answer_index": idx})
        return out

    def _chapters(self, book: dict) -> list:
        return read_chapters(self.fs.resolve(book["text_path"]))

    def _progress(self, user_id: str, book_id: str):
        return next((r for r in self.fs.load("reading_progress")
                     if r["user_id"] == user_id and r["book_id"] == book_id), None)

    def _check_chapter(self, state: CompanionState, n: int) -> None:
        if not 1 <= n <= len(state.chapters):
            raise CompanionError("No such chapter")
        if not state.readable(n):                                        # R15 -> E2
            raise CompanionError(BUY_TO_READ, buy=True)

    @staticmethod
    def _limit(state: CompanionState):
        """A-10: book-wide retrieval for owned books, chapter 1 only otherwise."""
        return None if state.owned else rules.FREE_CHAPTERS

    def _require_llm(self) -> None:
        """Checked before retrieval: offline, the embedding model is gone too (UC-14 E4)."""
        if not self.llm.is_available():
            raise CompanionError(OFFLINE)

    def _chunks(self, state, query, k, chapter=None, whole_chapter=False) -> list[str]:
        """Relevant excerpts of THIS book (UC-14 step 4). whole_chapter: no similarity
        cut-off (D-18). If nothing is found (index still building, or no excerpt similar
        enough) the current readable chapter itself is used, so answers stay grounded."""
        try:
            chunks = self.rag.retrieve(query, {PUBLIC}, k=k, book_id=state.book["book_id"], chapter=chapter,
                                       min_sim=0 if whole_chapter else None)
        except ModelUnavailable as e:
            raise CompanionError(OFFLINE) from e
        if not chunks:
            n = chapter or (state.chapter if state.readable(state.chapter) else 1)
            chunks = self.rag.chunk(self._chapters(state.book)[n - 1][2])[:k]
        return chunks

    def _ask_llm(self, instruction, chunks, state, action, task, question="") -> str:
        prompt = (f"You are a reading companion for '{state.book['title']}'. Use only these excerpts:\n"
                  + "\n---\n".join(chunks) + "\n" + instruction)
        try:
            answer = self.llm.generate(prompt, task=task, context=chunks, question=question)
        except LLMUnavailable as e:
            raise CompanionError(OFFLINE) from e
        self.save_progress(state, state.chapter, action)
        return answer
