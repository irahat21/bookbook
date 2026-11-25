"""CatalogService - browse, text search, cover search, details (SRS 4.8, UC-04, UC-05)."""
import re
from datetime import datetime

from bookorbit import rules
from bookorbit.errors import ModelUnavailable, NotFound

SORT_KEYS = {
    "title": (lambda b: b["title"].lower(), False),
    "price": (lambda b: b["price"], False),
    "weighted_avg": (lambda b: b["weighted_avg"], True),   # best rated first
    "pub_year": (lambda b: b["pub_year"], True),           # newest first
}
FIELDS = ("title", "author", "keyword", "year")


def parse_year_range(q: str) -> tuple[int, int]:
    """'1990-2000' or '1995' -> (lo, hi). ValueError if non-numeric or from > to (UC-04 E2)."""
    m = re.fullmatch(r"\s*(\d{1,4})\s*(?:-\s*(\d{1,4})\s*)?", q)
    if not m:
        raise ValueError("Enter a year or a range like 1990-2000")
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if lo > hi:
        raise ValueError("The 'from' year must not be after the 'to' year")
    return lo, hi


class CatalogService:
    def __init__(self, fs, reviews, covers=None, purchases=None):
        self.fs = fs
        self.reviews = reviews
        self.purchases = purchases    # PurchaseService: VIP price + "already owned" (UC-05 step 5)
        self.covers = covers          # CoverIndex (UC-04 step 4); None or not ready -> E5

    def categories(self) -> list[str]:
        return sorted({b["category"] for b in self.fs.load("books")})

    def browse(self, category=None, sort="title") -> list[dict]:
        """All books (optionally one category), sorted. Paging is done by page()."""
        books = self.fs.load("books")
        if category:
            books = [b for b in books if b["category"] == category]
        key, reverse = SORT_KEYS.get(sort, SORT_KEYS["title"])
        return sorted(books, key=key, reverse=reverse)

    @staticmethod
    def page(books: list[dict], page: int = 1) -> list[dict]:
        """12 results per page (UC-04 step 5)."""
        start = (page - 1) * rules.PAGE_SIZE
        return books[start:start + rules.PAGE_SIZE]

    def search(self, query: str, field: str = "title", category=None) -> list[dict]:
        """Exact matches first, then prefix, then substring (UC-04 step 3)."""
        if field not in FIELDS:
            raise ValueError(f"Unknown search field: {field}")
        q = (query or "").strip().lower()
        books = self.browse(category)
        if not q:
            return books
        results = []
        if field == "year":
            lo, hi = parse_year_range(q)                     # ValueError -> field highlighted
            results = [(0, b) for b in books if lo <= b["pub_year"] <= hi]
        else:
            for b in books:
                if field == "title":
                    text = b["title"].lower()
                elif field == "author":
                    text = b["author"].lower()
                else:  # keyword: keywords + description (SRS 4.8)
                    text = (b["keywords"] + " " + b["description"]).lower()
                if text == q:
                    results.append((0, b))
                elif text.startswith(q):
                    results.append((1, b))
                elif q in text:
                    results.append((2, b))
        results.sort(key=lambda rb: (rb[0], rb[1]["title"].lower()))
        return [b for _, b in results]

    def search_by_cover(self, image: bytes) -> list[tuple[dict, float]]:
        """UC-04 step 4: the (up to) 5 covers most similar to the photo, best first, with
        their similarity. Raises ModelUnavailable (E5) or ValueError (E3, not an image).
        Returns [] when even the best cover is below the threshold (E4); weaker matches
        below it are dropped too (ASSUMPTIONS A-33)."""
        if self.covers is None or not self.covers.ready:
            raise ModelUnavailable("Cover search is not available (image model not loaded)")
        hits = self.covers.query(self.covers.embed_bytes(image), rules.COVER_TOP_K)
        if not hits or hits[0][1] < self.covers.min_sim:                # E4
            return []
        books = {b["book_id"]: b for b in self.fs.load("books")}
        return [(books[bid], sim) for bid, sim in hits if sim >= self.covers.min_sim and bid in books]

    def get_details(self, book_id: str, session) -> dict:
        """Book + published reviews; records the view (UC-05)."""
        book = self.fs.find("books", "book_id", book_id)
        if book is None:
            raise NotFound("Book unavailable")                # E1
        book = self.record_browse(session, book_id)
        book["reviews"] = self.reviews.list_reviews(book_id)  # E2 handled by the screen
        # UC-05 step 5 / UC-09: a VC sees the VIP price. final_price re-reads the role,
        # so a VIP demoted a moment ago sees the full price at once (UC-11 E1).
        book["display_price"], book["vip_discount"] = book["price"], 0.0
        book["owned"], book["my_review"] = False, None
        if session.is_customer and session.user and self.purchases:
            price = self.purchases.final_price(session.user, book)
            book["display_price"], book["vip_discount"] = price.paid, price.discount
            uid = session.user["user_id"]
            book["owned"] = self.purchases.already_owned(uid, book_id)          # UC-08 E3
            book["my_review"] = self.reviews.user_review(uid, book_id)          # A-09
        return book

    def record_browse(self, session, book_id: str) -> dict:
        """browse_count + 1 for every view (R3); a BROWSE_EVENT for RC/VC (R4)."""
        with self.fs.lock:  # read-increment-write as one step
            b = self.fs.find("books", "book_id", book_id)
            updated = self.fs.update("books", "book_id", book_id,
                                     {"browse_count": b["browse_count"] + 1})
        if session.role in rules.CUSTOMER_ROLES and session.user:
            self.fs.append("browse_history", {
                "event_id": self.fs.next_id("browse_history", "E"),
                "user_id": session.user["user_id"], "book_id": book_id, "action": "VIEW",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        return updated
