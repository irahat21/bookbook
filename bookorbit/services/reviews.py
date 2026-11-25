"""ReviewService (SRS 4.14) - submit (UC-10) and list reviews (UC-05).

Flow of submit(): validate -> moderate (R9) -> store PUBLISHED with weight 2.0
for verified buyers else 1.0 (R12) -> recalculate rating and order list (R12,
R13); or store BLOCKED -> WarningService (UC-11, R10).
One PUBLISHED review per customer per book (ASSUMPTIONS A-09, A-21): a blocked
review does not use up that one review, so the customer may try again.
"""
from dataclasses import dataclass

from bookorbit import clock, rules


@dataclass
class SubmitResult:
    status: str          # PUBLISHED or BLOCKED
    message: str
    review: dict
    consequence: str     # "", "DEMOTED" or "SUSPENDED" (only when BLOCKED)


class ReviewService:
    def __init__(self, fs, moderation=None, warnings=None, ratings=None, purchases=None):
        self.fs = fs
        self.moderation = moderation
        self.warnings = warnings
        self.ratings = ratings
        self.purchases = purchases

    def submit(self, session, book_id: str, rating, text: str) -> SubmitResult:
        """PermissionError if not an ACTIVE RC/VC (R8, R11, UC-10 E3);
        ValueError for E1 and for a second review of the same book."""
        session.require(rules.RC, rules.VC)
        if rating not in (1, 2, 3, 4, 5):
            raise ValueError("Choose a rating from 1 to 5 stars")
        text = (text or "").strip()
        if not text or len(text) > rules.REVIEW_MAX_CHARS:
            raise ValueError(f"Comment must be 1-{rules.REVIEW_MAX_CHARS} characters")
        uid = session.user["user_id"]
        if self.fs.find("books", "book_id", book_id) is None:
            raise ValueError("Book unavailable")
        if self.user_review(uid, book_id):
            raise ValueError("You have already reviewed this book")                   # A-09

        mod = self.moderation.moderate(text)
        verified = self.is_verified_buyer(uid, book_id)
        review = self.fs.append("reviews", {
            "review_id": self.fs.next_id("reviews", "R"), "book_id": book_id, "user_id": uid,
            "rating": rating, "original_text": text, "display_text": mod.display_text,
            "taboo_count": mod.count, "status": mod.status, "verified_buyer": verified,
            "weight": rules.W_VERIFIED if verified else rules.W_OTHER, "timestamp": clock.now()})

        if mod.status == rules.BLOCKED:                                                 # E2 -> UC-11
            consequence = self.warnings.issue(uid, review["review_id"], "blocked comment")
            session.refresh()
            return SubmitResult(rules.BLOCKED, self.warning_message(session.user, mod.count, consequence),
                                review, consequence)
        self.ratings.recalculate(book_id)                                               # R12, R13
        return SubmitResult(rules.PUBLISHED, "Review published" + self.masked_note(mod.count), review, "")

    @staticmethod
    def masked_note(count: int) -> str:
        if count == 0:
            return "."
        return f" ({count} word{'s' if count != 1 else ''} masked)."

    @staticmethod
    def warning_message(user: dict, count: int, consequence: str) -> str:
        """UC-11 step 3: the warning number and any status change."""
        n = user["warnings"]
        msg = (f"Your review was blocked: it contains {count} taboo words (more than "
               f"{rules.TABOO_BLOCK_ABOVE} are not allowed, R9). This is warning #{n}.")
        if consequence == rules.DEMOTED:                                                # E1
            msg += " As a VIP, one blocked review costs your VIP status: you are now a Registered Customer."
        elif consequence == rules.SUSPENDED:                                            # E2
            msg += " Your account is now SUSPENDED (more than 2 warnings, R10)."
        else:                                                                           # E3
            left = rules.RC_SUSPEND_ABOVE + 1 - n
            msg += f" {left} more warning{'s' if left != 1 else ''} and your account will be suspended."
        return msg

    def is_verified_buyer(self, user_id: str, book_id: str) -> bool:
        return self.purchases.already_owned(user_id, book_id)

    def user_review(self, user_id: str, book_id: str) -> dict | None:
        """The customer's PUBLISHED review of this book, if any."""
        for r in self.fs.load("reviews"):
            if r["user_id"] == user_id and r["book_id"] == book_id and r["status"] == rules.PUBLISHED:
                return r
        return None

    def list_reviews(self, book_id: str) -> list[dict]:
        """Published reviews, newest first, with the author's name.
        Only display_text (masked) is ever shown; original_text never is."""
        names = {u["user_id"]: u["full_name"] for u in self.fs.load("users")}
        rs = [dict(r) for r in self.fs.load("reviews")
              if r["book_id"] == book_id and r["status"] == rules.PUBLISHED]
        for r in rs:
            r["author"] = names.get(r["user_id"], "Former customer")
        return sorted(rs, key=lambda r: (r["timestamp"], r["review_id"]), reverse=True)

    def list_user_reviews(self, user_id: str) -> list[dict]:
        """My Reviews (ASSUMPTIONS A-14): all the user's reviews, blocked ones included."""
        titles = {b["book_id"]: b["title"] for b in self.fs.load("books")}
        rs = [dict(r, title=titles.get(r["book_id"], "(book removed)"))
              for r in self.fs.load("reviews") if r["user_id"] == user_id]
        return sorted(rs, key=lambda r: (r["timestamp"], r["review_id"]), reverse=True)
