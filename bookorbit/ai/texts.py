"""Book-text helpers shared by RAGRetriever (SRS 4.21) and ReadingCompanion (4.23).

The SRS assumes Project Gutenberg .txt files: strip the Gutenberg licence header and
footer, then split the text into chapters. Our seeded books are short original texts
(ASSUMPTIONS A-11) written in the same "CHAPTER n: Title" layout, so the same code
reads both.
"""
import re

# "*** START OF THE PROJECT GUTENBERG EBOOK ... ***" / "*** END OF ..." markers
_START = re.compile(r"^\*{3}\s*START OF (THE|THIS) PROJECT GUTENBERG.*$", re.I | re.M)
_END = re.compile(r"^\*{3}\s*END OF (THE|THIS) PROJECT GUTENBERG.*$", re.I | re.M)
# A chapter heading on its own line: "CHAPTER 3", "Chapter IV.", "CHAPTER 2: The Storm"
_HEADING = re.compile(r"^[ \t]*CHAPTER[ \t]+([0-9]+|[IVXLC]+)\b[.:]?[ \t]*(.*)$", re.I | re.M)


def strip_gutenberg_header_footer(text: str) -> str:
    """Keep only the text between the Gutenberg START and END markers (if present)."""
    start = _START.search(text)
    if start:
        text = text[start.end():]
    end = _END.search(text)
    if end:
        text = text[:end.start()]
    return text.strip()


def split_chapters(text: str) -> list[tuple[int, str, str]]:
    """[(chapter_no, title, body)], numbered 1..n in reading order.

    Anything before the first heading (title page, preface) is dropped. A text with no
    chapter headings at all is treated as one chapter, so every text can be read."""
    heads = list(_HEADING.finditer(text))
    if not heads:
        return [(1, "Full text", text.strip())] if text.strip() else []
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end].strip()
        title = m.group(2).strip() or f"Chapter {i + 1}"
        out.append((i + 1, title, body))
    return out


def read_chapters(path) -> list[tuple[int, str, str]]:
    """Read a book text file (UTF-8) and split it into chapters."""
    with open(path, encoding="utf-8") as fh:
        return split_chapters(strip_gutenberg_header_footer(fh.read()))
