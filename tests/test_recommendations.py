"""RecommendationEngine.personalized (SRS 4.10): UC-06, R4, deviation D-19."""
from bookorbit import rules
from tests.helpers import TempStoreCase


class RecommendationTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        b = self.add_book
        self.dragon1 = b(title="Dragon One", category="Fantasy", author="Ada Ash", keywords="dragons, magic")
        self.dragon2 = b(title="Dragon Two", category="Fantasy", author="Bram Bell", keywords="dragons, quest")
        self.wizard = b(title="Wizard Tale", category="Fantasy", author="Cora Cole", keywords="magic")
        self.ada2 = b(title="Ada's Mystery", category="Mystery", author="Ada Ash", keywords="clues")
        self.space = b(title="Space Freight", category="Science Fiction", author="Dan Dee", keywords="space",
                       weighted_avg=5.0, rating_count=4)
        self.popular = b(title="Popular Poems", category="Poetry", author="Eva Eve", keywords="verse",
                         browse_count=99)
        self.pat = self.add_user("pat", balance=100.0)
        self.uid = self.pat["user_id"]

    def buy(self, book):
        self.ctx.purchases.purchase(self.session_for(self.pat), book["book_id"])

    def view(self, book):
        self.ctx.catalog.get_details(book["book_id"], self.session_for(self.pat))

    def recs(self):
        return [b["title"] for b in self.ctx.recs.personalized(self.uid)]

    def test_r4_profile_weights_purchase_3_view_1(self):
        self.buy(self.dragon1)
        self.view(self.wizard)
        p = self.ctx.recs.build_profile(self.uid)
        self.assertEqual(p["cat:Fantasy"], rules.PROFILE_W_BUY + rules.PROFILE_W_VIEW)   # 3 + 1
        self.assertEqual(p["auth:Ada Ash"], 3)
        self.assertEqual((p["kw:dragons"], p["kw:magic"]), (3, 3 + 1))
        self.assertEqual(p["auth:Cora Cole"], 1)

    def test_r4_top_unowned_matches_best_first(self):
        self.buy(self.dragon1)              # Fantasy, Ada Ash, dragons, magic (3 points each)
        # Dragon Two: Fantasy 3 + dragons 3 = 6; Wizard Tale: Fantasy 3 + magic 3 = 6;
        # Ada's Mystery: author 3. Ties broken by title.
        self.assertEqual(self.recs(), ["Dragon Two", "Wizard Tale", "Ada's Mystery"])
        self.assertNotIn("Dragon One", self.recs())                       # owned books never recommended

    def test_purchase_outweighs_views(self):
        self.buy(self.space)                # Science Fiction / Dan Dee / space: 3 each
        self.view(self.ada2)                # Mystery / Ada Ash / clues: 1 each
        self.view(self.ada2)
        recs = self.ctx.recs.personalized(self.uid)
        # Ada's Mystery is now seen (2 views, still unowned): author 2 + cat 2 + kw 2 = 6
        self.assertEqual(recs[0]["title"], "Ada's Mystery")
        self.assertEqual(recs[1]["title"], "Dragon One")                 # author Ada Ash = 2

    def test_e1_no_history_shows_popular(self):
        session = self.session_for(self.pat)
        self.assertEqual(self.ctx.recs.personalized(self.uid), [])
        self.assertEqual(self.ctx.recs.home_books(session)[0], "Popular right now")

    def test_e2_fewer_than_three_matches_filled_with_popular(self):
        self.buy(self.space)                # nothing else is Science Fiction / Dan Dee / space
        recs = self.ctx.recs.personalized(self.uid)
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["title"], "Popular Poems")             # fill = top popular, unowned
        self.assertNotIn("Space Freight", [b["title"] for b in recs])

    def test_d19_unrelated_rated_book_is_not_a_match(self):
        # Space Freight is rated 5.0, so its tie-breaker score is 0.5 > 0; the pseudo-code
        # would recommend it to a Fantasy reader. D-19: only books matching the profile.
        self.buy(self.wizard)               # Fantasy / Cora Cole / magic
        # Dragon One: Fantasy 3 + magic 3 = 6; Dragon Two: Fantasy 3; nothing else matches.
        # The third slot is the popular fill (E2), not the unrelated 5-star Space Freight.
        self.assertEqual(self.recs(), ["Dragon One", "Dragon Two", "Popular Poems"])

    def test_e3_owns_every_book(self):
        self.ctx.wallet.deposit(self.session_for(self.pat), "500")
        for b in self.fs.load("books"):
            self.buy(b)
        self.assertEqual(self.ctx.recs.personalized(self.uid), [])
        self.assertEqual(self.ctx.recs.home_books(self.session_for(self.pat))[0], "Popular right now")

    def test_home_title_for_customer_with_history(self):
        self.view(self.dragon1)
        title, books = self.ctx.recs.home_books(self.session_for(self.pat))
        self.assertEqual(title, "Recommended for You")
        self.assertEqual(len(books), 3)

    def test_reasons(self):
        self.buy(self.dragon1)
        p = self.ctx.recs.build_profile(self.uid)
        self.assertEqual(self.ctx.recs.reasons(self.dragon2, p), ["category Fantasy", "keyword dragons"])
