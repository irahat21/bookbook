"""ChatbotService - role-aware AI chatbot (SRS 4.20, UC-12, UC-13, R14).

How a question is answered (UC-12 Petri net, Figure 13):
1. classify the intent: ADMIN, ACCOUNT, STORE or GENERAL (keyword rules first);
2. check R14: is that intent allowed for the user's role? If not -> DENIED;
3. if the language model is offline -> offline message (ADMIN: the facts as a plain list);
4. collect facts: ADMIN -> computed from the files; otherwise RAG chunks (+ the user's own
   account facts for ACCOUNT questions);
5. the LLM answers using ONLY those facts ([Store data] / [Admin data]), or, with no facts,
   from its own knowledge ([General AI]) - but never for a Visitor (D-17);
6. every exchange is appended to chat_log.txt.
"""
import re
from dataclasses import dataclass, field

from bookorbit import clock, rules
from bookorbit.ai.rag import PUBLIC
from bookorbit.errors import LLMUnavailable

# source values of CHAT_MESSAGE (SRS 3.1); the GUI shows them as labels
RAG, GENERAL_SRC, ADMIN_SRC, DENIED, ERROR, NONE = "RAG", "GENERAL", "ADMIN", "DENIED", "ERROR", "NONE"

# SRS 4.20 classify_intent keyword lists. "admin" and "report" are added so that UC-13 E3
# ("question not understood") can happen at all (ASSUMPTIONS A-13).
ADMIN_WORDS = ("suspended", "all users", "warnings issued", "revenue", "sales", "no-order", "to-order",
               "total balance", "every customer", "admin", "report")
ACCOUNT_WORDS = ("my balance", "my order", "my purchase", "my review", "my warning", "my account", "am i vip")
STORE_WORDS = ("price", "stock", "policy", "discount", "fine", "vip", "return", "recommend")

OFFLINE_TEXT = "The assistant is offline - please try again later."                  # UC-12 E3
NOT_PERMITTED_TEXT = "That information isn't available for your account type."         # UC-12 E1
STORE_ONLY_TEXT = "I can only answer questions about the store."                       # UC-12 E2, P10
ADMIN_EXAMPLES = [                                                                     # UC-13 E3 (A-13)
    "Which accounts are suspended?",
    "What are the sales this month?",
    "How many warnings were issued this month?",
    "What is the total balance of all users?",
    "How many customers are there among all users?",
    "Which books are on the No-Order list?",
    "Which books are on the To-Order list?",
]

# admin_context(): which question words make a fact relevant (SRS: "f relates to keywords of question")
ADMIN_TOPICS = {
    "suspended": ("suspend",),
    "roles": ("role", "vip", "customer", "users", "registered"),
    "balances": ("balance",),
    "sales": ("sales", "revenue", "sold", "sell"),
    "warnings": ("warning",),
    "no_order": ("no-order", "no order"),
    "to_order": ("to-order", "to order"),
}
BOTH_LISTS = ("order list", "lists")      # "order lists" without "no"/"to": show both lists


@dataclass
class ChatResponse:
    text: str
    source: str
    intent: str = ""
    facts: list = field(default_factory=list)     # what the answer was based on (shown on request)


def _has(q: str, phrase: str) -> bool:
    """SRS: the question "contains" the keyword. It must start at a word boundary, so
    "fine" does not match "define", but may continue ("my purchase" matches "my purchases")."""
    return re.search(rf"(?<![a-z]){re.escape(phrase)}", q) is not None


class ChatbotService:
    def __init__(self, fs, rag, llm):
        self.fs = fs
        self.rag = rag
        self.llm = llm

    # ---------------------------------------------------------------- main entry
    def ask(self, session, question: str) -> ChatResponse:
        q = (question or "").strip()
        if not q:                                        # UC-12 E4 (Send is disabled anyway)
            return ChatResponse("", NONE)
        session.refresh()
        role = session.role
        available = self.llm.is_available()              # D-16: checked BEFORE classifying
        intent = self.classify_intent(q, use_llm=available)

        if not self.is_permitted(role, intent):          # R14 -> UC-12 E1 / E2
            text = STORE_ONLY_TEXT if (role == rules.VISITOR and intent == rules.GENERAL) else NOT_PERMITTED_TEXT
            return self._log(session, q, ChatResponse(text, DENIED, intent))

        if intent == rules.ADMIN:                        # UC-13
            facts, understood = self.admin_context(q)
            if not understood:                           # UC-13 E3
                return self._log(session, q, ChatResponse(
                    "I'm not sure which admin data you mean. You can ask, for example:\n"
                    + "\n".join("• " + e for e in ADMIN_EXAMPLES), ADMIN_SRC, intent))
            if not available:                            # UC-13 E2: facts as a plain table
                return self._log(session, q, ChatResponse(
                    "The assistant is offline, so here are the computed facts:\n" + self.table_text(facts),
                    ADMIN_SRC, intent, facts))
            source = ADMIN_SRC
        else:
            if not available:                            # UC-12 E3 (Petri net T4)
                return self._log(session, q, ChatResponse(OFFLINE_TEXT, ERROR, intent))
            facts = self.rag.retrieve(q, {PUBLIC}, k=4)
            if intent == rules.ACCOUNT:
                facts = facts + self.account_context(session.user)
            source = RAG if facts else GENERAL_SRC

        if source == GENERAL_SRC and role == rules.VISITOR:   # D-17: P10 "store questions only"
            return self._log(session, q, ChatResponse(STORE_ONLY_TEXT, DENIED, intent))
        try:
            text = self.llm.generate(self.build_prompt(q, facts, role), task="answer",
                                     context=facts, question=q)
        except LLMUnavailable:                           # Ollama stopped mid-session
            return self._log(session, q, ChatResponse(OFFLINE_TEXT, ERROR, intent))
        return self._log(session, q, ChatResponse(text, source, intent, facts))

    # ---------------------------------------------------------------- steps
    def classify_intent(self, question: str, use_llm: bool = True) -> str:
        q = question.lower()
        if any(_has(q, w) for w in ADMIN_WORDS):
            return rules.ADMIN
        if any(_has(q, w) for w in ACCOUNT_WORDS):
            return rules.ACCOUNT
        if any(_has(q, w) for w in STORE_WORDS) or self._mentions_catalog(q):
            return rules.STORE
        if not use_llm:                                  # D-16: offline -> keyword rules only
            return rules.GENERAL
        hint = self.rag.retrieve(question, {PUBLIC}, k=1) if self.llm.is_mock else []   # A-27
        try:
            label = self.llm.generate("Classify as STORE or GENERAL: " + question, max_tokens=3,
                                      task="classify", context=hint, question=question)
        except LLMUnavailable:
            return rules.GENERAL
        return rules.STORE if "STORE" in label.upper() else rules.GENERAL

    def _mentions_catalog(self, q: str) -> bool:
        """"q mentions a catalog title/author/category" (SRS 4.20)."""
        for b in self.fs.load("books"):
            if any(_has(q, x.lower()) for x in (b["title"], b["author"], b["category"])):
                return True
        return False

    @staticmethod
    def is_permitted(role: str, intent: str) -> bool:
        return intent in rules.CHAT_PERMITTED.get(role, set())

    @staticmethod
    def build_prompt(question: str, facts: list[str], role: str) -> str:
        sys = "You are the BookOrbit AI store assistant. Answer in at most 120 words. "
        if facts:
            sys += ("Use ONLY the facts below. If they do not answer, say you don't know.\n"
                    + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)) + "\n")
        if role != rules.SU:
            sys += "Never reveal other customers' data."
        return sys + "\nQuestion: " + question

    def account_context(self, user: dict) -> list[str]:
        """The asking customer's own facts only (R14: "their own account")."""
        u = self.fs.find("users", "user_id", user["user_id"])
        titles = {b["book_id"]: b["title"] for b in self.fs.load("books")}
        mine = sorted((p for p in self.fs.load("purchases") if p["user_id"] == u["user_id"]),
                      key=lambda p: (p["timestamp"], p["purchase_id"]), reverse=True)[:5]
        recent = ", ".join(titles.get(p["book_id"], "?") for p in mine) or "none"
        return [f"Your balance: ${u['balance']:.2f}",
                f"Your role: {'VIP Customer' if u['role'] == rules.VC else 'Registered Customer'} ({u['role']})",
                f"Your account status: {u['status']}",
                f"Your warnings: {u['warnings']}",
                f"Your recent purchases: {recent}"]

    def admin_context(self, question: str) -> tuple[list[str], bool]:
        """UC-13 step 3: facts computed from the files, never invented by the LLM.
        Returns (facts, understood). understood=False when the question matches none of
        the fact topics (UC-13 E3, A-13)."""
        users = self.fs.load("users")
        customers = [u for u in users if u["role"] in rules.CUSTOMER_ROLES]
        month = clock.now()[:7]                                        # "YYYY-MM"
        sales = [p for p in self.fs.load("purchases") if p["timestamp"].startswith(month)]
        warnings = [w for w in self.fs.load("warnings") if w["timestamp"].startswith(month)]
        books = self.fs.load("books")

        def titles(status):
            return ", ".join(sorted(b["title"] for b in books if b["list_status"] == status)) or "none"

        suspended = [f"{u['username']} ({u['full_name']})" for u in users if u["status"] == rules.SUSPENDED]
        facts = {
            "suspended": "Suspended accounts: " + (", ".join(suspended) or "none"),
            "roles": (f"Customers by role: {sum(u['role'] == rules.RC for u in customers)} Registered, "
                      f"{sum(u['role'] == rules.VC for u in customers)} VIP"),
            "balances": f"Total customer balances: ${sum(u['balance'] for u in customers):.2f}",
            "sales": f"Sales this month ({month}): ${sum(p['price_paid'] for p in sales):.2f} from {len(sales)} purchase(s)",
            "warnings": f"Warnings this month ({month}): {len(warnings)}",
            "no_order": "No-Order List: " + titles(rules.LIST_NO_ORDER),
            "to_order": "To-Order List: " + titles(rules.LIST_TO_ORDER),
        }
        q = question.lower()
        hit = {k for k, words in ADMIN_TOPICS.items() if any(w in q for w in words)}
        if not hit & {"no_order", "to_order"} and any(w in q for w in BOTH_LISTS):
            hit |= {"no_order", "to_order"}
        relevant = [facts[k] for k in ADMIN_TOPICS if k in hit]
        return (relevant, True) if relevant else (list(facts.values()), False)

    @staticmethod
    def table_text(facts: list[str]) -> str:
        return "\n".join("• " + f for f in facts)

    def _log(self, session, question: str, resp: ChatResponse) -> ChatResponse:
        """UC-12 step 7: every answered question is appended to chat_log.txt."""
        with self.fs.lock:
            self.fs.append("chat_log", {
                "msg_id": self.fs.next_id("chat_log", "M"),
                "user_id": session.user["user_id"] if session.user else None,
                "session_id": session.session_id, "role": session.role, "question": question,
                "answer": resp.text, "source": resp.source, "timestamp": clock.now()})
        return resp
