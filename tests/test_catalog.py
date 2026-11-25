"""UC-03 popular books (R3), UC-04 browse/search, UC-05 details, R12/R13 ratings."""
from bookorbit import rules
from bookorbit.errors import ModelUnavailable, NotFound
from bookorbit.services.ratings import classify, weighted_average
from bookorbit.services.session import Session
from tests.helpers import TempStoreCase


class CatalogTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.add_book(title="Night Garden", author="Ada Moss", pub_year=1990, category="Fiction")
        self.add_book(title="Night", author="Bram Hale", pub_year=2001, category="Mystery",
                      keywords="detective, clues")
        self.add_book(title="The Night Garden Returns", author="Ada Moss", pub_year=2010, category="Fiction")
        self.add_book(title="Ocean Maps", author="Celia Night", pub_year=2020, category="Science")

    def titles(self, books):
        return [b["title"] for b in books]

    def test_title_ranking_exact_then_prefix_then_contains(self):      # UC-04 step 3
        self.assertEqual(self.titles(self.ctx.catalog.search("night", "title")),
                         ["Night", "Night Garden", "The Night Garden Returns"])

    def test_author_and_keyword_and_category(self):
        self.assertEqual(self.titles(self.ctx.catalog.search("ada moss", "author")),
                         ["Night Garden", "The Night Garden Returns"])
        self.assertEqual(self.titles(self.ctx.catalog.search("clues", "keyword")), ["Night"])
        self.assertEqual(self.titles(self.ctx.catalog.search("night", "title", category="Fiction")),
                         ["Night Garden", "The Night Garden Returns"])

    def test_year_range(self):
        self.assertEqual(len(self.ctx.catalog.search("1995-2015", "year")), 2)
        self.assertEqual(self.titles(self.ctx.catalog.search("2020", "year")), ["Ocean Maps"])

    def test_invalid_year_range(self):                                  # UC-04 E2
        for bad in ("2015-1995", "abc", "19x0"):
            with self.assertRaises(ValueError):
                self.ctx.catalog.search(bad, "year")

    def test_no_match(self):                                            # UC-04 E1
        self.assertEqual(self.ctx.catalog.search("zebra", "title"), [])

    def test_paging_12_per_page(self):                                   # UC-04 step 5
        for i in range(20):
            self.add_book(title=f"Filler {i:02d}")
        books = self.ctx.catalog.browse()
        self.assertEqual(len(self.ctx.catalog.page(books, 1)), rules.PAGE_SIZE)
        self.assertEqual(len(self.ctx.catalog.page(books, 2)), 24 - rules.PAGE_SIZE)

    def test_cover_search_disabled_without_model(self):                 # UC-04 E5 (STUB until Phase 3)
        with self.assertRaises(ModelUnavailable):
            self.ctx.catalog.search_by_cover(b"\x89PNG")

    def test_details_counts_browse_and_logs_event_for_customers_only(self):  # UC-05 step 3, R3, R4
        visitor = Session(self.fs)
        self.ctx.catalog.get_details("B-0001", visitor)
        self.assertEqual(self.fs.find("books", "book_id", "B-0001")["browse_count"], 1)
        self.assertEqual(self.fs.load("browse_history"), [])
        pat = self.add_user("pat")
        self.ctx.catalog.get_details("B-0001", self.session_for(pat))
        self.assertEqual(self.fs.find("books", "book_id", "B-0001")["browse_count"], 2)
        self.assertEqual(self.fs.load("browse_history")[0]["user_id"], pat["user_id"])

    def test_details_missing_book(self):                                # UC-05 E1
        with self.assertRaises(NotFound):
            self.ctx.catalog.get_details("B-9999", Session(self.fs))

    def test_reviews_published_only_newest_first(self):                 # UC-05 step 4
        self.fs.append("users", {"user_id": "U-0001", "full_name": "Ann"})
        base = {"book_id": "B-0001", "user_id": "U-0001", "rating": 4, "original_text": "x",
                "display_text": "x", "taboo_count": 0, "verified_buyer": False, "weight": 1.0}
        self.fs.append("reviews", dict(base, review_id="R-0001", status="PUBLISHED", timestamp="2026-11-01 10:00:00"))
        self.fs.append("reviews", dict(base, review_id="R-0002", status="BLOCKED", timestamp="2026-11-02 10:00:00"))
        self.fs.append("reviews", dict(base, review_id="R-0003", status="PUBLISHED", timestamp="2026-11-03 10:00:00"))
        rs = self.ctx.reviews.list_reviews("B-0001")
        self.assertEqual([r["review_id"] for r in rs], ["R-0003", "R-0001"])
        self.assertEqual(rs[0]["author"], "Ann")


class PopularTests(TempStoreCase):
    def test_popularity_formula_and_tie_breaks(self):                  # R3, UC-03 E3
        self.add_book(title="Browsed", browse_count=10, purchase_count=0)          # 10
        self.add_book(title="Bought", browse_count=1, purchase_count=3)            # 10, better rated
        self.add_book(title="Bought", browse_count=1, purchase_count=3, weighted_avg=4.5)
        self.add_book(title="Alpha", browse_count=0, purchase_count=4)             # 12
        self.add_book(title="Quiet", browse_count=2)
        top = self.ctx.recs.top_popular(3)
        self.assertEqual([(b["title"], b["weighted_avg"]) for b in top],
                         [("Alpha", 0.0), ("Bought", 4.5), ("Bought", 0.0)])

    def test_title_tie_break(self):
        self.add_book(title="Zeta", browse_count=5)
        self.add_book(title="Beta", browse_count=5)
        self.assertEqual([b["title"] for b in self.ctx.recs.top_popular(2)], ["Beta", "Zeta"])

    def test_fewer_than_three_and_empty(self):                          # UC-03 E1 / E2
        self.assertEqual(self.ctx.recs.top_popular(3), [])
        self.add_book(title="Only")
        self.assertEqual(len(self.ctx.recs.top_popular(3)), 1)

    def test_home_books_by_role(self):                                  # UC-03 / UC-06 E1 fallback
        self.add_book(title="A", browse_count=3)
        visitor = Session(self.fs)
        self.assertEqual(self.ctx.recs.home_books(visitor)[0], "Top 3 Most Popular")
        rc = Session(self.fs)
        rc.start({"user_id": "U-0002", "role": rules.RC, "status": rules.ACTIVE})
        self.assertEqual(self.ctx.recs.home_books(rc)[0], "Popular right now")


class RatingTests(TempStoreCase):
    def test_weighted_average(self):                                    # R12
        rs = [{"rating": 5, "weight": 2.0}, {"rating": 2, "weight": 1.0}]
        self.assertEqual(weighted_average(rs), 4.0)
        self.assertEqual(weighted_average([]), 0.0)

    def test_order_lists_need_more_than_three_ratings(self):            # R13
        self.assertEqual(classify(3, 4.9), rules.LIST_NONE)
        self.assertEqual(classify(4, 4.1), rules.LIST_TO_ORDER)
        self.assertEqual(classify(4, 4.0), rules.LIST_NONE)
        self.assertEqual(classify(4, 1.9), rules.LIST_NO_ORDER)
        self.assertEqual(classify(4, 2.0), rules.LIST_NONE)
