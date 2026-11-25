"""Test fixtures: a fresh temporary data folder per test, plus sample generators."""
import shutil
import tempfile
import unittest

from bookorbit.app_context import build_context
from bookorbit import rules
from bookorbit.config import DEFAULTS
from bookorbit.services.session import Session
from seed import make_face_photo, make_voice


class TempStoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bookorbit_test_")
        self.ctx = build_context(dict(DEFAULTS, DATA_DIR=self.tmp))
        self.fs = self.ctx.fs

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # samples (MOCK biometrics)
    @staticmethod
    def face(person="pat", variant=0, faces=1):
        return make_face_photo(person, faces, variant)

    @staticmethod
    def voice(pitch=220, seconds=3.0, variant=0):
        return make_voice(pitch, seconds, variant)

    def add_book(self, **over):
        b = {"book_id": self.fs.next_id("books", "B"), "title": "Book", "author": "Author A",
             "category": "Fiction", "keywords": "family, secrets", "pub_year": 2000, "price": 10.0,
             "description": "A story.", "cover_path": None, "cover_vec_path": None, "text_path": None,
             "added_by": "U-0001", "browse_count": 0, "purchase_count": 0, "rating_count": 0,
             "weighted_avg": 0.0, "list_status": "NONE", "indexed": False, "added_at": "2026-11-01 10:00:00"}
        b.update(over)
        return self.fs.append("books", b)

    def add_text_book(self, text: str, **over):
        """A book with a full text in data/texts/ (UC-14, R15)."""
        bid = self.fs.next_id("books", "B")
        rel = f"texts/{bid}.txt"
        self.fs.resolve(rel).parent.mkdir(parents=True, exist_ok=True)
        self.fs.resolve(rel).write_text(text, encoding="utf-8")
        return self.add_book(book_id=bid, text_path=rel, **over)

    def write_policies(self, *paragraphs):
        (self.fs.dir / "policies.txt").write_text("\n\n".join(paragraphs), encoding="utf-8")

    def add_user(self, username="pat", role=rules.RC, status=rules.ACTIVE, balance=0.0, **over):
        """A customer record written straight to users.txt (no biometrics needed)."""
        u = {"user_id": self.fs.next_id("users", "U"), "username": username, "full_name": username.title(),
             "email": f"{username}@x.com", "role": role, "status": status, "balance": balance, "warnings": 0,
             "purchase_count": 0, "total_spent": 0.0, "promo_purchases": 0, "promo_spent": 0.0,
             "created_at": "2026-11-01 10:00:00"}
        u.update(over)
        return self.fs.append("users", u)

    def session_for(self, user: dict) -> Session:
        s = Session(self.fs)
        s.start(self.fs.find("users", "user_id", user["user_id"]))
        return s

    def user(self, user: dict) -> dict:
        """Fresh copy of a user record."""
        return self.fs.find("users", "user_id", user["user_id"])

    def taboo(self, *words):
        for w in words:
            self.fs.append("taboo_words", {"word": w, "added_by": "U-0001", "added_at": "2026-11-01 10:00:00"})
