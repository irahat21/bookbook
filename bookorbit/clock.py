"""One place for "now" in the Phase 2+ services.

Services stamp records with clock.now(). seed.py uses clock.frozen(...) so the
demo data it writes through the real services gets fixed, repeatable timestamps
instead of the time the seed happened to run.
"""
from contextlib import contextmanager
from datetime import datetime

FORMAT = "%Y-%m-%d %H:%M:%S"     # SRS 3.1: datetime is YYYY-MM-DD HH:MM:SS
_fixed: str | None = None


def now() -> str:
    return _fixed or datetime.now().strftime(FORMAT)


@contextmanager
def frozen(timestamp: str):
    """Make now() return `timestamp` inside the with-block (used by seed.py only)."""
    global _fixed
    old, _fixed = _fixed, timestamp
    try:
        yield
    finally:
        _fixed = old
