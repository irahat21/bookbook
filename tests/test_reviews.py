"""UC-10 Submit Book Reviews, UC-11 Receive Review Warnings; rules R9-R13.
Includes the six prototype tests listed in SRS Table 13 (Section 5.2)."""
from bookorbit import rules
from bookorbit.services.session import Session
from tests.helpers import TempStoreCase

CLEAN = "A lovely, thoughtful book."
FOUR_TABOO = "Dumb, STUPID and lame, with a darn ending."      # 4 taboo words, mixed case


class ReviewTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.taboo("dumb", "stupid", "lame", "darn", "ass")
        self.book = self.add_book(title="Dune-ish", price=14.99)

    def submit(self, user, text=CLEAN, rating=4, book=None):
        return self.ctx.reviews.submit(self.session_for(user), (book or self.book)["book_id"], rating, text)

    # ---- R9 moderation
    def test_mask_up_to_three(self):                                  # SRS Table 13, R9
        pat = self.add_user("pat")
        res = self.submit(pat, "Dumb start, STUPID middle, lame end.")
        self.assertEqual(res.status, rules.PUBLISHED)
        self.assertEqual(res.review["display_text"], "**** start, ****** middle, **** end.")
        self.assertEqual(res.review["taboo_count"], 3)
        self.assertIn("3 words masked", res.message)
        self.assertEqual(res.review["original_text"], "Dumb start, STUPID middle, lame end.")

    def test_whole_words_only(self):                                  # R9: 'class' does not match 'ass'
        pat = self.add_user("pat")
        res = self.submit(pat, "A classic class, no dumbbells.")
        self.assertEqual((res.review["taboo_count"], res.review["display_text"]),
                         (0, "A classic class, no dumbbells."))

    def test_four_taboo_words_blocked_and_never_listed(self):         # R9, UC-10 E2
        pat = self.add_user("pat")
        res = self.submit(pat, FOUR_TABOO)
        self.assertEqual(res.status, rules.BLOCKED)
        self.assertEqual(res.review["display_text"], "")
        self.assertEqual(self.ctx.reviews.list_reviews(self.book["book_id"]), [])
        self.assertEqual(self.fs.find("books", "book_id", self.book["book_id"])["rating_count"], 0)
        [w] = self.fs.load("warnings")
        self.assertEqual(w["review_id"], res.review["review_id"])

    # ---- R10 warnings
    def test_rc_first_and_second_warning_no_status_change(self):      # UC-11 E3
        pat = self.add_user("pat")
        res = self.submit(pat, FOUR_TABOO)
        self.assertEqual(res.consequence, "")
        self.assertIn("warning #1", res.message)
        self.assertIn("2 more warnings", res.message)
        res = self.submit(pat, FOUR_TABOO)
        self.assertIn("1 more warning ", res.message)
        u = self.user(pat)
        self.assertEqual((u["warnings"], u["status"]), (2, rules.ACTIVE))

    def test_block_and_suspend_rc_on_third_warning(self):             # SRS Table 13, R10, UC-11 E2
        evan = self.add_user("evan", warnings=2)
        s = self.session_for(evan)
        res = self.ctx.reviews.submit(s, self.book["book_id"], 1, FOUR_TABOO)
        self.assertEqual(res.consequence, rules.SUSPENDED)
        self.assertTrue(s.wallet_only)
        u = self.user(evan)
        self.assertEqual((u["warnings"], u["status"]), (3, rules.SUSPENDED))
        [c] = self.fs.load("status_changes")
        self.assertEqual((c["to_status"], c["reason"]), (rules.SUSPENDED, "3 warnings"))

    def test_vip_demoted_after_one_blocked_comment(self):             # SRS Table 13, R10, UC-11 E1
        selina = self.add_user("selina", role=rules.VC, promo_purchases=8, promo_spent=214.5)
        res = self.submit(selina, FOUR_TABOO)
        self.assertEqual(res.consequence, rules.DEMOTED)
        u = self.user(selina)
        self.assertEqual((u["role"], u["promo_purchases"], u["promo_spent"], u["warnings"]), (rules.RC, 0, 0.0, 1))
        s = self.session_for(selina)                                   # price drops the discount at once
        self.assertEqual(self.ctx.purchases.quote(s, self.book["book_id"]).price.paid, 14.99)

    def test_vip_with_two_warnings_only_demoted(self):                # F-24: SRS order kept, flagged
        vic = self.add_user("vic", role=rules.VC, warnings=2)
        res = self.submit(vic, FOUR_TABOO)
        self.assertEqual(res.consequence, rules.DEMOTED)
        self.assertEqual(self.user(vic)["status"], rules.ACTIVE)       # 3 warnings but not suspended
        res = self.submit(vic, FOUR_TABOO)                             # next block as RC -> suspended
        self.assertEqual(res.consequence, rules.SUSPENDED)

    # ---- R8 / R11 who may review
    def test_suspended_user_cannot_review(self):                      # SRS Table 13, R8, UC-10 E3
        sid = self.add_user("sid", status=rules.SUSPENDED)
        with self.assertRaises(PermissionError):
            self.submit(sid)
        self.assertEqual(self.fs.load("reviews"), [])

    def test_r11_only_customers_review(self):                         # R11
        with self.assertRaises(PermissionError):
            self.ctx.reviews.submit(Session(self.fs), self.book["book_id"], 5, CLEAN)
        su = self.add_user("sue", role=rules.SU)
        with self.assertRaises(PermissionError):
            self.submit(su)

    # ---- validation and the one-review rule
    def test_validation_stores_nothing(self):                         # UC-10 E1
        pat = self.add_user("pat")
        for rating, text in ((0, CLEAN), (6, CLEAN), (None, CLEAN), (3, "   "), (3, "x" * 1001)):
            with self.assertRaises(ValueError):
                self.submit(pat, text, rating)
        self.submit(pat, "x" * 1000, 3)                                # 1000 is allowed
        self.assertEqual(len(self.fs.load("reviews")), 1)

    def test_one_published_review_per_book(self):                     # A-09
        pat = self.add_user("pat")
        self.submit(pat)
        with self.assertRaisesRegex(ValueError, "already reviewed"):
            self.submit(pat, "Second thoughts.")
        other = self.add_book(title="Other")
        self.assertEqual(self.submit(pat, book=other).status, rules.PUBLISHED)

    def test_blocked_review_does_not_use_up_the_review(self):         # A-21
        pat = self.add_user("pat")
        self.assertEqual(self.submit(pat, FOUR_TABOO).status, rules.BLOCKED)
        self.assertEqual(self.submit(pat, CLEAN).status, rules.PUBLISHED)

    # ---- R12 / R13 ratings
    def test_weighted_average_and_to_order(self):                     # SRS Table 13, R12, R13
        buyer = self.add_user("buyer", balance=50.0)
        self.ctx.purchases.purchase(self.session_for(buyer), self.book["book_id"])
        for i, r in enumerate((5, 4, 4)):
            self.submit(self.add_user(f"u{i}"), rating=r)
        b = self.fs.find("books", "book_id", self.book["book_id"])
        self.assertEqual((b["rating_count"], b["list_status"]), (3, rules.LIST_NONE))  # needs > 3 ratings
        res = self.submit(buyer, rating=5)
        self.assertTrue(res.review["verified_buyer"])
        self.assertEqual(res.review["weight"], 2.0)
        b = self.fs.find("books", "book_id", self.book["book_id"])
        # (5 + 4 + 4 + 5x2) / (1 + 1 + 1 + 2) = 23 / 5 = 4.6
        self.assertEqual((b["rating_count"], b["weighted_avg"], b["list_status"]), (4, 4.6, rules.LIST_TO_ORDER))

    def test_no_order(self):                                          # SRS Table 13, R13
        for i, r in enumerate((1, 2, 1, 2)):
            self.submit(self.add_user(f"u{i}"), rating=r)
        b = self.fs.find("books", "book_id", self.book["book_id"])
        self.assertEqual((b["weighted_avg"], b["list_status"]), (1.5, rules.LIST_NO_ORDER))

    def test_my_reviews_and_warnings_lists(self):                     # A-14, UC-11 step 3
        pat = self.add_user("pat")
        self.submit(pat, FOUR_TABOO)
        self.submit(pat, CLEAN)
        mine = self.ctx.reviews.list_user_reviews(pat["user_id"])
        self.assertEqual(sorted(r["status"] for r in mine), [rules.BLOCKED, rules.PUBLISHED])
        self.assertEqual(len(self.ctx.warnings.get_warnings(pat["user_id"])), 1)
