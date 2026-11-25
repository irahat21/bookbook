"""CoverIndex (SRS 4.9) and CatalogService.search_by_cover: UC-04 step 4, E3, E4, E5."""
import io

import numpy as np
from PIL import Image

from bookorbit.ai.covers import COVER_MIN_SIM_MOCK, NOT_AN_IMAGE, CoverIndex, MockCoverEmbedder, get_cover_embedder
from bookorbit.config import DEFAULTS
from bookorbit.errors import ModelUnavailable
from seed import make_cover, make_cover_photo, make_face_photo
from tests.helpers import TempStoreCase


class CoverTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        (self.fs.dir / "covers").mkdir(exist_ok=True)
        self.books = []
        for i in range(8):                          # 8 covers in 4 "categories" (similar colours in pairs)
            b = self.add_book(title=f"Book {i}")
            png = make_cover(b["book_id"], i // 2)
            (self.fs.dir / "covers" / f"{b['book_id']}.png").write_bytes(png)
            self.fs.update("books", "book_id", b["book_id"], {"cover_path": f"covers/{b['book_id']}.png"})
            self.books.append(b)
        self.covers = self.ctx.covers
        self.covers.build()

    def cover_png(self, book):
        return self.fs.resolve(f"covers/{book['book_id']}.png").read_bytes()

    def test_build_stores_a_vector_per_cover(self):
        self.assertTrue(self.covers.ready)
        self.assertEqual(len(self.covers.ids), 8)
        for b in self.fs.load("books"):
            v = np.load(self.fs.resolve(b["cover_vec_path"]))
            self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=6)

    def test_second_build_reuses_vectors_and_model_change_rebuilds(self):
        path = self.fs.resolve(self.fs.load("books")[0]["cover_vec_path"])
        before = path.stat().st_mtime_ns
        CoverIndex(self.fs, MockCoverEmbedder()).build()
        self.assertEqual(path.stat().st_mtime_ns, before)                  # nothing recomputed
        (self.fs.dir / "covers" / "index_model.txt").write_text("another-model")
        CoverIndex(self.fs, MockCoverEmbedder()).build()
        self.assertNotEqual(path.stat().st_mtime_ns, before)               # A-33: re-embedded

    def test_photo_of_each_cover_finds_it_first(self):                    # UC-04 step 4
        for b in self.books:
            for variant in (0, 1):                                         # JPEG and PNG photos
                hits = self.ctx.catalog.search_by_cover(make_cover_photo(self.cover_png(b), variant))
                self.assertEqual(hits[0][0]["book_id"], b["book_id"])
                self.assertGreaterEqual(hits[0][1], COVER_MIN_SIM_MOCK)

    def test_at_most_five_results_best_first(self):
        hits = self.ctx.catalog.search_by_cover(self.cover_png(self.books[0]))
        self.assertLessEqual(len(hits), 5)
        sims = [s for _b, s in hits]
        self.assertEqual(sims, sorted(sims, reverse=True))
        self.assertTrue(all(s >= COVER_MIN_SIM_MOCK for s in sims))       # weaker ones dropped
        self.assertEqual(len(self.covers.query(self.covers.embed_bytes(self.cover_png(self.books[0])), k=5)), 5)

    def test_e3_not_an_image(self):
        for data in (b"plain text", b"\x89PNG\r\n\x1a\n broken", b""):
            with self.assertRaises(ValueError) as cm:
                self.ctx.catalog.search_by_cover(data)
            self.assertEqual(str(cm.exception), NOT_AN_IMAGE)

    def test_e4_non_cover_photo_is_no_match(self):
        for data in (make_face_photo("pat", 1, 0), make_face_photo(None, 0, 7)):
            self.assertEqual(self.ctx.catalog.search_by_cover(data), [])
        noise = Image.fromarray(np.random.default_rng(3).integers(0, 255, (180, 120, 3), dtype=np.uint8))
        buf = io.BytesIO()
        noise.save(buf, "JPEG")
        self.assertEqual(self.ctx.catalog.search_by_cover(buf.getvalue()), [])

    def test_e5_index_not_ready(self):
        self.covers.ready = False
        with self.assertRaises(ModelUnavailable):
            self.ctx.catalog.search_by_cover(self.cover_png(self.books[0]))

    def test_real_mode_without_openclip_falls_back_to_labelled_mock(self):
        emb = get_cover_embedder(dict(DEFAULTS, COVER_MODE="real"))
        self.assertIsInstance(emb, MockCoverEmbedder)                      # open_clip is not installed
        self.assertIn("MOCK", emb.mode_label)
        self.assertIn("OpenCLIP", emb.mode_label)
