"""PurchaseService (SRS 4.12) - Buy Now (UC-08) with the VIP discount (UC-09).

There is no cart and no stock (ASSUMPTIONS C-02, C-03): one book is bought at a
time, paid from the wallet, and a customer can own each book once.
Rules: R5 promotion, R6 VIP price, R7 fine + suspension.
"""
from dataclasses import dataclass

from bookorbit import clock, rules
from bookorbit.errors import PurchaseError
from bookorbit.money import cents


@dataclass
class Price:
    list: float
    discount: float
    paid: float


@dataclass
class Quote:
    """What the Buy Now confirmation dialog shows (UC-08 step 2, decision A-20)."""
    price: Price
    balance: float

    @property
    def insufficient(self) -> bool:
        return self.balance < self.price.paid

    @property
    def fine_would_suspend(self) -> bool:
        """R7: the $1.00 fine would take the balance below $0."""
        return self.insufficient and cents(self.balance - rules.FINE_AMOUNT) < 0


@dataclass
class Receipt:
    title: str
    list_price: float
    discount: float
    paid: float
    balance: float
    promoted: bool


class PurchaseService:
    def __init__(self, fs, wallet, status):
        self.fs = fs
        self.wallet = wallet
        self.status = status

    def final_price(self, user: dict, book: dict) -> Price:
        """UC-09 / R6. The role is re-read from users.txt: it may have changed since
        sign-in (promotion, or demotion after a blocked review - UC-09 E1)."""
        u = self.fs.find("users", "user_id", user["user_id"])
        discount = cents(book["price"] * rules.VIP_RATE) if u["role"] == rules.VC else 0.0
        return Price(book["price"], discount, cents(book["price"] - discount))

    def quote(self, session, book_id: str) -> Quote:
        session.require(rules.RC, rules.VC)
        book = self._book(book_id)
        return Quote(self.final_price(session.user, book), session.user["balance"])

    def already_owned(self, user_id: str, book_id: str) -> bool:
        return any(p["user_id"] == user_id and p["book_id"] == book_id for p in self.fs.load("purchases"))

    def purchase(self, session, book_id: str) -> Receipt:
        """UC-08. Raises PermissionError (E4: suspended / not a customer) or PurchaseError
        (E1 insufficient funds + fine, E2 suspended by the fine, E3 already owned)."""
        session.require(rules.RC, rules.VC)                     # re-reads role and status
        uid = session.user["user_id"]
        with self.fs.lock:                                      # balance check + payment as one step
            book = self._book(book_id)
            if self.already_owned(uid, book_id):
                raise PurchaseError("You already own this book")                       # E3
            price = self.final_price(session.user, book)
            user = self.fs.find("users", "user_id", uid)
            if user["balance"] < price.paid:                                            # E1 (R7)
                fine = self.wallet.charge_fine(uid, book_id)
                session.refresh()
                msg = (f"Insufficient funds: you need ${price.paid:.2f} but have ${user['balance']:.2f}. "
                       f"A ${rules.FINE_AMOUNT:.2f} fine was charged (R7); balance now "
                       f"${fine['balance_after']:.2f}.")
                if session.wallet_only:                                                 # E2
                    msg += " Your balance is below $0, so your account is SUSPENDED."
                raise PurchaseError(msg, suspended=session.wallet_only, fined=True)

            note = book["title"] + (" (VIP -10%)" if price.discount > 0 else "")      # UC-09 step 4
            txn = self.wallet.post_transaction(uid, rules.PURCHASE, -price.paid, book_id, note)
            self.fs.append("purchases", {
                "purchase_id": self.fs.next_id("purchases", "P"), "user_id": uid, "book_id": book_id,
                "txn_id": txn["txn_id"], "list_price": price.list, "discount": price.discount,
                "price_paid": price.paid, "timestamp": clock.now()})
            u = self.fs.find("users", "user_id", uid)
            self.fs.update("users", "user_id", uid, {
                "purchase_count": u["purchase_count"] + 1,
                "total_spent": cents(u["total_spent"] + price.paid),
                "promo_purchases": u["promo_purchases"] + 1,
                "promo_spent": cents(u["promo_spent"] + price.paid)})
            self.fs.update("books", "book_id", book_id, {"purchase_count": book["purchase_count"] + 1})
            # R5 is checked AFTER this purchase is paid, so the discount starts with the
            # next one (R6, UC-09 E2).
            promoted = self.status.evaluate_promotion(uid)
        session.refresh()
        return Receipt(book["title"], price.list, price.discount, price.paid, txn["balance_after"], promoted)

    def list_orders(self, user_id: str) -> list[dict]:
        """My Orders (ASSUMPTIONS A-14): the user's purchases with book titles, newest first."""
        titles = {b["book_id"]: b["title"] for b in self.fs.load("books")}
        orders = [dict(p, title=titles.get(p["book_id"], "(book removed)"))
                  for p in self.fs.load("purchases") if p["user_id"] == user_id]
        return sorted(orders, key=lambda p: (p["timestamp"], p["purchase_id"]), reverse=True)

    def _book(self, book_id: str) -> dict:
        book = self.fs.find("books", "book_id", book_id)
        if book is None:
            raise PurchaseError("Book unavailable")
        return book
