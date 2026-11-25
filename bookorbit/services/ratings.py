"""RatingService - weighted rating and order lists (SRS 4.17, R12, R13).

Phase 1 needs recalculate() so seeded reviews give every book a weighted
average for the details page (UC-05) and the popularity tie-break (UC-03 E3).
The SU list screen (UC-18) arrives in Phase 4.
"""
from bookorbit import rules


def weighted_average(reviews: list[dict]) -> float:
    """R12: sum(rating x weight) / sum(weight) over published reviews."""
    total_w = sum(r["weight"] for r in reviews)
    if total_w == 0:
        return 0.0
    return round(sum(r["rating"] * r["weight"] for r in reviews) / total_w, 2)


def classify(rating_count: int, avg: float) -> str:
    """R13: > 3 ratings and avg < 2 -> No-Order; > 3 and avg > 4 -> To-Order."""
    if rating_count > rules.MIN_RATINGS and avg < rules.NO_ORDER_BELOW:
        return rules.LIST_NO_ORDER
    if rating_count > rules.MIN_RATINGS and avg > rules.TO_ORDER_ABOVE:
        return rules.LIST_TO_ORDER
    return rules.LIST_NONE


class RatingService:
    def __init__(self, fs):
        self.fs = fs

    def recalculate(self, book_id: str) -> dict:
        rs = [r for r in self.fs.load("reviews")
              if r["book_id"] == book_id and r["status"] == "PUBLISHED"]
        avg = weighted_average(rs)
        return self.fs.update("books", "book_id", book_id, {
            "rating_count": len(rs), "weighted_avg": avg,
            "list_status": classify(len(rs), avg)})

    def recalculate_all(self) -> int:
        books = self.fs.load("books")
        for b in books:
            self.recalculate(b["book_id"])
        return len(books)
