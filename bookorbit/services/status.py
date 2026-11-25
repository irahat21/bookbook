"""StatusManager (SRS 4.13) - the ONLY class that changes a user's role or status.

R5 promotion, R7/R10 suspension, R10 demotion and R8 reopening all come through
here, and every change is written to status_changes.txt, so the file is a full
history of each account (STATUS_CHANGE in the E-R diagram).
"""
from bookorbit import clock, rules
from bookorbit.errors import ReopenError
from bookorbit.money import cents


class StatusManager:
    def __init__(self, fs):
        self.fs = fs

    def evaluate_promotion(self, user_id: str) -> bool:
        """R5: an ACTIVE RC with more than 3 purchases, or more than $200 spent, since
        joining or the last demotion becomes VC right after that purchase.
        Returns True only if the user was promoted by this call."""
        with self.fs.lock:
            u = self.fs.find("users", "user_id", user_id)
            if (u["role"] == rules.RC and u["status"] == rules.ACTIVE
                    and (u["promo_purchases"] > rules.PROMO_PURCHASES
                         or u["promo_spent"] > rules.PROMO_SPENT)):
                self.log_change(u, rules.VC, u["status"], "promotion")
                self.fs.update("users", "user_id", user_id, {"role": rules.VC})
                return True
            return False

    def demote(self, user_id: str, reason: str) -> dict:
        """R10: VC -> RC; the promotion counters restart at 0 (UC-11 E1)."""
        with self.fs.lock:
            u = self.fs.find("users", "user_id", user_id)
            if u["role"] != rules.VC:
                return u
            self.log_change(u, rules.RC, u["status"], reason)
            return self.fs.update("users", "user_id", user_id,
                                  {"role": rules.RC, "promo_purchases": 0, "promo_spent": 0.0})

    def suspend(self, user_id: str, reason: str) -> dict:
        """R7 (negative balance) and R10 (3rd warning of an RC)."""
        with self.fs.lock:
            u = self.fs.find("users", "user_id", user_id)
            if u["status"] == rules.SUSPENDED:
                return u
            self.log_change(u, u["role"], rules.SUSPENDED, reason)
            return self.fs.update("users", "user_id", user_id, {"status": rules.SUSPENDED})

    @staticmethod
    def can_reopen(user: dict) -> tuple[bool, str]:
        """R8: only a suspended account with a balance >= $0 can be reopened."""
        if user["status"] != rules.SUSPENDED:
            return False, "Account is not suspended"
        if user["balance"] < 0:
            return False, f"Customer must deposit at least ${cents(-user['balance']):.2f}"
        return True, ""

    def reopen(self, su_id: str, user_id: str) -> dict:
        """R8: back to ACTIVE with warnings reset to 0. The Super-User screen that
        calls this (UC-17, with its ADMIN_ACTION log entry) arrives in Phase 4."""
        with self.fs.lock:
            u = self.fs.find("users", "user_id", user_id)
            ok, why = self.can_reopen(u)
            if not ok:
                raise ReopenError(why)
            self.log_change(u, u["role"], rules.ACTIVE, f"reopened by {su_id}")
            return self.fs.update("users", "user_id", user_id, {"status": rules.ACTIVE, "warnings": 0})

    def log_change(self, user: dict, to_role: str, to_status: str, reason: str) -> None:
        self.fs.append("status_changes", {
            "change_id": self.fs.next_id("status_changes", "SC"), "user_id": user["user_id"],
            "from_role": user["role"], "to_role": to_role, "from_status": user["status"],
            "to_status": to_status, "reason": reason, "timestamp": clock.now()})
