"""MainWindow - navy role-based sidebar + content area (SRS 4.24, Section 5)."""
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from bookorbit import rules
from bookorbit.app_context import start_ai_indexing
from bookorbit.services.session import Session
from bookorbit.ui import screens
from bookorbit.ui.widgets import BG, FONT, NAVY, NAVY_HI, ORANGE, setup_styles

ROLE_NAMES = {rules.VISITOR: "Visitor", rules.RC: "Registered Customer",
              rules.VC: "VIP Customer", rules.SU: "Super-User"}

# Sidebar items per role (SRS 4.24 MainWindow.build_sidebar). Each maps to (screen, kwargs).
# Screens not built yet open a clearly marked placeholder naming the phase that adds them.
SIDEBAR = {
    rules.VISITOR: [("Home", "home", {}), ("Browse", "catalog", {}),
                    ("Search", "catalog", {"focus_search": True}), ("Top Books", "home", {}),
                    ("AI Chatbot", "chat", {}),
                    ("Sign In", "login", {}), ("Register", "register", {})],
    rules.RC: [("Home", "home", {}), ("Browse", "catalog", {}),
               ("Recommendations", "recommendations", {}),
               ("My Orders", "orders", {}), ("My Reviews", "my_reviews", {}),
               ("My Balance", "wallet", {}),
               ("AI Chatbot", "chat", {}),
               ("Sign Out", "logout", {})],
    rules.SU: [("Home", "home", {}),
               ("Manage Books", "placeholder", {"title": "Manage Books", "phase": 4, "uc": "UC-15"}),
               ("Manage Taboo Words", "placeholder", {"title": "Manage Taboo Words", "phase": 4, "uc": "UC-16"}),
               ("User Management", "placeholder", {"title": "User Management", "phase": 4, "uc": "UC-17"}),
               ("Reports", "placeholder", {"title": "Reports", "phase": 4, "uc": "UC-18"}),
               ("AI Chatbot", "chat", {}),
               ("Sign Out", "logout", {})],
}
SIDEBAR[rules.VC] = SIDEBAR[rules.RC]
WALLET_ONLY = [("My Balance", "wallet", {}), ("Sign Out", "logout", {})]   # R8

SCREENS = {
    "home": screens.HomeScreen, "catalog": screens.CatalogScreen, "book": screens.BookDetailScreen,
    "login": screens.LoginScreen, "register": screens.RegisterScreen, "wallet": screens.WalletScreen,
    "orders": screens.OrdersScreen, "my_reviews": screens.MyReviewsScreen,
    "recommendations": screens.RecommendationsScreen, "chat": screens.ChatScreen, "companion": screens.CompanionScreen,
    "placeholder": screens.PlaceholderScreen,
}


class MainWindow(tk.Tk):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.session = Session(ctx.fs)          # starts as a Visitor
        self.flash = None                       # (text, kind) shown by the next screen
        self.current = None
        self.active = "Home"                    # highlighted sidebar item
        self.title("BookOrbit AI")
        self.geometry("1200x800")
        self.minsize(1100, 720)
        self.configure(bg=BG)
        setup_styles(self)
        self.sidebar = tk.Frame(self, bg=NAVY, width=210)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.content = ttk.Frame(self, padding=20)
        self.content.pack(side="left", fill="both", expand=True)
        # SRS 4.24: build the AI indexes in a background thread; the sidebar shows
        # "Preparing AI index..." (the splash text) until they are ready.
        self.indexer = start_ai_indexing(ctx)
        self.build_sidebar()
        self.show("home")
        self.after(300, self._poll_ai)

    # ---------------------------------------------------------------- sidebar
    def build_sidebar(self, active: str = "Home") -> None:
        self.active = active
        for w in self.sidebar.winfo_children():
            w.destroy()
        tk.Label(self.sidebar, text="BookOrbit AI", bg=NAVY, fg="white",
                 font=(FONT, 18, "bold"), pady=18).pack(fill="x")
        s = self.session
        who = (f"{s.user['full_name']}\n{ROLE_NAMES[s.role]}" if s.user else "Browsing as Visitor")
        if s.wallet_only:
            who += "\nSUSPENDED"
        tk.Label(self.sidebar, text=who, bg=NAVY, fg=ORANGE if s.role == rules.VC else "#c9d1e3",
                 font=(FONT, 11), justify="left", anchor="w", padx=18).pack(fill="x", pady=(0, 12))
        items = WALLET_ONLY if s.wallet_only else SIDEBAR[s.role]
        for label, screen, kwargs in items:
            bg = NAVY_HI if label == active else NAVY
            btn = tk.Label(self.sidebar, text=label, bg=bg, fg="white", font=(FONT, 13),
                           anchor="w", padx=18, pady=8, cursor="hand2")
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda _e, l=label, sc=screen, kw=kwargs: self._nav(l, sc, kw))
        # Which AI parts are real and which are mocked (CLAUDE.md: label every MOCK in the UI)
        modes = [self.ai_status_text(), self.ctx.llm.mode_label]
        if self.ctx.bio.is_mock:
            modes.append("MOCK biometrics")
        tk.Label(self.sidebar, text="\n".join(m for m in modes if m) + "\n(see docs/ASSUMPTIONS.md)", bg=NAVY,
                 fg="#8f9bb8", font=(FONT, 10), justify="left", padx=18, wraplength=180).pack(
            side="bottom", anchor="w", pady=12)

    def ai_status_text(self) -> str:
        if not self.ctx.ai_ready.is_set():
            return "⏳ Preparing AI index…"
        if not self.ctx.rag.ready:
            return "AI index unavailable (model offline)"
        return ""

    def _poll_ai(self) -> None:
        """Redraw the sidebar once the background indexing has finished."""
        if self.ctx.ai_ready.is_set():
            self.build_sidebar(self.active)
            if hasattr(self.current, "on_ai_ready"):     # e.g. enable the camera button (UC-04)
                self.current.on_ai_ready()
        else:
            self.after(300, self._poll_ai)

    def _nav(self, label, screen, kwargs):
        if screen == "logout":
            self.on_logout()
            return
        self.build_sidebar(active=label)
        self.show(screen, **kwargs)

    # ---------------------------------------------------------------- screens
    def show(self, name: str, **kwargs) -> None:
        # R8: a suspended customer may only use the wallet
        if self.session.wallet_only and name != "wallet":
            name, kwargs = "wallet", {}
        for w in self.content.winfo_children():
            w.destroy()
        screen = SCREENS[name](self.content, self, **kwargs)
        screen.pack(fill="both", expand=True)
        screen.render()
        self.current = screen

    def set_flash(self, text: str, kind: str = "info") -> None:
        self.flash = (text, kind)

    def refresh_chrome(self) -> None:
        """Re-read the user and redraw the sidebar after a role/status change
        (R5 promotion, R10 demotion, R7/R10 suspension -> wallet-only mode)."""
        self.session.refresh()
        self.build_sidebar("My Balance" if self.session.wallet_only else self.active)

    def run_async(self, work, on_done) -> None:
        """Run a slow AI call in a worker thread so the window stays responsive
        (SRS 4.24: "run in worker thread; GUI stays responsive"). on_done(result, error)
        is called back on the Tk thread. The UI smoke test replaces this with a direct call."""
        box = queue.Queue()

        def worker():
            try:
                box.put((work(), None))
            except Exception as e:                       # shown in the screen's banner
                box.put((None, e))

        def poll():
            try:
                result, error = box.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            on_done(result, error)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    # Dialogs go through these two methods so the UI smoke test can answer them.
    def confirm(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message, parent=self)

    def inform(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self)

    def on_login(self, session) -> None:
        self.session = session
        self.set_flash(f"Welcome, {session.user['full_name']}!", "ok")
        if session.wallet_only:   # UC-02 E4
            self.set_flash("Your account is SUSPENDED: only My Balance is available. Deposit until your "
                           "balance is at least $0.00, then a Super-User can reactivate you (R8).", "warn")
        self.build_sidebar("My Balance" if session.wallet_only else "Home")
        self.show("home")

    def on_logout(self) -> None:
        self.ctx.auth.logout(self.session)
        self.set_flash("You have signed out.", "info")
        self.build_sidebar()
        self.show("home")
