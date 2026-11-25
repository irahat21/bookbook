"""UC-07 wallet, UC-08 Buy Now, UC-09 VIP discount; rules R5, R6, R7, R8."""
from bookorbit import rules
from bookorbit.errors import PurchaseError, ReopenError
from bookorbit.money import cents, parse_amount
from tests.helpers import TempStoreCase


class MoneyTests(TempStoreCase):
    def test_round_half_up_to_the_cent(self):                         # A-19
        self.assertEqual(cents(1.245), 1.25)
        self.assertEqual(cents(2.675), 2.68)      # round(2.675, 2) == 2.67
        self.assertEqual(cents(0.125), 0.13)      # round(0.125, 2) == 0.12 (banker's rounding)

    def test_parse_amount(self):
        self.assertEqual(parse_amount(" $1,000.50 "), 1000.5)
        for bad in ("abc", "", "1.234", "nan", "inf"):
            with self.assertRaises(ValueError, msg=bad):
                parse_amount(bad)


class WalletTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.pat = self.add_user("pat")
        self.s = self.session_for(self.pat)

    def test_deposit_posts_ledger_entry(self):                        # UC-07 steps 2-4
        res = self.ctx.wallet.deposit(self.s, "25.50")
        self.assertEqual(res.balance, 25.5)
        self.assertEqual(self.user(self.pat)["balance"], 25.5)
        [txn] = self.ctx.wallet.get_ledger(self.pat["user_id"])
        self.assertEqual((txn["type"], txn["amount"], txn["balance_after"]), (rules.DEPOSIT, 25.5, 25.5))

    def test_invalid_amounts_change_nothing(self):                    # UC-07 E1
        for bad in ("0", "-5", "abc", "10.001", "10000.01"):
            with self.assertRaises(ValueError, msg=bad):
                self.ctx.wallet.deposit(self.s, bad)
        self.ctx.wallet.deposit(self.s, "10000")                      # the maximum is allowed
        self.assertEqual(len(self.fs.load("transactions")), 1)

    def test_suspended_user_can_deposit_and_gets_note(self):          # R8, UC-07 step 5
        sid = self.add_user("sid", status=rules.SUSPENDED, balance=-1.0)
        s = self.session_for(sid)
        self.assertTrue(s.wallet_only)
        res = self.ctx.wallet.deposit(s, "0.50")
        self.assertEqual(res.balance, -0.5)
        self.assertEqual(res.note, "")                                # still below $0
        res = self.ctx.wallet.deposit(s, "0.50")
        self.assertIn("Super-User can now reactivate", res.note)
        self.assertEqual(self.user(sid)["status"], rules.SUSPENDED)   # only an SU reopens

    def test_super_user_cannot_deposit(self):
        su = self.add_user("sue", role=rules.SU)
        with self.assertRaises(PermissionError):
            self.ctx.wallet.deposit(self.session_for(su), "5")


class PurchaseTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.books = [self.add_book(title=f"Book {i}", price=10.0) for i in range(6)]
        self.pricey = self.add_book(title="Pricey", price=150.0)

    def buy(self, user, book):
        return self.ctx.purchases.purchase(self.session_for(user), book["book_id"])

    def test_purchase_updates_everything(self):                       # UC-08 step 4
        pat = self.add_user("pat", balance=50.0)
        r = self.buy(pat, self.books[0])
        self.assertEqual((r.list_price, r.discount, r.paid, r.balance, r.promoted), (10.0, 0.0, 10.0, 40.0, False))
        u = self.user(pat)
        self.assertEqual((u["balance"], u["purchase_count"], u["total_spent"], u["promo_purchases"],
                          u["promo_spent"]), (40.0, 1, 10.0, 1, 10.0))
        self.assertEqual(self.fs.find("books", "book_id", self.books[0]["book_id"])["purchase_count"], 1)
        [p] = self.fs.load("purchases")
        [txn] = self.fs.load("transactions")
        self.assertEqual(p["txn_id"], txn["txn_id"])
        self.assertEqual((txn["type"], txn["amount"]), (rules.PURCHASE, -10.0))

    def test_already_owned(self):                                     # UC-08 E3
        pat = self.add_user("pat", balance=50.0)
        self.buy(pat, self.books[0])
        with self.assertRaisesRegex(PurchaseError, "already own"):
            self.buy(pat, self.books[0])
        self.assertEqual(self.user(pat)["balance"], 40.0)             # no fine for E3

    def test_r5_promotion_on_fourth_purchase(self):                   # R5: purchases > 3
        pat = self.add_user("pat", balance=100.0)
        results = [self.buy(pat, b) for b in self.books[:4]]
        self.assertEqual([r.promoted for r in results], [False, False, False, True])
        self.assertEqual(self.user(pat)["role"], rules.VC)
        [change] = self.fs.load("status_changes")
        self.assertEqual((change["from_role"], change["to_role"], change["reason"]), (rules.RC, rules.VC, "promotion"))

    def test_r5_promotion_by_spending_over_200(self):                 # R5: spent > $200
        pat = self.add_user("pat", balance=500.0, promo_spent=45.0)
        self.assertFalse(self.buy(pat, self.books[0]).promoted)       # spent 55.00, 1 purchase
        self.assertTrue(self.buy(pat, self.pricey).promoted)          # spent 205.00 > 200, only 2 purchases
        self.assertEqual(self.user(pat)["role"], rules.VC)

    def test_r5_exactly_200_is_not_enough(self):                      # R5 uses ">" not ">="
        pat = self.add_user("pat", balance=500.0, promo_spent=40.0)
        r1 = self.buy(pat, self.books[0])                             # 50
        r2 = self.buy(pat, self.pricey)                               # 200 exactly
        self.assertEqual((r1.promoted, r2.promoted), (False, False))
        self.assertEqual(self.user(pat)["role"], rules.RC)
        self.assertTrue(self.buy(pat, self.books[1]).promoted)        # 210 > 200

    def test_r6_vip_discount_and_label(self):                         # R6, UC-09
        vic = self.add_user("vic", role=rules.VC, balance=100.0)
        book = self.add_book(title="Odd price", price=12.45)
        r = self.buy(vic, book)
        self.assertEqual((r.list_price, r.discount, r.paid), (12.45, 1.25, 11.2))   # 1.245 -> 1.25 (A-19)
        [txn] = self.fs.load("transactions")
        self.assertTrue(txn["note"].endswith("(VIP -10%)"))
        [p] = self.fs.load("purchases")
        self.assertEqual((p["list_price"], p["discount"], p["price_paid"]), (12.45, 1.25, 11.2))

    def test_r6_discount_starts_after_promotion(self):                # UC-09 E2
        pat = self.add_user("pat", balance=100.0)
        paid = [self.buy(pat, b).paid for b in self.books[:5]]
        self.assertEqual(paid, [10.0, 10.0, 10.0, 10.0, 9.0])         # promoted by the 4th, discount on the 5th

    def test_r6_price_follows_current_role(self):                     # UC-09 E1: demoted after opening the page
        vic = self.add_user("vic", role=rules.VC, balance=100.0)
        s = self.session_for(vic)
        self.assertEqual(self.ctx.purchases.quote(s, self.books[0]["book_id"]).price.paid, 9.0)
        self.ctx.status.demote(vic["user_id"], "blocked comment")
        self.assertEqual(self.ctx.purchases.quote(s, self.books[0]["book_id"]).price.paid, 10.0)
        self.assertEqual(self.ctx.purchases.purchase(s, self.books[0]["book_id"]).paid, 10.0)

    def test_r7_insufficient_funds_fine_without_suspension(self):     # R7, UC-08 E1
        pat = self.add_user("pat", balance=5.0)
        with self.assertRaises(PurchaseError) as cm:
            self.buy(pat, self.books[0])
        self.assertTrue(cm.exception.fined)
        self.assertFalse(cm.exception.suspended)
        u = self.user(pat)
        self.assertEqual((u["balance"], u["status"], u["purchase_count"]), (4.0, rules.ACTIVE, 0))
        [txn] = self.fs.load("transactions")
        self.assertEqual((txn["type"], txn["amount"], txn["balance_after"]), (rules.FINE, -1.0, 4.0))
        self.assertEqual(self.fs.load("purchases"), [])

    def test_r7_fine_below_zero_suspends(self):                       # R7, UC-08 E2 (FLAG F-18)
        pat = self.add_user("pat", balance=0.0)
        s = self.session_for(pat)
        with self.assertRaises(PurchaseError) as cm:
            self.ctx.purchases.purchase(s, self.books[0]["book_id"])
        self.assertTrue(cm.exception.suspended)
        self.assertTrue(s.wallet_only)                                # switched to wallet-only mode
        u = self.user(pat)
        self.assertEqual((u["balance"], u["status"]), (-1.0, rules.SUSPENDED))
        [change] = self.fs.load("status_changes")
        self.assertEqual((change["to_status"], change["reason"]), (rules.SUSPENDED, "negative balance"))

    def test_quote_warns_before_fine(self):                           # decision A-20
        pat = self.add_user("pat", balance=0.5)
        q = self.ctx.purchases.quote(self.session_for(pat), self.books[0]["book_id"])
        self.assertTrue(q.insufficient)
        self.assertTrue(q.fine_would_suspend)
        rich = self.add_user("rich", balance=50.0)
        q = self.ctx.purchases.quote(self.session_for(rich), self.books[0]["book_id"])
        self.assertFalse(q.insufficient)

    def test_r8_suspended_cannot_buy(self):                           # R8, UC-08 E4
        sid = self.add_user("sid", status=rules.SUSPENDED, balance=100.0)
        with self.assertRaises(PermissionError):
            self.buy(sid, self.books[0])
        self.assertEqual(self.fs.load("transactions"), [])

    def test_visitor_and_su_cannot_buy(self):
        from bookorbit.services.session import Session
        with self.assertRaises(PermissionError):
            self.ctx.purchases.purchase(Session(self.fs), self.books[0]["book_id"])
        su = self.add_user("sue", role=rules.SU, balance=100.0)
        with self.assertRaises(PermissionError):
            self.buy(su, self.books[0])

    def test_ledger_explains_balance(self):                           # SRS 4.11
        pat = self.add_user("pat")
        s = self.session_for(pat)
        self.ctx.wallet.deposit(s, "15")
        self.buy(pat, self.books[0])
        with self.assertRaises(PurchaseError):
            self.buy(pat, self.books[1])                              # 5.00 < 10.00 -> fine
        ledger = self.ctx.wallet.get_ledger(pat["user_id"])
        self.assertEqual(cents(sum(t["amount"] for t in ledger)), self.user(pat)["balance"])
        self.assertEqual(ledger[0]["balance_after"], 4.0)             # newest first

    def test_details_page_shows_vip_price_and_owned(self):            # UC-05 step 5 (M-04 removed)
        vic = self.add_user("vic", role=rules.VC, balance=100.0)
        s = self.session_for(vic)
        d = self.ctx.catalog.get_details(self.books[0]["book_id"], s)
        self.assertEqual((d["display_price"], d["vip_discount"], d["owned"]), (9.0, 1.0, False))
        self.buy(vic, self.books[0])
        self.assertTrue(self.ctx.catalog.get_details(self.books[0]["book_id"], s)["owned"])


class StatusManagerTests(TempStoreCase):
    def test_r8_reopen_needs_non_negative_balance_and_resets_warnings(self):   # R8 (UC-17 in Phase 4)
        sid = self.add_user("sid", status=rules.SUSPENDED, balance=-1.0, warnings=3)
        with self.assertRaisesRegex(ReopenError, r"deposit at least \$1.00"):
            self.ctx.status.reopen("U-0001", sid["user_id"])
        self.fs.update("users", "user_id", sid["user_id"], {"balance": 0.0})
        u = self.ctx.status.reopen("U-0001", sid["user_id"])
        self.assertEqual((u["status"], u["warnings"]), (rules.ACTIVE, 0))
        with self.assertRaisesRegex(ReopenError, "not suspended"):
            self.ctx.status.reopen("U-0001", sid["user_id"])

    def test_promotion_needs_active_rc(self):
        sid = self.add_user("sid", status=rules.SUSPENDED, promo_purchases=9)
        self.assertFalse(self.ctx.status.evaluate_promotion(sid["user_id"]))
