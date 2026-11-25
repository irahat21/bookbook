"""seed.py builds the demo states through the real services (Phase 2)."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import seed
from bookorbit import rules
from bookorbit.persistence.filestore import FileStore


class SeedTests(unittest.TestCase):
    def test_seed_demo_states(self):
        tmp = tempfile.mkdtemp(prefix="bookorbit_seed_")
        try:
            with mock.patch.dict(os.environ, {"DATA_DIR": tmp}), mock.patch.object(sys, "argv", ["seed.py", "--force"]), \
                    contextlib.redirect_stdout(io.StringIO()):
                seed.main()        # main() also asserts the demo states (VIP, suspended, warnings, lists)
            fs = FileStore(tmp)
            users = {u["username"]: u for u in fs.load("users")}
            self.assertEqual((users["victor"]["role"], users["victor"]["balance"]), (rules.VC, 120.0))
            self.assertEqual((users["alice"]["promo_purchases"], users["alice"]["balance"]), (3, 50.0))
            self.assertEqual(users["sid"]["balance"], -1.0)
            for u in users.values():           # the ledger explains every balance (SRS 4.11)
                txns = sorted((t for t in fs.load("transactions") if t["user_id"] == u["user_id"]),
                              key=lambda t: t["txn_id"])
                self.assertEqual(txns[-1]["balance_after"] if txns else 0.0, u["balance"], u["username"])
            verified = [r for r in fs.load("reviews") if r["verified_buyer"]]
            self.assertTrue(verified and all(r["weight"] == rules.W_VERIFIED for r in verified))
            # Phase 3: 10 books carry a text (A-11), the rest none (UC-14 E1); policies for the chatbot
            with_text = [b for b in fs.load("books") if b["text_path"]]
            self.assertEqual(len(with_text), len(seed.BOOK_TEXTS))
            self.assertTrue(all(fs.resolve(b["text_path"]).exists() for b in with_text))
            self.assertTrue((fs.dir / "policies.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
