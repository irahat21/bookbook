"""WarningService (SRS 4.16, UC-11, R10).

A blocked review gives its author one warning, then R10 is applied:
  - VC: demoted to RC at once (promotion counters restart at 0);
  - RC: more than 2 warnings (i.e. the 3rd) -> SUSPENDED.
The VC check comes first, exactly as in the SRS pseudo-code, so a VC who
already had 2 warnings is only demoted by the 3rd (see ASSUMPTIONS F-24).
"""
from bookorbit import clock, rules


class WarningService:
    def __init__(self, fs, status):
        self.fs = fs
        self.status = status

    def issue(self, user_id: str, review_id: str, reason: str) -> str:
        """Returns the consequence: "", "DEMOTED" or "SUSPENDED"."""
        with self.fs.lock:
            self.fs.append("warnings", {"warning_id": self.fs.next_id("warnings", "W"), "user_id": user_id,
                                        "review_id": review_id, "reason": reason, "timestamp": clock.now()})
            u = self.fs.find("users", "user_id", user_id)
            self.fs.update("users", "user_id", user_id, {"warnings": u["warnings"] + 1})
            return self.apply_consequences(user_id)

    def apply_consequences(self, user_id: str) -> str:
        u = self.fs.find("users", "user_id", user_id)
        if u["role"] == rules.VC:
            self.status.demote(user_id, "blocked comment")
            return rules.DEMOTED
        if u["role"] == rules.RC and u["warnings"] > rules.RC_SUSPEND_ABOVE:
            self.status.suspend(user_id, f"{u['warnings']} warnings")
            return rules.SUSPENDED
        return ""

    def get_warnings(self, user_id: str) -> list[dict]:
        ws = [w for w in self.fs.load("warnings") if w["user_id"] == user_id]
        return sorted(ws, key=lambda w: (w["timestamp"], w["warning_id"]), reverse=True)
