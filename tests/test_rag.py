"""RAGRetriever (SRS 4.21) with the MOCK embeddings."""
import numpy as np

from bookorbit.ai.llm import OfflineLLM
from bookorbit.ai.rag import BOOK, CATALOG, CHUNK_WORDS, OVERLAP, POLICY, PUBLIC, RAGRetriever
from tests.helpers import TempStoreCase

DRAGON_TEXT = """The Dragon Book

CHAPTER 1: The Cave
Pellinore the dragon collected maps in a cave beneath the Thornback Mountains. He kept sea charts and star maps.

CHAPTER 2: The Thief
A thief named Ilsa Quill stole the map of the Unwritten Coast and left a drawing of a feather.
"""
VIP = "VIP Customers pay 90 percent of the list price, a 10 percent discount."
FINE = "Insufficient funds: the purchase is rejected and a fine of one dollar is charged."


class ChunkTests(TempStoreCase):
    def test_chunk_sizes_and_overlap(self):
        words = [f"w{i}" for i in range(600)]
        pieces = RAGRetriever.chunk(" ".join(words))
        self.assertEqual([len(p.split()) for p in pieces], [250, 250, 180])
        step = CHUNK_WORDS - OVERLAP
        self.assertEqual(pieces[1].split()[0], words[step])                   # starts 40 words early
        self.assertEqual(pieces[0].split()[-OVERLAP:], pieces[1].split()[:OVERLAP])
        self.assertEqual(pieces[2].split()[-1], "w599")                       # nothing lost at the end

    def test_short_text_is_one_chunk(self):
        self.assertEqual(RAGRetriever.chunk("just a few words"), ["just a few words"])
        self.assertEqual(RAGRetriever.chunk(""), [])


class RetrieverTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.write_policies(VIP, FINE)
        self.plain = self.add_book(title="Ocean Atlas", category="Science", keywords="ocean, maps",
                                   description="Maps of the deep ocean floor.")
        self.dragon = self.add_text_book(DRAGON_TEXT, title="The Dragon Who Collected Maps", category="Fantasy")
        self.rag = self.ctx.rag
        self.rag.build_index()

    def test_build_creates_policy_catalog_and_book_chunks(self):
        chunks = self.fs.load("rag_chunks")
        by_source = {s: [c for c in chunks if c["source"] == s] for s in (POLICY, CATALOG, BOOK)}
        self.assertEqual(len(by_source[POLICY]), 2)
        self.assertEqual(len(by_source[CATALOG]), 2)
        self.assertEqual(sorted(c["chapter"] for c in by_source[BOOK]), [1, 2])   # C-05: chapter kept
        self.assertTrue(all(c["scope"] == PUBLIC for c in chunks))
        self.assertTrue(self.fs.find("books", "book_id", self.dragon["book_id"])["indexed"])
        self.assertTrue(all(self.fs.resolve(c["vector_path"]).exists() for c in chunks))
        self.assertTrue(self.rag.ready)

    def test_second_build_adds_nothing(self):
        n = len(self.fs.load("rag_chunks"))
        self.rag.build_index()
        self.assertEqual(len(self.fs.load("rag_chunks")), n)

    def test_unindexed_book_is_indexed_at_next_start(self):          # UC-15 E4
        later = self.add_text_book("CHAPTER 1\nA story about lighthouses and storms.", title="Later")
        RAGRetriever(self.fs, self.ctx.llm).build_index()
        chunks = [c for c in self.fs.load("rag_chunks") if c["book_id"] == later["book_id"]]
        self.assertEqual(sorted(c["source"] for c in chunks), [BOOK, CATALOG])

    def test_model_change_rebuilds_index(self):
        recs = self.fs.load("rag_chunks")
        for r in recs:
            r["embed_model"] = "some-old-model"
        self.fs.save_all("rag_chunks", recs)
        RAGRetriever(self.fs, self.ctx.llm).build_index()
        chunks = self.fs.load("rag_chunks")
        self.assertEqual(len(chunks), len(recs))
        self.assertTrue(all(c["embed_model"] == self.ctx.llm.embed_model_id for c in chunks))

    def test_chatbot_retrieval_finds_policy_and_never_book_text(self):
        self.assertEqual(self.rag.retrieve("What discount do VIP customers get?", {PUBLIC}, k=1), [VIP])
        hits = self.rag.retrieve("Who stole the map of the Unwritten Coast?", {PUBLIC})
        self.assertFalse(any("Ilsa Quill" in h for h in hits))       # BOOK chunks are companion-only

    def test_unrelated_question_finds_nothing(self):                 # below MIN_SIM -> [General AI]
        self.assertEqual(self.rag.retrieve("How do I bake a chocolate cake?", {PUBLIC}), [])

    def test_book_and_chapter_filters(self):
        # One question that matches BOTH chapters ("map" is in each), so any difference in
        # the results below comes from the chapter filter, not from the MIN_SIM cut-off.
        bid, q = self.dragon["book_id"], "who stole the map"
        both = self.rag.retrieve(q, {PUBLIC}, book_id=bid)
        # no chapter filter: chapter 2 (best match), chapter 1, and this book's own CATALOG
        # line (it has the book's id but no chapter, SRS 4.21)
        self.assertEqual(len(both), 3)
        self.assertIn("Ilsa Quill", both[0])
        self.assertIn("Pellinore", both[1])
        self.assertTrue(both[2].startswith("The Dragon Who Collected Maps by"))
        ch1 = self.rag.retrieve(q, {PUBLIC}, book_id=bid, chapter=1)
        self.assertEqual(len(ch1), 1)
        self.assertIn("Pellinore", ch1[0])
        self.assertNotIn("Ilsa Quill", ch1[0])
        ch2 = self.rag.retrieve(q, {PUBLIC}, book_id=bid, chapter=2)
        self.assertEqual(len(ch2), 1)
        self.assertIn("Ilsa Quill", ch2[0])
        self.assertNotIn("Pellinore", ch2[0])
        # book filter: the other book's catalog line never comes back for this book
        self.assertFalse(any("Ocean Atlas" in h for h in self.rag.retrieve("maps of the ocean", {PUBLIC}, book_id=bid)))
        # min_sim=0 (D-18): "the chunks of chapter 1", whatever the query says
        whole = self.rag.retrieve("summary of chapter 1", {PUBLIC}, k=6, book_id=bid, chapter=1, min_sim=0)
        self.assertEqual(len(whole), 1)
        self.assertIn("Thornback", whole[0])

    def test_vectors_are_unit_length(self):
        for v in self.rag.vectors.values():
            self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=6)


class OfflineIndexTests(TempStoreCase):
    def test_offline_index_is_not_ready_and_retrieves_nothing(self):
        self.write_policies(VIP)
        rag = RAGRetriever(self.fs, OfflineLLM())
        rag.build_index()
        self.assertFalse(rag.ready)
        self.assertIn("offline", rag.error)
        self.assertEqual(rag.retrieve("VIP discount", {PUBLIC}), [])
