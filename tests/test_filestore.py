"""FileStore (SRS 4.4) - JSON Lines persistence."""
from pathlib import Path

from tests.helpers import TempStoreCase


class FileStoreTests(TempStoreCase):
    def test_missing_table_loads_empty(self):
        self.assertEqual(self.fs.load("users"), [])

    def test_append_find_update(self):
        self.fs.append("users", {"user_id": "U-0001", "username": "a"})
        self.fs.append("users", {"user_id": "U-0002", "username": "b"})
        self.assertEqual(self.fs.find("users", "username", "b")["user_id"], "U-0002")
        self.fs.update("users", "user_id", "U-0001", {"username": "z"})
        self.assertEqual(self.fs.find("users", "user_id", "U-0001")["username"], "z")
        self.assertIsNone(self.fs.find("users", "username", "nobody"))

    def test_update_missing_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.fs.update("users", "user_id", "U-9999", {"x": 1})

    def test_next_id_is_max_plus_one_zero_padded(self):
        self.assertEqual(self.fs.next_id("reviews", "R"), "R-0001")
        self.fs.append("reviews", {"review_id": "R-0007"})
        self.fs.append("reviews", {"review_id": "R-0003"})
        self.assertEqual(self.fs.next_id("reviews", "R"), "R-0008")

    def test_one_json_object_per_line_and_no_temp_left(self):
        self.fs.save_all("books", [{"book_id": "B-0001"}, {"book_id": "B-0002"}])
        path = Path(self.tmp) / "books.txt"
        self.assertEqual(len(path.read_text().splitlines()), 2)
        self.assertFalse((Path(self.tmp) / "books.txt.tmp").exists())
