"""TabooService (SRS 4.18, read side) and ModerationEngine (SRS 4.15, R9).

R9: case-insensitive WHOLE-word match. 1-3 taboo words -> each is replaced by
asterisks of the same length and the review is published; more than 3 -> the
review is BLOCKED. Whole words means 'class' does not match 'ass'.
Adding / editing / removing words is UC-16 (Phase 4).
"""
import re
from dataclasses import dataclass

from bookorbit import rules

WORD = re.compile(r"[A-Za-z']+")     # SRS 4.15 tokenize()


class TabooService:
    def __init__(self, fs):
        self.fs = fs

    def list_words(self) -> list[str]:
        return sorted(r["word"] for r in self.fs.load("taboo_words"))


@dataclass
class ModerationResult:
    status: str          # PUBLISHED or BLOCKED
    display_text: str    # masked text ("" when blocked: a blocked review is never shown)
    count: int           # number of taboo words found


class ModerationEngine:
    def __init__(self, taboo: TabooService):
        self.taboo = taboo

    @staticmethod
    def tokenize(text: str) -> list[tuple[str, int, int]]:
        return [(m.group(), m.start(), m.end()) for m in WORD.finditer(text)]

    def find_taboo(self, text: str) -> list[tuple[str, int, int]]:
        words = set(self.taboo.list_words())           # stored lower case
        return [(w, s, e) for (w, s, e) in self.tokenize(text) if w.lower() in words]

    @staticmethod
    def mask(text: str, matches) -> str:
        chars = list(text)
        for _w, s, e in matches:
            chars[s:e] = "*" * (e - s)
        return "".join(chars)

    def moderate(self, text: str) -> ModerationResult:
        matches = self.find_taboo(text)
        if len(matches) > rules.TABOO_BLOCK_ABOVE:
            return ModerationResult(rules.BLOCKED, "", len(matches))
        return ModerationResult(rules.PUBLISHED, self.mask(text, matches), len(matches))
