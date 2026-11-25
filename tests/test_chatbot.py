"""ChatbotService (SRS 4.20): UC-12, UC-13, R14, deviations D-16 and D-17."""
from bookorbit import clock, rules
from bookorbit.ai.llm import MockLLM, OfflineLLM
from bookorbit.errors import LLMUnavailable
from bookorbit.services.chatbot import ADMIN_EXAMPLES, ChatbotService
from bookorbit.services.session import Session
from tests.helpers import TempStoreCase

VIP = "VIP status: VIP Customers pay 90 percent of the list price, a 10 percent discount."
FINE = "Insufficient funds: the purchase is rejected and a fine of $1.00 is charged."


class SpyLLM(MockLLM):
    """A MOCK that records generate() calls and can pretend to be offline."""

    def __init__(self, available=True, fail_generate=False):
        super().__init__()
        self.available, self.fail_generate, self.calls = available, fail_generate, []

    def is_available(self):
        return self.available

    def generate(self, prompt, *args, **kw):
        self.calls.append((kw.get("task"), prompt))
        if self.fail_generate:
            raise LLMUnavailable("down")
        return super().generate(prompt, *args, **kw)


class ChatbotTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.write_policies(VIP, FINE)
        self.book = self.add_book(title="Ocean Atlas", author="Mira Juniper", category="Science",
                                  keywords="ocean, maps", description="Maps of the deep ocean floor.")
        self.ctx.rag.build_index()
        self.bot = self.ctx.chatbot
        self.visitor = Session(self.fs)
        self.pat = self.add_user("pat", balance=42.5)
        self.vic = self.add_user("vic", role=rules.VC)
        self.sue = self.add_user("sue", role=rules.SU)

    def ask(self, user, q, bot=None):
        return (bot or self.bot).ask(self.visitor if user is None else self.session_for(user), q)

    # ---- R14: the permission table, one row per role
    def test_r14_permission_table(self):
        p = ChatbotService.is_permitted
        self.assertEqual({i for i in (rules.STORE, rules.ACCOUNT, rules.GENERAL, rules.ADMIN) if p(rules.VISITOR, i)},
                         {rules.STORE})
        for role in (rules.RC, rules.VC):
            self.assertTrue(p(role, rules.ACCOUNT) and p(role, rules.GENERAL) and not p(role, rules.ADMIN))
        self.assertTrue(all(p(rules.SU, i) for i in (rules.STORE, rules.ACCOUNT, rules.GENERAL, rules.ADMIN)))

    # ---- intents (SRS 4.20 classify_intent)
    def test_classify_keywords(self):
        c = self.bot.classify_intent
        self.assertEqual(c("Which accounts are suspended?"), rules.ADMIN)
        self.assertEqual(c("What is my balance?"), rules.ACCOUNT)
        self.assertEqual(c("What does VIP give me?"), rules.STORE)
        self.assertEqual(c("Tell me about Ocean Atlas"), rules.STORE)          # catalog title
        self.assertEqual(c("Can you define this word?"), rules.GENERAL)        # "fine" is not in "define"
        self.assertEqual(c("Show my purchases"), rules.ACCOUNT)                # "my purchase" + s
        self.assertEqual(c("Tell me a joke"), rules.GENERAL)

    def test_mock_classifier_uses_store_context(self):                       # A-27
        self.assertEqual(self.bot.classify_intent("Anything about the deep ocean floor?"), rules.STORE)

    # ---- UC-12 normal scenario
    def test_store_question_answered_from_store_data(self):
        r = self.ask(None, "What discount do VIP customers get?")
        self.assertEqual(r.source, "RAG")
        self.assertIn("90 percent", r.text)
        self.assertIn(VIP, r.facts)

    def test_customer_general_question_is_general_ai(self):                  # UC-12 step 6
        r = self.ask(self.pat, "Tell me a joke")
        self.assertEqual(r.source, "GENERAL")
        self.assertIn("MOCK", r.text)

    def test_account_question_uses_only_own_data(self):
        r = self.ask(self.pat, "What is my balance?")
        self.assertEqual(r.source, "RAG")
        self.assertTrue(r.text.startswith("Your balance: $42.50"), r.text)   # own fact first
        self.assertFalse(any("vic" in f for f in r.facts))
        prompt = self.bot.build_prompt("q", ["f"], rules.RC)
        self.assertIn("Never reveal other customers' data", prompt)

    def test_exchange_is_logged(self):                                       # UC-12 step 7
        self.ask(None, "What discount do VIP customers get?")
        self.ask(self.pat, "Tell me a joke")
        log = self.fs.load("chat_log")
        self.assertEqual([(m["user_id"], m["role"], m["source"]) for m in log],
                         [(None, rules.VISITOR, "RAG"), (self.pat["user_id"], rules.RC, "GENERAL")])

    # ---- exceptional scenarios
    def test_e1_visitor_account_question_denied(self):
        r = self.ask(None, "What is my balance?")
        self.assertEqual((r.source, r.text), ("DENIED", "That information isn't available for your account type."))

    def test_e1_customer_admin_question_denied(self):                        # UC-13 E1
        r = self.ask(self.vic, "Which accounts are suspended?")
        self.assertEqual(r.source, "DENIED")

    def test_e2_visitor_general_question(self):
        r = self.ask(None, "Tell me a joke")
        self.assertEqual((r.source, r.text), ("DENIED", "I can only answer questions about the store."))

    def test_e3_offline(self):
        bot = ChatbotService(self.fs, self.ctx.rag, OfflineLLM())
        r = self.ask(self.pat, "What does VIP give me?", bot)
        self.assertEqual((r.source, r.text), ("ERROR", "The assistant is offline - please try again later."))

    def test_e3_ollama_stops_mid_session(self):
        bot = ChatbotService(self.fs, self.ctx.rag, SpyLLM(fail_generate=True))
        self.assertEqual(self.ask(self.pat, "What does VIP give me?", bot).source, "ERROR")

    def test_e4_empty_question_not_logged(self):
        self.assertEqual(self.ask(self.pat, "   ").source, "NONE")
        self.assertEqual(self.fs.load("chat_log"), [])

    # ---- deviations
    def test_d16_offline_classifies_without_llm(self):
        spy = SpyLLM(available=False)
        r = self.ask(self.pat, "Tell me a joke", ChatbotService(self.fs, self.ctx.rag, spy))
        self.assertEqual(r.source, "ERROR")
        self.assertEqual(spy.calls, [])                                      # the LLM was never called

    def test_d17_visitor_store_question_without_context(self):
        # "return" + "policy" make it a STORE question, and no chunk mentions either word, so
        # the pseudo-code would answer "I couldn't find that..." labelled RAG. D-17: P10 instead.
        q = "Is there a return policy?"
        self.assertEqual(self.bot.classify_intent(q), rules.STORE)          # preconditions of
        self.assertEqual(self.ctx.rag.retrieve(q, {"PUBLIC"}), [])         # the D-17 branch
        r = self.ask(None, q)
        self.assertEqual((r.source, r.text), ("DENIED", "I can only answer questions about the store."))
        self.assertEqual(self.ask(self.pat, q).source, "GENERAL")         # a customer gets [General AI]

    # ---- UC-13 (Super-User)
    def test_admin_facts_from_files(self):
        self.fs.update("users", "user_id", self.pat["user_id"], {"status": rules.SUSPENDED})
        with clock.frozen("2026-11-20 10:00:00"):
            r = self.ask(self.sue, "Which accounts are suspended?")
        self.assertEqual(r.source, "ADMIN")
        self.assertEqual(r.facts, ["Suspended accounts: pat (Pat)"])
        self.assertIn("pat (Pat)", r.text)

    def test_admin_sales_this_month(self):
        self.fs.append("purchases", {"purchase_id": "P-0001", "user_id": self.pat["user_id"], "book_id": "B-0001",
                                     "txn_id": "X", "list_price": 10.0, "discount": 0.0, "price_paid": 10.0,
                                     "timestamp": "2026-11-03 09:00:00"})
        self.fs.append("purchases", {"purchase_id": "P-0002", "user_id": self.pat["user_id"], "book_id": "B-0001",
                                     "txn_id": "Y", "list_price": 5.0, "discount": 0.0, "price_paid": 5.0,
                                     "timestamp": "2026-10-30 09:00:00"})                    # last month
        with clock.frozen("2026-11-20 10:00:00"):
            facts, understood = self.bot.admin_context("What are the sales this month?")
        self.assertTrue(understood)
        self.assertEqual(facts, ["Sales this month (2026-11): $10.00 from 1 purchase(s)"])

    def test_admin_lists_are_separate(self):
        self.assertEqual([f.split(":")[0] for f in self.bot.admin_context("Which books are on the No-Order list?")[0]],
                         ["No-Order List"])
        self.assertEqual([f.split(":")[0] for f in self.bot.admin_context("Show both order lists")[0]],
                         ["No-Order List", "To-Order List"])

    def test_admin_e2_offline_shows_fact_table(self):
        bot = ChatbotService(self.fs, self.ctx.rag, OfflineLLM())
        r = self.ask(self.sue, "Which books are on the No-Order list?", bot)
        self.assertEqual(r.source, "ADMIN")
        self.assertIn("• No-Order List: none", r.text)

    def test_admin_e3_lists_examples(self):
        r = self.ask(self.sue, "Give me an admin report")
        self.assertEqual(r.source, "ADMIN")
        self.assertTrue(all(e in r.text for e in ADMIN_EXAMPLES))
