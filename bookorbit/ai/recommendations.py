"""RecommendationEngine - the three Home-page books (SRS 4.10, UC-03, UC-06, R3, R4).

R3 (Visitors, Super-Users): the most popular books, popularity = views + 3 x purchases.
R4 (customers): a content-based recommender.
  1. Build a profile from the customer's history: every purchased book adds 3 points and
     every viewed book 1 point to its category, its author and each of its keywords,
     e.g. {"cat:Fantasy": 7, "auth:Nils Corrigan": 3, "kw:dragons": 4}.
  2. Score every book the customer does not own: the sum of the profile points of its
     category, author and keywords, + 0.1 x its weighted rating as a small tie-breaker.
  3. Keep the 3 best books that match the profile; fill up with popular books.
"""
from collections import Counter

from bookorbit import rules

TIE_BREAK = 0.1          # SRS 4.10 score(): "+ 0.1 * weighted_avg - small tie-breaker"


def popularity(book: dict) -> int:
    """R3: browse_count + 3 x purchase_count."""
    return book["browse_count"] + rules.POPULAR_PURCHASE_WEIGHT * book["purchase_count"]


def keywords(book: dict) -> list[str]:
    """keywords is a comma-separated string (ASSUMPTIONS A-12)."""
    return [k.strip() for k in (book.get("keywords") or "").split(",") if k.strip()]


def book_terms(book: dict) -> list[str]:
    return ["cat:" + book["category"], "auth:" + book["author"]] + ["kw:" + k for k in keywords(book)]


class RecommendationEngine:
    def __init__(self, fs):
        self.fs = fs

    def home_books(self, session) -> tuple[str, list[dict]]:
        k = rules.HOME_BOOK_COUNT
        if session.role in (rules.VISITOR, rules.SU):
            return "Top 3 Most Popular", self.top_popular(k)
        recs = self.personalized(session.user["user_id"], k)
        if not recs:                                    # UC-06 E1 (no history) / E3 (owns everything)
            return "Popular right now", self.top_popular(k)
        return "Recommended for You", recs

    def top_popular(self, k: int = 3, exclude=frozenset()) -> list[dict]:
        """Ties broken by weighted average (desc), then title (UC-03 E3)."""
        books = [b for b in self.fs.load("books") if b["book_id"] not in exclude]
        books.sort(key=lambda b: (-popularity(b), -b["weighted_avg"], b["title"].lower()))
        return books[:k]                                # UC-03 E1/E2: fewer / none

    def personalized(self, user_id: str, k: int = 3) -> list[dict]:
        """UC-06 / R4."""
        profile = self.build_profile(user_id)
        if not profile:                                 # E1: no history yet
            return []
        owned = {p["book_id"] for p in self.fs.load("purchases") if p["user_id"] == user_id}
        scored = [(self.score(b, profile), b) for b in self.fs.load("books") if b["book_id"] not in owned]
        scored.sort(key=lambda sb: (-sb[0], sb[1]["title"].lower()))
        # D-19: a pick must MATCH the profile. The pseudo-code keeps "s > 0", but the
        # tie-breaker makes every rated book score > 0, so E2's popular fill would never
        # happen and unrelated well-rated books would be "recommended".
        picks = [b for s, b in scored if self.match(b, profile) > 0][:k]
        if len(picks) < k:                              # E2: fill with popular books
            picks += self.top_popular(k - len(picks), exclude=owned | {b["book_id"] for b in picks})
        return picks

    def build_profile(self, user_id: str) -> Counter:
        """Weights per term: purchase = 3 (W_BUY), view = 1 (W_VIEW) (UC-06 step 3)."""
        books = {b["book_id"]: b for b in self.fs.load("books")}
        profile = Counter()
        for p in self.fs.load("purchases"):
            if p["user_id"] == user_id and p["book_id"] in books:
                for t in book_terms(books[p["book_id"]]):
                    profile[t] += rules.PROFILE_W_BUY
        for e in self.fs.load("browse_history"):
            if e["user_id"] == user_id and e["book_id"] in books:
                for t in book_terms(books[e["book_id"]]):
                    profile[t] += rules.PROFILE_W_VIEW
        return profile

    @staticmethod
    def match(book: dict, profile: Counter) -> float:
        """Profile points of the book's category, author and keywords."""
        return sum(profile.get(t, 0) for t in book_terms(book))

    def score(self, book: dict, profile: Counter) -> float:
        return self.match(book, profile) + TIE_BREAK * book["weighted_avg"]

    @staticmethod
    def reasons(book: dict, profile: Counter) -> list[str]:
        """Which of the customer's interests a recommended book matches (shown in the UI)."""
        labels = {"cat": "category", "auth": "author", "kw": "keyword"}
        return [f"{labels[t.split(':', 1)[0]]} {t.split(':', 1)[1]}" for t in book_terms(book) if profile.get(t)]
