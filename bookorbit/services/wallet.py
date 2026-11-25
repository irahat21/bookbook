"""WalletService (SRS 4.11, UC-07, R7, R8).

Every change of balance goes through post_transaction(), so the ledger
(transactions.txt) always explains the balance: the last transaction's
balance_after equals users.balance.
"""
from dataclasses import dataclass

from bookorbit import clock, rules
from bookorbit.money import cents, parse_amount


@dataclass
class DepositResult:
    balance: float
    note: str = ""          # UC-07 step 5: "a Super-User can now reactivate your account"


class WalletService:
    def __init__(self, fs, status):
        self.fs = fs
        self.status = status

    def deposit(self, session, amount_text: str) -> DepositResult:
        """UC-07. Allowed in wallet-only mode (R8: suspended users can still deposit).
        ValueError("Enter a valid amount") for E1."""
        session.require(rules.RC, rules.VC, active=False)
        amount = parse_amount(amount_text)                  # not a number / > 2 decimals
        if amount <= 0 or amount > rules.MAX_DEPOSIT:
            raise ValueError("Enter a valid amount")
        txn = self.post_transaction(session.user["user_id"], rules.DEPOSIT, amount, None, "Add funds")
        session.refresh()
        note = ""
        if session.user["status"] == rules.SUSPENDED and txn["balance_after"] >= 0:
            note = "Your balance is now $0.00 or more: a Super-User can now reactivate your account (R8)."
        return DepositResult(txn["balance_after"], note)

    def get_balance(self, user_id: str) -> float:
        return self.fs.find("users", "user_id", user_id)["balance"]

    def get_ledger(self, user_id: str) -> list[dict]:
        """Every deposit, purchase and fine of the user, newest first."""
        txns = [t for t in self.fs.load("transactions") if t["user_id"] == user_id]
        return sorted(txns, key=lambda t: (t["timestamp"], t["txn_id"]), reverse=True)

    def post_transaction(self, user_id: str, type_: str, amount: float, book_id, note: str) -> dict:
        """Append a ledger entry and update the balance. amount is signed
        (+deposit, -purchase, -fine). Read and write happen under one lock."""
        with self.fs.lock:
            user = self.fs.find("users", "user_id", user_id)
            new_balance = cents(user["balance"] + amount)
            txn = {"txn_id": self.fs.next_id("transactions", "X"), "user_id": user_id, "type": type_,
                   "amount": cents(amount), "balance_after": new_balance, "book_id": book_id,
                   "note": note, "timestamp": clock.now()}
            self.fs.append("transactions", txn)
            self.fs.update("users", "user_id", user_id, {"balance": new_balance})
            return txn

    def charge_fine(self, user_id: str, book_id: str) -> dict:
        """R7: $1.00 fine; if the balance is now below $0 the account is SUSPENDED."""
        txn = self.post_transaction(user_id, rules.FINE, -rules.FINE_AMOUNT, book_id, "Insufficient funds")
        if txn["balance_after"] < 0:
            self.status.suspend(user_id, "negative balance")
        return txn
