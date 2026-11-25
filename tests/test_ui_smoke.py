"""Opens every Phase 1 screen for every role in a real Tk window (then closes it).
Skipped automatically when no display is available."""
import tkinter as tk
from tkinter import ttk
import unittest

from bookorbit import rules
from bookorbit.ai.biometrics import FACE
from bookorbit.ui.main_window import SIDEBAR, MainWindow
from seed import make_cover, make_cover_photo, make_face_photo
from tests.helpers import TempStoreCase
from tests.test_companion import TEXT as COMPANION_TEXT


class UISmokeTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        for i in range(15):
            self.add_book(title=f"Book {i:02d}", browse_count=i)
        self.text_book = self.add_text_book(COMPANION_TEXT, title="The Lighthouse Book")   # B-0016 (UC-14)
        (self.fs.dir / "covers").mkdir(exist_ok=True)                    # covers for UC-04 cover search
        for i, bid in enumerate(("B-0003", "B-0007", "B-0011")):
            (self.fs.dir / "covers" / f"{bid}.png").write_bytes(make_cover(bid, i))
            self.fs.update("books", "book_id", bid, {"cover_path": f"covers/{bid}.png"})
        self.ctx.auth.register("Pat", "pat", "p@x.com", make_face_photo("pat", 1, 0))
        try:
            self.win = MainWindow(self.ctx)
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.win.withdraw()
        self.assertTrue(self.ctx.ai_ready.wait(30))      # background AI indexing (SRS 4.24)

    def tearDown(self):
        if hasattr(self, "win"):
            self.ctx.ai_ready.wait(30)                   # never delete data/ under the indexing thread
            self.win.destroy()
        super().tearDown()

    def visit_all(self, role):
        for _label, screen, kwargs in SIDEBAR[role]:
            if screen != "logout":
                self.win.show(screen, **kwargs)
                self.win.update()
        self.win.show("book", book_id="B-0001")
        self.win.update()
        self.win.show("catalog", query="2015-2000", field="year")   # invalid range -> banner
        self.win.update()
        self.assertIn("year", self.win.current.banner.text)

    def test_all_roles_in_one_window(self):
        # One test on purpose: on macOS, creating a second Tk root in the same
        # process after destroying the first can hang inside update().
        self.win.run_async = lambda work, done: self.run_now(work, done)   # no worker threads in tests
        self.visit_all(rules.VISITOR)
        self.visitor_chat()
        self.cover_search()
        session = self.ctx.auth.login("pat", FACE, make_face_photo("pat", 1, 1))
        self.win.on_login(session)
        self.visit_all(rules.RC)
        self.phase2_flows()
        self.phase3_flows()
        self.ctx.fs.update("users", "username", "pat", {"status": rules.SUSPENDED})
        session.refresh()
        self.win.show("catalog")                     # R8: redirected to the wallet
        self.assertEqual(type(self.win.current).__name__, "WalletScreen")

    @staticmethod
    def run_now(work, done):
        try:
            result = work()
        except Exception as e:
            done(None, e)
        else:
            done(result, None)

    def chat(self, question):
        """UC-12 through the real ChatScreen; returns the ChatResponse it received."""
        if self.screen() != "ChatScreen":
            self.win.show("chat")
        chat = self.win.current
        self.assertEqual(str(chat.send_btn["state"]), "disabled")         # E4: empty -> disabled
        chat.use_example(question)
        self.assertEqual(str(chat.send_btn["state"]), "normal")
        chat.on_send()
        self.win.update()
        self.assertIn(question, chat.log.get("1.0", "end"))
        self.assertNotIn("…thinking", chat.log.get("1.0", "end"))
        return chat.last_response

    def cover_search(self):
        """UC-04 step 4 / E3 / E4 through the real CatalogScreen (file dialog skipped)."""
        photo = self.fs.dir / "photo.jpg"
        photo.write_bytes(make_cover_photo(self.fs.resolve("covers/B-0007.png").read_bytes(), 0))
        self.win.show("home")
        self.win.current.on_ai_ready()
        self.assertEqual(str(self.win.current.cam[0]["state"]), "normal")     # index ready -> enabled
        self.win.show("catalog", cover_file=str(photo))                        # what Home's camera does
        cat = self.win.current
        self.assertEqual(cat.results[0]["book_id"], "B-0007")
        self.assertIn("Cover search with photo.jpg", cat.status.cget("text"))
        (self.fs.dir / "notes.txt").write_text("not a picture")
        cat.run_cover_search(str(self.fs.dir / "notes.txt"))                   # E3
        self.assertIn("JPG or PNG", cat.banner.text)
        face = self.fs.dir / "face.png"
        face.write_bytes(make_face_photo("pat", 1, 0))
        cat.run_cover_search(str(face))                                        # E4
        self.assertEqual(cat.results, [])
        self.win.update()

    def visitor_chat(self):
        self.assertEqual(self.chat("Tell me a joke").source, "DENIED")      # UC-12 E2
        self.assertIn("[Not available]", self.win.current.log.get("1.0", "end"))

    def phase3_flows(self):
        """UC-12 / UC-13 / UC-14 / UC-04 cover search through the real screens."""
        r = self.chat("What is my balance?")                             # UC-12 ACCOUNT
        self.assertEqual(r.source, "RAG")
        self.assertIn("[Store data] · MOCK AI", self.win.current.log.get("1.0", "end"))
        self.companion_flows()
        self.win.show("recommendations")                                  # UC-06 with history
        self.win.update()
        labels = [w.cget("text") for w in self.win.current.winfo_children() if isinstance(w, ttk.Label)]
        self.assertIn("Recommended for You", labels)
        self.assertIn("Your interests", labels)

    def companion_flows(self):
        """UC-14: preview (R15), E2 + Buy, then every chapter and the AI tools."""
        bid = self.text_book["book_id"]
        self.ctx.wallet.deposit(self.win.session, "50")
        self.win.show("companion", book_id=bid)
        comp = self.win.current
        self.assertEqual(self.screen(), "CompanionScreen")
        self.assertFalse(comp.state.owned)
        self.assertIn("The Light", comp.text.get("1.0", "end"))
        comp.show_chapter(2)                                             # E2: locked chapter
        self.assertIn("Buy the book", comp.banner.text)
        comp.buy()                                                       # confirm() answered yes
        self.win.update()
        comp = self.win.current
        self.assertEqual(self.screen(), "CompanionScreen")
        self.assertTrue(comp.state.owned)
        comp.show_chapter(3)
        self.assertIn("violent storm", comp.text.get("1.0", "end"))
        comp.on_summarize()
        self.assertIn("Summary of chapter 3", comp.answer.get("1.0", "end"))
        comp.on_explain()                                                # E3: nothing selected
        self.assertIn("Select a passage first", comp.banner.text)
        comp.text.tag_add("sel", "3.0", "3.30")
        comp.on_explain()
        self.assertIn("Explanation", comp.answer.get("1.0", "end"))
        comp.on_quiz()
        self.assertEqual(len(comp.quiz), 3)
        for q, var in zip(comp.quiz, comp.quiz_vars):
            var.set(q["answer_index"])
        self.assertEqual(comp.check_quiz(), 3)
        comp.question.insert(0, "Why did the lamp fail?")
        comp.on_ask()
        self.assertIn("Answer", comp.answer.get("1.0", "end"))
        self.win.show("book", book_id="B-0001")                          # E1: no text -> disabled button
        self.win.update()

    def screen(self):
        return type(self.win.current).__name__

    def buy(self, book_id):
        self.win.show("book", book_id=book_id)
        self.win.current.on_buy(self.ctx.fs.find("books", "book_id", book_id))
        self.win.update()

    def phase2_flows(self):
        """UC-07..UC-11 through the real screens. Dialogs are answered by stubs."""
        self.win.confirm = lambda *_a: True
        self.win.inform = lambda *_a: None
        self.taboo("dumb", "stupid", "lame", "darn")
        # UC-07: invalid then valid deposit
        self.win.show("wallet")
        self.win.current.amount.insert(0, "12.345")
        self.win.current.on_deposit()
        self.assertIn("valid amount", self.win.current.banner.text)
        self.win.current.amount.delete(0, "end")
        self.win.current.amount.insert(0, "100")
        self.win.current.on_deposit()
        self.assertIn("100.00", self.win.current.banner.text)
        # UC-08: Buy Now -> receipt -> owned
        self.buy("B-0001")
        self.assertIn("You bought", self.win.current.banner.text)
        self.assertEqual(self.screen(), "BookDetailScreen")
        # UC-10: masked review
        detail = self.win.current
        detail.toggle_review_form()
        detail.stars_var.set(5)
        detail.review_text.insert("1.0", "Not dumb at all, great book.")
        detail.on_review(self.ctx.fs.find("books", "book_id", "B-0001"))
        self.win.update()
        self.assertIn("1 word masked", self.win.current.banner.text)
        # R5: 4th purchase promotes; sidebar now says VIP
        for bid in ("B-0002", "B-0003", "B-0004"):
            self.buy(bid)
        self.assertEqual(self.win.session.role, rules.VC)
        self.assertIn("VIP", self.win.current.banner.text)
        self.assertEqual(self.chat("Am I VIP?").source, "RAG")               # chat as a VIP Customer
        for name in ("orders", "my_reviews", "home"):
            self.win.show(name)
            self.win.update()
        # UC-11 E1: blocked review demotes the VIP
        self.win.show("book", book_id="B-0005")
        detail = self.win.current
        detail.stars_var.set(1)
        detail.review_text.insert("1.0", "Dumb, stupid, lame and darn boring.")
        detail.on_review(self.ctx.fs.find("books", "book_id", "B-0005"))
        self.win.update()
        self.assertEqual(self.win.session.role, rules.RC)
        self.assertIn("blocked", self.win.current.banner.text)
        # R7 / UC-08 E2: fine below $0 -> suspended -> wallet-only
        self.ctx.fs.update("users", "username", "pat", {"balance": 0.0})
        self.buy("B-0006")
        self.assertEqual(self.screen(), "WalletScreen")
        self.assertTrue(self.win.session.wallet_only)
        self.assertIn("SUSPENDED", self.win.current.banner.text)
        # R8: deposit back to >= $0 shows the reactivation note; an SU reopens (Phase 4 screen)
        self.win.current.amount.insert(0, "1")
        self.win.current.on_deposit()
        self.assertIn("reactivate", self.win.current.banner.text)
        self.ctx.status.reopen("U-0000", self.win.session.user["user_id"])
        self.win.refresh_chrome()


if __name__ == "__main__":
    unittest.main()
