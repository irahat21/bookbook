"""ReadingCompanion (SRS 4.23): UC-14, R15 (applied to every action, A-10), D-18."""
import json

from bookorbit import rules
from bookorbit.ai.llm import MockLLM, OfflineLLM
from bookorbit.errors import CompanionError
from bookorbit.services.companion import BUY_TO_READ, NO_TEXT, OFFLINE, ReadingCompanion
from bookorbit.services.session import Session
from tests.helpers import TempStoreCase

TEXT = """The Lighthouse Book

CHAPTER 1: The Light
Wren climbed the lighthouse stairs every evening with her father. The great lens turned slowly above the harbour.
The keeper polished the brass rail and wrote the wind direction in the logbook.

CHAPTER 2: The Letters
Behind the oil cans Wren discovered letters tied with a blue ribbon. Her mother had written them long ago.
The secret letters explained why the keeper loved the lighthouse so much.

CHAPTER 3: The Storm
A violent storm arrived from the northeast. The electric lamp failed and the old oil lamp saved a small boat.
The fishermen watched the beam sweeping across the black water from their windows.
In the morning the inspector climbed the stairs and changed his decision about the lighthouse.
"""


class SpyLLM(MockLLM):
    """Records the excerpts each call received; can return a fixed reply."""

    def __init__(self, reply=None):
        super().__init__()
        self.reply, self.calls = reply, []

    def generate(self, prompt, *args, **kw):
        self.calls.append(kw)
        return self.reply if self.reply is not None else super().generate(prompt, *args, **kw)


class CompanionTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.book = self.add_text_book(TEXT, title="The Lighthouse Book")
        self.plain = self.add_book(title="No Text Here")
        self.ctx.rag.build_index()
        self.reader = self.add_user("rita", balance=100.0)
        self.owner = self.add_user("olga", role=rules.VC, balance=100.0)
        self.ctx.purchases.purchase(self.session_for(self.owner), self.book["book_id"])
        self.comp = self.ctx.companion

    def open(self, user, comp=None):
        return (comp or self.comp).open(self.session_for(user), self.book["book_id"])

    def with_llm(self, llm):
        return ReadingCompanion(self.fs, self.ctx.rag, llm, self.ctx.purchases)

    # ---- opening (UC-14 steps 1-2)
    def test_only_customers(self):
        for s in (Session(self.fs), self.session_for(self.add_user("sue", role=rules.SU))):
            with self.assertRaises(PermissionError):
                self.comp.open(s, self.book["book_id"])

    def test_e1_book_without_text(self):
        with self.assertRaises(CompanionError) as cm:
            self.comp.open(self.session_for(self.reader), self.plain["book_id"])
        self.assertEqual(str(cm.exception), NO_TEXT)

    def test_open_lists_chapters_and_ownership(self):
        st = self.open(self.reader)
        self.assertEqual(st.chapters, [(1, "The Light"), (2, "The Letters"), (3, "The Storm")])
        self.assertFalse(st.owned)
        self.assertTrue(self.open(self.owner).owned)

    # ---- R15
    def test_r15_owner_reads_every_chapter(self):
        st = self.open(self.owner)
        self.assertIn("violent storm", self.comp.load_chapter(st, 3))

    def test_r15_non_owner_reads_chapter_one_only(self):
        st = self.open(self.reader)
        self.assertIn("lighthouse stairs", self.comp.load_chapter(st, 1))
        with self.assertRaises(CompanionError) as cm:                     # E2
            self.comp.load_chapter(st, 2)
        self.assertEqual((str(cm.exception), cm.exception.buy), (BUY_TO_READ, True))

    def test_r15_applies_to_every_action(self):                         # A-10
        st = self.open(self.reader)
        for action in (lambda: self.comp.summarize(st, 2), lambda: self.comp.quiz(st, 3)):
            with self.assertRaises(CompanionError) as cm:
                action()
            self.assertTrue(cm.exception.buy)
        spy = SpyLLM()
        comp = self.with_llm(spy)
        st = self.open(self.reader, comp)
        comp.ask(st, "Who wrote the secret letters with a blue ribbon?")   # the answer is in chapter 2
        comp.explain(st, "secret letters blue ribbon")
        for call in spy.calls:
            self.assertFalse(any("ribbon" in c for c in call["context"]), call["context"])
        # the owner's companion does find chapter 2
        spy.calls.clear()
        comp.ask(self.open(self.owner, comp), "Who wrote the secret letters with a blue ribbon?")
        self.assertTrue(any("ribbon" in c for c in spy.calls[0]["context"]))

    def test_progress_resumes_but_never_past_the_preview(self):
        st = self.open(self.owner)
        self.comp.load_chapter(st, 3)
        self.assertEqual(self.open(self.owner).chapter, 3)               # resumes (UC-14 step 2)
        rows = self.fs.load("reading_progress")
        self.assertEqual([(r["chapter"], r["last_action"]) for r in rows], [(3, "read")])
        # a non-owner with a saved chapter 3 (e.g. written before a refund) restarts at 1
        self.fs.append("reading_progress", {"progress_id": "RP-0009", "user_id": self.reader["user_id"],
                                            "book_id": self.book["book_id"], "chapter": 3,
                                            "last_action": "read", "updated_at": "x"})
        self.assertEqual(self.open(self.reader).chapter, 1)

    # ---- AI actions (UC-14 steps 3-6)
    def test_summary_uses_only_that_chapter(self):
        spy = SpyLLM()
        comp = self.with_llm(spy)
        st = self.open(self.owner, comp)
        out = comp.summarize(st, 3)
        self.assertTrue(out.startswith("• "))
        self.assertTrue(all("storm" in c for c in spy.calls[0]["context"]))   # D-18: chapter 3 chunks
        self.assertEqual(self.fs.load("reading_progress")[0]["last_action"], "summarize")

    def test_e3_explain_without_selection(self):
        with self.assertRaises(CompanionError) as cm:
            self.comp.explain(self.open(self.owner), "   ")
        self.assertEqual(str(cm.exception), "Select a passage first")

    def test_define_word_in_context(self):
        st = self.open(self.owner)
        self.assertIn("logbook", self.comp.define(st, "logbook"))

    def test_quiz_three_valid_questions(self):
        qs = self.comp.quiz(self.open(self.owner), 1)
        self.assertEqual(len(qs), 3)
        self.assertTrue(all(len(q["options"]) == 4 and 0 <= q["answer_index"] < 4 for q in qs))

    def test_quiz_invalid_json_retried_once_then_error(self):
        spy = SpyLLM(reply="Sorry, here is no JSON.")
        comp = self.with_llm(spy)
        with self.assertRaises(CompanionError):
            comp.quiz(self.open(self.owner, comp), 1)
        self.assertEqual(len(spy.calls), 2)

    def test_quiz_on_a_one_sentence_chapter_gives_a_clear_error(self):
        # The MOCK needs other sentences to take wrong options from; with one usable
        # sentence it makes no question, and the reader sees a clear message.
        tiny = self.add_text_book("CHAPTER 1\nThe electric lamp failed and the old oil lamp saved a small boat.")
        self.ctx.rag.build_index()
        self.ctx.purchases.purchase(self.session_for(self.owner), tiny["book_id"])
        with self.assertRaises(CompanionError) as cm:
            self.comp.quiz(self.comp.open(self.session_for(self.owner), tiny["book_id"]), 1)
        self.assertIn("Couldn't make a quiz", str(cm.exception))

    def test_parse_quiz_filters_bad_questions(self):
        good = {"q": "Who?", "options": ["a", "b", "c", "d"], "answer_index": 2}
        raw = "Here you go:\n```json\n" + json.dumps([good, {"q": "x", "options": ["a"], "answer_index": 0},
                                                       {"q": "y", "options": list("abcd"), "answer_index": 4}]) + "\n```"
        self.assertEqual(ReadingCompanion.parse_quiz(raw), [good])
        self.assertEqual(ReadingCompanion.parse_quiz("[not json"), [])

    def test_e4_offline_text_still_readable(self):
        comp = self.with_llm(OfflineLLM())
        st = self.open(self.owner, comp)
        self.assertIn("lighthouse", comp.load_chapter(st, 1))
        for action in (lambda: comp.summarize(st, 1), lambda: comp.ask(st, "why?"),
                       lambda: comp.quiz(st, 1), lambda: comp.define(st, "lens")):
            with self.assertRaises(CompanionError) as cm:
                action()
            self.assertEqual(str(cm.exception), OFFLINE)

    def test_works_before_the_index_is_built(self):
        """Index still building: answers fall back to the chapter's own text (D-18)."""
        from bookorbit.ai.rag import RAGRetriever
        comp = ReadingCompanion(self.fs, RAGRetriever(self.fs, self.ctx.llm), self.ctx.llm, self.ctx.purchases)
        out = comp.summarize(self.open(self.owner, comp), 2)
        self.assertIn("letters", out.lower())
