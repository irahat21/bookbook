"""Book-text helpers (SRS 4.21 strip_gutenberg_header_footer / split_chapters) and the
seeded texts (ASSUMPTIONS A-11)."""
import unittest

import seed
from bookorbit.ai.texts import read_chapters, split_chapters, strip_gutenberg_header_footer


class TextHelperTests(unittest.TestCase):
    def test_strip_gutenberg_markers(self):
        raw = ("The Project Gutenberg eBook of X\nlicence...\n"
               "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nCHAPTER I\nHello.\n"
               "*** END OF THE PROJECT GUTENBERG EBOOK X ***\nmore licence")
        self.assertEqual(strip_gutenberg_header_footer(raw), "CHAPTER I\nHello.")

    def test_text_without_markers_is_kept(self):
        self.assertEqual(strip_gutenberg_header_footer("  plain text \n"), "plain text")

    def test_split_chapters_numbers_titles_and_drops_preface(self):
        text = "Title page\n\nCHAPTER 1: Start\nOne.\n\nChapter II.\nTwo.\nCHAPTER 3 The End\nThree."
        chapters = split_chapters(text)
        self.assertEqual([c[0] for c in chapters], [1, 2, 3])
        self.assertEqual(chapters[0][1:], ("Start", "One."))
        self.assertEqual(chapters[1][1], "Chapter 2")          # heading without a title
        self.assertEqual(chapters[2][1:], ("The End", "Three."))

    def test_no_headings_is_one_chapter(self):
        self.assertEqual(split_chapters("Just a poem."), [(1, "Full text", "Just a poem.")])
        self.assertEqual(split_chapters("   "), [])

    def test_seeded_texts_have_three_chapters_of_400_to_600_words(self):
        # Phase 3 plan: 3 chapters of ~400-600 words, so each chapter gives the RAG index
        # 2-3 chunks of 250 words (SRS 4.21 CHUNK_WORDS / OVERLAP).
        for title, name in seed.BOOK_TEXTS.items():
            chapters = read_chapters(seed.SEED_TEXTS / name)
            self.assertEqual(len(chapters), 3, title)
            for n, _t, body in chapters:
                self.assertTrue(400 <= len(body.split()) <= 600, f"{title} chapter {n}: {len(body.split())} words")


if __name__ == "__main__":
    unittest.main()
