"""Screens (SRS 4.24). Screens only display data and forward actions to
services; every handler catches the service's named error and shows its
message in the banner. No business rules live here."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from bookorbit import rules
from bookorbit.ai.biometrics import FACE, VOICE
from bookorbit.errors import (CompanionError, LoginError, ModelUnavailable, NoFaceError, NotFound, NoVoiceError, PurchaseError, RegistrationError,
                              TemplateMissingError)
from bookorbit.services.catalog import FIELDS
from bookorbit.ui.widgets import (CARD, FONT, GREEN, MUTED, NAVY, RED, Banner, BookCard, ScrollFrame, draw_cover,
                                  Tooltip, stars)

COVER_TIP_WAIT = "Cover search is starting: the cover index is still being built."
COVER_TIP_OFF = "Cover-image search is disabled: the image model is not loaded (UC-04 E5)."


def cover_button(parent, ctx, on_click):
    """The camera button of UC-04. Disabled with a tooltip while the cover index is being
    built or when the image model is missing (E5); text search always works."""
    cam = ttk.Button(parent, text="📷 Cover", command=on_click)
    tip = Tooltip(cam, "")
    sync_cover_button(cam, tip, ctx)
    return cam, tip


def sync_cover_button(cam, tip, ctx):
    if ctx.covers.ready:
        cam.configure(state="normal")
        tip.text = "Search by a photo of a book cover (JPG or PNG)." + (
            " " + ctx.covers.mode_label + "." if ctx.covers.is_mock else "")
    else:
        cam.configure(state="disabled")
        tip.text = COVER_TIP_WAIT if not ctx.ai_ready.is_set() else COVER_TIP_OFF


def pick_cover_photo(data_dir) -> str:
    """Choose the photo to search with ("All files" too, so UC-04 E3 can be shown)."""
    initial = Path(data_dir) / "samples" / "covers"
    return filedialog.askopenfilename(title="Choose a photo of a book cover",
                                      filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
                                      initialdir=str(initial if initial.exists() else data_dir))


class Screen(ttk.Frame):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent)
        self.app, self.ctx, self.kwargs = app, app.ctx, kwargs
        self.images = []
        self.banner = Banner(self)
        self.banner.pack(fill="x")

    @property
    def session(self):
        return self.app.session

    def render(self):
        if self.app.flash:
            self.banner.show(*self.app.flash)
            self.app.flash = None
        self.build()

    def build(self):
        raise NotImplementedError

    def open_book(self, book_id):
        self.app.show("book", book_id=book_id)


def search_bar(parent, ctx, on_search, on_cover, initial=""):
    """Search box + camera button used on Home and Catalog (UC-04)."""
    row = ttk.Frame(parent)
    entry = ttk.Entry(row, width=48, font=(FONT, 13))
    entry.insert(0, initial)
    entry.pack(side="left", ipady=4)
    entry.bind("<Return>", lambda _e: on_search(entry.get()))
    ttk.Button(row, text="Search", style="Primary.TButton",
               command=lambda: on_search(entry.get())).pack(side="left", padx=6)
    cam, tip = cover_button(row, ctx, on_cover)
    cam.pack(side="left")
    return row, entry, (cam, tip)


# ---------------------------------------------------------------- Home (UC-03, UC-06)
class HomeScreen(Screen):
    def build(self):
        ttk.Label(self, text="Discover Your Next Favorite Book", style="H1.TLabel").pack(anchor="w")
        ttk.Label(self, text="Search by title, author, keyword or year.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        row, _, self.cam = search_bar(self, self.ctx, lambda q: self.app.show("catalog", query=q, field="title"),
                                      self.on_cover)
        row.pack(anchor="w", pady=(0, 18))

        if self.session.role == rules.VC:
            tk.Label(self, text="👑  VIP Member - you receive a 10% discount on all purchases (R6)",
                     bg="#fff4d6", fg="#7a5200", font=(FONT, 13, "bold"), anchor="w",
                     padx=12, pady=8).pack(fill="x", pady=(0, 14))

        title, books = self.ctx.recs.home_books(self.session)
        ttk.Label(self, text=title, style="H2.TLabel").pack(anchor="w")
        if self.session.is_customer:                     # UC-06
            note = ("Based on the books you bought and viewed (R4)." if title == "Recommended for You" else
                    "View or buy a few books and we'll recommend more like them (UC-06 E1).")
            ttk.Label(self, text=note, style="Muted.TLabel").pack(anchor="w")
        cards = ttk.Frame(self)
        cards.pack(anchor="w", pady=10)
        if not books:
            ttk.Label(cards, text="No books available yet", style="Muted.TLabel").pack()  # UC-03 E2
        for b in books:
            BookCard(cards, b, self.open_book, self.images, self.ctx.fs.resolve(b["cover_path"])).pack(side="left", padx=(0, 14))

        if self.session.is_customer:
            box = ttk.Frame(self, style="Card.TFrame", padding=14)
            box.pack(anchor="w", pady=10)
            ttk.Label(box, text="Account Balance", style="Card.TLabel", font=(FONT, 13, "bold")).pack(anchor="w")
            bal = self.ctx.wallet.get_balance(self.session.user["user_id"])
            ttk.Label(box, text=f"${bal:,.2f}", style="Card.TLabel", font=(FONT, 22, "bold")).pack(anchor="w")
            ttk.Button(box, text="Open My Balance", command=lambda: self.app.show("wallet")).pack(anchor="w", pady=4)

    def on_cover(self):
        path = pick_cover_photo(self.ctx.fs.dir)
        if path:
            self.app.show("catalog", cover_file=path)

    def on_ai_ready(self):
        sync_cover_button(*self.cam, self.ctx)


# ---------------------------------------------------------------- Recommendations (UC-06, R4)
class RecommendationsScreen(Screen):
    def build(self):
        ttk.Label(self, text="Recommendations", style="H1.TLabel").pack(anchor="w")
        if not self.session.is_customer:
            ttk.Label(self, text="Recommendations are for signed-in customers.", style="Muted.TLabel").pack(anchor="w")
            return
        uid = self.session.user["user_id"]
        title, books = self.ctx.recs.home_books(self.session)
        profile = self.ctx.recs.build_profile(uid)
        ttk.Label(self, text=title, style="H2.TLabel").pack(anchor="w", pady=(8, 0))
        if not profile:
            ttk.Label(self, text="No history yet: these are popular books. View or buy a few books and "
                                 "we'll recommend more like them (UC-06 E1).", style="Muted.TLabel").pack(anchor="w")
        cards = ttk.Frame(self)
        cards.pack(anchor="w", pady=10)
        for b in books:
            col = ttk.Frame(cards)
            col.pack(side="left", padx=(0, 14), anchor="n")
            BookCard(col, b, self.open_book, self.images, self.ctx.fs.resolve(b["cover_path"])).pack()
            why = self.ctx.recs.reasons(b, profile)
            ttk.Label(col, text=("Matches: " + ", ".join(why)) if why else "Popular pick",
                      style="Muted.TLabel", wraplength=146, font=(FONT, 10)).pack(anchor="w", pady=(4, 0))
        if profile:
            ttk.Label(self, text="Your interests", style="H2.TLabel").pack(anchor="w", pady=(10, 2))
            ttk.Label(self, text=f"Each purchase adds {rules.PROFILE_W_BUY} points and each view "
                                 f"{rules.PROFILE_W_VIEW} point to the book's category, author and keywords (R4).",
                      style="Muted.TLabel").pack(anchor="w")
            tree = ttk.Treeview(self, columns=("term", "points"), show="headings", height=8)
            tree.heading("term", text="Interest")
            tree.heading("points", text="Points")
            tree.column("term", width=320)
            tree.column("points", width=90, anchor="e")
            kinds = {"cat": "Category", "auth": "Author", "kw": "Keyword"}
            for term, pts in profile.most_common(8):
                kind, value = term.split(":", 1)
                tree.insert("", "end", values=(f"{kinds[kind]}: {value}", pts))
            tree.pack(anchor="w")


# ---------------------------------------------------------------- Catalog (UC-04)
class CatalogScreen(Screen):
    def build(self):
        self.page = 1
        self.results = []
        ttk.Label(self, text="Browse & Search", style="H1.TLabel").pack(anchor="w", pady=(0, 8))

        controls = ttk.Frame(self)
        controls.pack(fill="x")
        ttk.Label(controls, text="Category").grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="Search in").grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(controls, text="Query (year: 1990 or 1990-2000)").grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Label(controls, text="Sort").grid(row=0, column=3, sticky="w", padx=(10, 0))
        self.category = ttk.Combobox(controls, state="readonly", width=16,
                                     values=["All categories"] + self.ctx.catalog.categories())
        self.category.set(self.kwargs.get("category") or "All categories")
        self.category.grid(row=1, column=0)
        self.field = ttk.Combobox(controls, state="readonly", width=9, values=list(FIELDS))
        self.field.set(self.kwargs.get("field", "title"))
        self.field.grid(row=1, column=1, padx=(10, 0))
        self.query = tk.Entry(controls, width=30, font=(FONT, 13), highlightthickness=2,
                              highlightbackground="#cfd5e1", highlightcolor=NAVY)
        self.query.insert(0, self.kwargs.get("query", ""))
        self.query.grid(row=1, column=2, padx=(10, 0), ipady=3)
        self.query.bind("<Return>", lambda _e: self.run_search())
        self.sort = ttk.Combobox(controls, state="readonly", width=12,
                                 values=["title", "price", "weighted_avg", "pub_year"])
        self.sort.set("title")
        self.sort.grid(row=1, column=3, padx=(10, 0))
        ttk.Button(controls, text="Search", style="Primary.TButton",
                   command=self.run_search).grid(row=1, column=4, padx=(10, 0))
        ttk.Button(controls, text="Clear filters", command=self.clear).grid(row=1, column=5, padx=(6, 0))
        self.cam = cover_button(controls, self.ctx, self.on_cover)
        self.cam[0].grid(row=1, column=6, padx=(6, 0))
        for cb in (self.category, self.sort):
            cb.bind("<<ComboboxSelected>>", lambda _e: self.run_search())

        self.status = ttk.Label(self, text="", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(10, 4))
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(anchor="w", fill="both", expand=True)
        pager = ttk.Frame(self)
        pager.pack(fill="x", pady=(6, 0))
        self.prev_btn = ttk.Button(pager, text="‹ Prev", command=lambda: self.go(-1))
        self.prev_btn.pack(side="left")
        self.page_label = ttk.Label(pager, text="")
        self.page_label.pack(side="left", padx=10)
        self.next_btn = ttk.Button(pager, text="Next ›", command=lambda: self.go(1))
        self.next_btn.pack(side="left")
        if self.kwargs.get("focus_search"):
            self.query.focus_set()
        self.scores, self.cover_name = {}, None
        if self.kwargs.get("cover_file"):            # camera button pressed on Home
            self.run_cover_search(self.kwargs["cover_file"])
        else:
            self.run_search()

    # ---- cover search (UC-04 step 4, E3-E5)
    def on_cover(self):
        path = pick_cover_photo(self.ctx.fs.dir)
        if path:
            self.run_cover_search(path)

    def on_ai_ready(self):
        sync_cover_button(*self.cam, self.ctx)

    def run_cover_search(self, path):
        self.banner.clear()
        try:
            data = Path(path).read_bytes()
            hits = self.ctx.catalog.search_by_cover(data)
        except ValueError as e:                  # E3: not a JPG / PNG
            self.banner.show(str(e), "error")
            return
        except (ModelUnavailable, OSError) as e:  # E5 / unreadable file
            self.banner.show(str(e), "error")
            return
        self.results = [b for b, _sim in hits]
        self.scores = {b["book_id"]: sim for b, sim in hits}
        self.cover_name = Path(path).name
        self.page = 1
        self.draw()

    def clear(self):
        self.category.set("All categories")
        self.field.set("title")
        self.query.delete(0, "end")
        self.run_search()

    def run_search(self):
        self.banner.clear()
        self.scores, self.cover_name = {}, None
        self.query.configure(highlightbackground="#cfd5e1")
        cat = None if self.category.get() == "All categories" else self.category.get()
        q = self.query.get()
        try:
            if q.strip():
                self.results = self.ctx.catalog.search(q, self.field.get(), category=cat)
                if self.sort.get() != "title":   # search keeps best-match order unless a sort is picked
                    from bookorbit.services.catalog import SORT_KEYS
                    key, rev = SORT_KEYS[self.sort.get()]
                    self.results.sort(key=key, reverse=rev)
            else:
                self.results = self.ctx.catalog.browse(cat, self.sort.get())
        except ValueError as e:                  # UC-04 E2: invalid year range
            self.query.configure(highlightbackground=RED)
            self.banner.show(str(e), "error")
            self.results = []
        self.page = 1
        self.draw()

    def go(self, delta):
        self.page += delta
        self.draw()

    def draw(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.images.clear()
        total = len(self.results)
        pages = max(1, -(-total // rules.PAGE_SIZE))
        self.page = min(max(1, self.page), pages)
        if total == 0:                           # UC-04 E1 (and E4 for a cover photo)
            box = ttk.Frame(self.grid_frame, padding=30)
            box.pack()
            ttk.Label(box, text="No matching cover found" if self.cover_name else "No books found",
                      style="H2.TLabel").pack()
            ttk.Button(box, text="Clear filters", command=self.clear).pack(pady=8)
        for i, b in enumerate(self.ctx.catalog.page(self.results, self.page)):
            cell = ttk.Frame(self.grid_frame)
            cell.grid(row=i // 6, column=i % 6, padx=(0, 12), pady=(0, 12), sticky="n")
            BookCard(cell, b, self.open_book, self.images, self.ctx.fs.resolve(b["cover_path"])).pack()
            if b["book_id"] in self.scores:        # cover search: show how similar each cover is
                ttk.Label(cell, text=f"{self.scores[b['book_id']]:.0%} similar", style="Muted.TLabel").pack()
        if self.cover_name:
            mock = f"  ({self.ctx.covers.mode_label})" if self.ctx.covers.is_mock else ""
            self.status.configure(text=f"Cover search with {self.cover_name}: {total} match(es), "
                                       f"most similar first{mock}")
        else:
            self.status.configure(text=f"{total} book(s) found")
        self.page_label.configure(text=f"Page {self.page} of {pages}")
        self.prev_btn.configure(state="normal" if self.page > 1 else "disabled")
        self.next_btn.configure(state="normal" if self.page < pages else "disabled")


# ---------------------------------------------------------------- Buy Now, shared (UC-08, UC-09)
class BuyMixin:
    """Buy Now dialog + receipt, used by the book page and the Reading Companion (UC-14 E2)."""

    def after_buy(self, book_id):
        """Where to go after a purchase attempt (the book page by default)."""
        self.app.show("book", book_id=book_id)

    def on_buy(self, book):
        self.banner.clear()
        try:
            q = self.ctx.purchases.quote(self.session, book["book_id"])   # fresh price (UC-09 E1)
        except (PermissionError, PurchaseError) as e:                     # E4 / book gone
            self.banner.show(str(e), "error")
            return
        p = q.price
        lines = [f"Buy \"{book['title']}\"?", "", f"List price:     ${p.list:.2f}"]
        if p.discount > 0:
            lines.append(f"VIP discount:  -${p.discount:.2f} (10%)")
        lines += [f"You pay:        ${p.paid:.2f}", f"Your balance:  ${q.balance:.2f}"]
        if q.insufficient:                     # decision A-20: warn before the R7 fine is charged
            lines += ["", f"⚠ Your balance is too low. If you confirm, the purchase is rejected and a "
                          f"${rules.FINE_AMOUNT:.2f} fine is charged (R7)."]
            if q.fine_would_suspend:
                lines.append("The fine would take your balance below $0.00, so your account would be SUSPENDED.")
        if not self.app.confirm("Confirm purchase", "\n".join(lines)):
            return                                                         # E5: nothing changes
        try:
            r = self.ctx.purchases.purchase(self.session, book["book_id"])
        except PurchaseError as e:                                         # E1 / E2 / E3
            self.app.set_flash(str(e), "error")
            self.app.refresh_chrome()          # E2: suspended -> wallet-only sidebar
            self.after_buy(book["book_id"])  # redirected to the wallet if suspended
            return
        except PermissionError as e:
            self.banner.show(str(e), "error")
            return
        receipt = [f"Receipt - {r.title}", "", f"List price:     ${r.list_price:.2f}"]
        if r.discount > 0:
            receipt.append(f"VIP discount:  -${r.discount:.2f} (VIP -10%)")
        receipt += [f"Amount paid:   ${r.paid:.2f}", f"New balance:    ${r.balance:.2f}"]
        if r.promoted:                         # R5; the discount starts next time (R6, UC-09 E2)
            receipt += ["", "👑 You are now a VIP Customer! Your 10% discount starts with your next purchase."]
        self.app.inform("Purchase complete", "\n".join(receipt))
        self.app.set_flash(f"You bought \"{r.title}\" for ${r.paid:.2f}."
                           + (" You are now a VIP Customer!" if r.promoted else ""), "ok")
        self.app.refresh_chrome()
        self.after_buy(book["book_id"])


# ---------------------------------------------------------------- Book details (UC-05)
class BookDetailScreen(BuyMixin, Screen):
    def build(self):
        try:
            book = self.ctx.catalog.get_details(self.kwargs["book_id"], self.session)
        except NotFound as e:                    # UC-05 E1
            self.app.set_flash(f"{e} - returning to the catalog.", "error")
            self.after(1, lambda: self.app.show("catalog"))
            return
        ttk.Button(self, text="‹ Back to Browse", command=lambda: self.app.show("catalog")).pack(anchor="w")

        top = ttk.Frame(self)
        top.pack(fill="x", pady=10)
        draw_cover(top, book, self.ctx.fs.resolve(book["cover_path"]), self.images).pack(side="left", anchor="n")

        info = ttk.Frame(top, padding=(18, 0))
        info.pack(side="left", fill="both", expand=True)
        ttk.Label(info, text=book["title"], style="H1.TLabel").pack(anchor="w")
        ttk.Label(info, text=f"{book['author']}  ·  {book['category']}  ·  {book['pub_year']}",
                  style="Muted.TLabel").pack(anchor="w")
        rating = (f"{stars(book['weighted_avg'])}  {book['weighted_avg']:.2f} weighted average "
                  f"({book['rating_count']} ratings)" if book["rating_count"] else "No ratings yet")
        ttk.Label(info, text=rating, foreground="#b7791f").pack(anchor="w", pady=(4, 0))
        price_row = ttk.Frame(info)
        price_row.pack(anchor="w", pady=4)
        ttk.Label(price_row, text=f"${book['display_price']:.2f}", font=(FONT, 20, "bold")).pack(side="left")
        if book["vip_discount"] > 0:                       # UC-09: VIP price, list price struck through
            ttk.Label(price_row, text=f"${book['price']:.2f}", style="Muted.TLabel",
                      font=(FONT, 13, "overstrike")).pack(side="left", padx=(8, 0))
            ttk.Label(price_row, text="VIP -10%", foreground="#7a5200").pack(side="left", padx=(6, 0))
        ttk.Label(info, text=book["description"], wraplength=640, justify="left").pack(anchor="w")
        ttk.Label(info, text=f"Keywords: {book['keywords']}", style="Muted.TLabel").pack(anchor="w", pady=(4, 8))

        buttons = ttk.Frame(info)
        buttons.pack(anchor="w")
        self.review_form = None
        if self.session.is_customer:
            # Role-based buttons (UC-05 step 5).
            if book["owned"]:                              # UC-08 E3
                ttk.Label(buttons, text="✔ You own this book", foreground=GREEN,
                          font=(FONT, 13, "bold")).pack(side="left", padx=(0, 12))
            else:
                ttk.Button(buttons, text="Buy Now", style="Primary.TButton",
                           command=lambda: self.on_buy(book)).pack(side="left", padx=(0, 8))
            if book["my_review"]:                          # one review per book (A-09)
                ttk.Label(buttons, text="✔ You reviewed this book", foreground=GREEN).pack(side="left", padx=(0, 12))
            else:
                ttk.Button(buttons, text="Write Review", command=self.toggle_review_form).pack(side="left", padx=(0, 8))
            if book.get("text_path"):                      # UC-14, R15
                ttk.Button(buttons, text="📖 Reading Companion",
                           command=lambda: self.app.show("companion", book_id=book["book_id"])).pack(
                    side="left", padx=(0, 8))
            else:                                          # UC-14 E1
                comp = ttk.Button(buttons, text="📖 Reading Companion", state="disabled")
                comp.pack(side="left", padx=(0, 8))
                Tooltip(comp, "The Reading Companion isn't available for this book (no full text).")
            self.review_form = self.build_review_form(info, book)
        elif self.session.role == rules.VISITOR:
            ttk.Label(buttons, text="Sign in to buy, review or read this book.", style="Muted.TLabel").pack()

        ttk.Label(self, text=f"Reviews ({len(book['reviews'])})", style="H2.TLabel").pack(anchor="w", pady=(8, 4))
        if not book["reviews"]:
            ttk.Label(self, text="No reviews yet", style="Muted.TLabel").pack(anchor="w")   # UC-05 E2
            return
        sf = ScrollFrame(self, height=260)
        sf.pack(fill="both", expand=True)
        for r in book["reviews"]:
            card = tk.Frame(sf.inner, bg=CARD, highlightbackground="#d9dee8", highlightthickness=1,
                            padx=10, pady=6)
            card.pack(fill="x", pady=3, padx=(0, 6))
            head = f"{r['author']}   {stars(r['rating'])}   {r['timestamp'][:10]}"
            if r["verified_buyer"]:
                head += "   ✔ Verified buyer"
            tk.Label(card, text=head, bg=CARD, font=(FONT, 11, "bold"), anchor="w").pack(fill="x")
            tk.Label(card, text=r["display_text"], bg=CARD, anchor="w", justify="left",
                     wraplength=820).pack(fill="x")

    # ---- Write Review (UC-10, UC-11)
    def build_review_form(self, parent, book):
        form = ttk.Frame(parent, style="Card.TFrame", padding=12)
        ttk.Label(form, text="Your review", style="Card.TLabel", font=(FONT, 13, "bold")).pack(anchor="w")
        row = ttk.Frame(form, style="Card.TFrame")
        row.pack(anchor="w", pady=4)
        self.stars_var = tk.IntVar(value=0)
        for n in range(1, 6):
            ttk.Radiobutton(row, text="★" * n, value=n, variable=self.stars_var).pack(side="left", padx=(0, 10))
        self.review_text = tk.Text(form, width=70, height=4, font=(FONT, 12), wrap="word")
        self.review_text.pack(anchor="w")
        bottom = ttk.Frame(form, style="Card.TFrame")
        bottom.pack(fill="x", pady=(6, 0))
        self.char_count = ttk.Label(bottom, text=f"0 / {rules.REVIEW_MAX_CHARS}", style="Card.TLabel", foreground=MUTED)
        self.char_count.pack(side="left")
        self.review_text.bind("<KeyRelease>", lambda _e: self.char_count.configure(
            text=f"{len(self.review_text.get('1.0', 'end-1c').strip())} / {rules.REVIEW_MAX_CHARS}"))
        ttk.Button(bottom, text="Submit Review", style="Primary.TButton",
                   command=lambda: self.on_review(book)).pack(side="right")
        ttk.Label(form, text="Reviews are checked for taboo words: 1-3 are masked with ****, more than 3 "
                             "block the review and give you a warning (R9, R10).", style="Card.TLabel",
                  foreground=MUTED, wraplength=600).pack(anchor="w", pady=(6, 0))
        return form

    def toggle_review_form(self):
        if self.review_form.winfo_ismapped():
            self.review_form.pack_forget()
        else:
            self.review_form.pack(anchor="w", pady=(10, 0), fill="x")
            self.review_text.focus_set()

    def on_review(self, book):
        self.banner.clear()
        try:
            res = self.ctx.reviews.submit(self.session, book["book_id"], self.stars_var.get(),
                                          self.review_text.get("1.0", "end-1c"))
        except ValueError as e:                                            # E1: nothing stored
            self.banner.show(str(e), "error")
            return
        except PermissionError as e:                                       # E3
            self.banner.show(str(e), "error")
            return
        if res.status == rules.PUBLISHED:
            self.app.set_flash(res.message, "ok")
        else:                                                              # E2 -> UC-11
            self.app.set_flash(res.message, "error" if res.consequence else "warn")
        self.app.refresh_chrome()              # role/status may have changed (demoted / suspended)
        self.app.show("book", book_id=book["book_id"])


# ---------------------------------------------------------------- Sign in (UC-02)
def pick_sample(method: str, data_dir: str) -> str:
    """MOCK capture: choose a photo / WAV file instead of the camera / microphone."""
    types = ([("Photos", "*.png *.jpg *.jpeg")] if method == FACE else [("WAV audio", "*.wav")])
    initial = Path(data_dir) / "samples"
    return filedialog.askopenfilename(title=f"Choose a {method.lower()} sample", filetypes=types,
                                      initialdir=str(initial if initial.exists() else data_dir))


class LoginScreen(Screen):
    def build(self):
        card = ttk.Frame(self, style="Card.TFrame", padding=24)
        card.pack(pady=30)
        ttk.Label(card, text="Sign in to BookOrbit AI", style="Card.TLabel",
                  font=(FONT, 20, "bold")).pack()
        ttk.Label(card, text="Customers and Super-Users verify with a face or voice sample (R1).",
                  style="Card.TLabel", foreground=MUTED).pack(pady=(2, 10))
        if self.ctx.bio.is_mock:
            tk.Label(card, text=self.ctx.bio.mode_label + ".\nDemo files are in data/samples/ "
                     "(e.g. alice_face.png, alice_voice.wav).", bg="#fff4e0", fg="#8a5300",
                     font=(FONT, 11), justify="left", padx=8, pady=6).pack(fill="x", pady=(0, 10))
        ttk.Label(card, text="Username", style="Card.TLabel", font=(FONT, 12, "bold")).pack(anchor="w")
        self.username = ttk.Entry(card, width=36, font=(FONT, 13))
        self.username.insert(0, self.kwargs.get("username", ""))
        self.username.pack(anchor="w", pady=(0, 10))
        self.method = tk.StringVar(value=FACE)
        tabs = ttk.Frame(card, style="Card.TFrame")
        tabs.pack(anchor="w")
        for m, label in ((FACE, "Face"), (VOICE, "Voice")):
            ttk.Radiobutton(tabs, text=label, value=m, variable=self.method,
                            command=self._reset_file).pack(side="left", padx=(0, 12))
        self.file = None
        self.file_label = ttk.Label(card, text="No sample chosen", style="Card.TLabel", foreground=MUTED)
        ttk.Button(card, text="Choose sample file…", command=self.choose).pack(anchor="w", pady=(8, 2))
        self.file_label.pack(anchor="w")
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(anchor="w", pady=(12, 4))
        ttk.Button(row, text="Capture & Verify", style="Primary.TButton", command=self.on_submit).pack(side="left")
        self.attempt = ttk.Label(row, text="", style="Card.TLabel", foreground=MUTED)
        self.attempt.pack(side="left", padx=10)
        link = ttk.Label(card, text="No account? Register", style="Card.TLabel", foreground=NAVY, cursor="hand2")
        link.pack(pady=(8, 0))
        link.bind("<Button-1>", lambda _e: self.app.show("register"))

    def _reset_file(self):
        self.file = None
        self.file_label.configure(text="No sample chosen")

    def choose(self):
        path = pick_sample(self.method.get(), self.ctx.fs.dir)
        if path:
            self.file = path
            self.file_label.configure(text=Path(path).name)

    def on_submit(self):
        self.banner.clear()
        if not self.file:
            self.banner.show("Choose a sample first.", "error")
            return
        try:
            session = self.ctx.auth.login(self.username.get(), self.method.get(), Path(self.file).read_bytes())
        except LoginError as e:
            msg = {"UNKNOWN_USER": "No account with that username.",                       # E1
                   "NO_MATCH": f"Not recognised - try again (attempt "
                               f"{rules.MAX_LOGIN_FAILS - e.attempts_left} of {rules.MAX_LOGIN_FAILS}).",  # E2
                   "LOCKED": f"Too many failed attempts. This username is locked for "
                             f"{e.minutes_left} more minute(s)."}[e.kind]                   # E3
            self.banner.show(msg, "error")
            if e.kind == "NO_MATCH":
                self.attempt.configure(text=f"Attempt {rules.MAX_LOGIN_FAILS - e.attempts_left} of "
                                            f"{rules.MAX_LOGIN_FAILS}")
        except (NoFaceError, NoVoiceError) as e:                                            # E5, not counted
            self.banner.show(f"{e} (not counted as a failed attempt).", "warn")
        except TemplateMissingError as e:                                                    # E6
            self.banner.show(str(e), "error")
        except OSError as e:
            self.banner.show(f"Could not read the file: {e}", "error")
        else:
            self.app.on_login(session)


# ---------------------------------------------------------------- Register (UC-01)
class RegisterScreen(Screen):
    FIELDS = (("full_name", "Full name"), ("username", "Username (3-20 letters, digits, _)"),
              ("email", "Email"))

    def build(self):
        self.face_tries = 0
        card = ttk.Frame(self, style="Card.TFrame", padding=24)
        card.pack(pady=20)
        ttk.Label(card, text="Create an account", style="Card.TLabel", font=(FONT, 20, "bold")).pack(anchor="w")
        if self.ctx.bio.is_mock:
            tk.Label(card, text=self.ctx.bio.mode_label + ".\nTry data/samples/new_user_face.png and "
                     "new_user_voice.wav.", bg="#fff4e0", fg="#8a5300", font=(FONT, 11),
                     justify="left", padx=8, pady=6).pack(fill="x", pady=(6, 10))
        self.entries, self.errors = {}, {}
        for key, label in self.FIELDS:
            ttk.Label(card, text=label, style="Card.TLabel", font=(FONT, 12, "bold")).pack(anchor="w")
            e = tk.Entry(card, width=38, font=(FONT, 13), highlightthickness=2,
                         highlightbackground="#cfd5e1", highlightcolor=NAVY)
            e.pack(anchor="w")
            err = ttk.Label(card, text="", style="Error.TLabel", background=CARD)
            err.pack(anchor="w", pady=(0, 6))
            self.entries[key], self.errors[key] = e, err
        self.face = self.voice = None
        self.face_label = ttk.Label(card, text="Face photo: none", style="Card.TLabel", foreground=MUTED)
        self.voice_label = ttk.Label(card, text="Voice clip (optional): none", style="Card.TLabel", foreground=MUTED)
        ttk.Button(card, text="Capture Face (choose photo)…", command=lambda: self.choose(FACE)).pack(anchor="w")
        self.face_label.pack(anchor="w", pady=(0, 6))
        ttk.Button(card, text="Record Voice (choose WAV)…", command=lambda: self.choose(VOICE)).pack(anchor="w")
        self.voice_label.pack(anchor="w")
        self.errors["biometric"] = ttk.Label(card, text="", style="Error.TLabel", background=CARD)
        self.errors["biometric"].pack(anchor="w", pady=(0, 6))
        ttk.Button(card, text="Create account", style="Primary.TButton", command=self.on_submit).pack(anchor="w", pady=6)

    def choose(self, method):
        path = pick_sample(method, self.ctx.fs.dir)
        if not path:
            return
        if method == FACE:
            self.face = path
            self.face_label.configure(text=f"Face photo: {Path(path).name}")
        else:
            self.voice = path
            self.voice_label.configure(text=f"Voice clip: {Path(path).name}")

    def on_submit(self):
        self.banner.clear()
        for key, err in self.errors.items():
            err.configure(text="")
            if key in self.entries:
                self.entries[key].configure(highlightbackground="#cfd5e1")
        try:
            user = self.ctx.auth.register(
                self.entries["full_name"].get(), self.entries["username"].get(), self.entries["email"].get(),
                Path(self.face).read_bytes() if self.face else None,
                Path(self.voice).read_bytes() if self.voice else None)
        except RegistrationError as e:                       # E1 / E2: outline the invalid fields
            for key, reason in e.problems.items():
                self.errors[key].configure(text=reason)
                if key in self.entries:
                    self.entries[key].configure(highlightbackground=RED)
            self.banner.show("Please fix the highlighted fields. Nothing was saved.", "error")
        except (NoFaceError, NoVoiceError) as e:            # E3: retake, up to 3 tries
            self.face_tries += 1
            if self.face_tries >= rules.MAX_FACE_RETRIES:
                self.app.set_flash("Registration cancelled after 3 unsuccessful captures.", "error")
                self.app.show("home")
                return
            self.banner.show(f"{e} - please retake (try {self.face_tries} of {rules.MAX_FACE_RETRIES}).", "warn")
        except OSError as e:                                  # E5: write error, nothing kept
            self.banner.show(f"Could not create the account: {e}", "error")
        else:
            self.app.set_flash("Account created - please sign in.", "ok")
            self.app.build_sidebar("Sign In")
            self.app.show("login", username=user["username"])


# ---------------------------------------------------------------- My Balance (UC-07)
class WalletScreen(Screen):
    def build(self):
        if not self.session.is_customer:
            ttk.Label(self, text="My Balance is for customers.", style="H2.TLabel").pack(anchor="w")
            return
        self.session.refresh()
        u = self.session.user
        ttk.Label(self, text="My Balance", style="H1.TLabel").pack(anchor="w", pady=(0, 10))
        top = ttk.Frame(self)
        top.pack(fill="x")
        box = ttk.Frame(top, style="Card.TFrame", padding=16)
        box.pack(side="left", fill="y")
        ttk.Label(box, text="Current balance", style="Card.TLabel", foreground=MUTED).pack(anchor="w")
        bal = self.ctx.wallet.get_balance(u["user_id"])
        ttk.Label(box, text=f"${bal:,.2f}", style="Card.TLabel", font=(FONT, 28, "bold"),
                  foreground=RED if bal < 0 else "black").pack(anchor="w")
        status_color = RED if u["status"] == rules.SUSPENDED else "#1e8449"
        ttk.Label(box, text=f"Status: {u['status']}    Role: {u['role']}    Warnings: {u['warnings']}",
                  style="Card.TLabel", foreground=status_color).pack(anchor="w")
        dep = ttk.Frame(top, style="Card.TFrame", padding=16)
        dep.pack(side="left", fill="both", expand=True, padx=(12, 0))
        ttk.Label(dep, text="Add funds", style="Card.TLabel", font=(FONT, 13, "bold")).pack(anchor="w")
        row = ttk.Frame(dep, style="Card.TFrame")
        row.pack(anchor="w", pady=4)
        ttk.Label(row, text="$", style="Card.TLabel", font=(FONT, 13)).pack(side="left")
        self.amount = tk.Entry(row, width=12, font=(FONT, 13), highlightthickness=2,
                               highlightbackground="#cfd5e1", highlightcolor=NAVY)
        self.amount.pack(side="left", ipady=2)
        self.amount.bind("<Return>", lambda _e: self.on_deposit())
        ttk.Button(row, text="Add Funds", style="Primary.TButton", command=self.on_deposit).pack(side="left", padx=6)
        ttk.Label(dep, text=f"Fake money only - no payment gateway. Up to ${rules.MAX_DEPOSIT:,.0f} per deposit, "
                            "at most 2 decimals.", style="Card.TLabel", foreground=MUTED,
                  wraplength=420).pack(anchor="w")
        if u["status"] == rules.SUSPENDED:
            ok, why = self.ctx.status.can_reopen(u)        # R8
            text = ("Your balance is $0.00 or more: a Super-User can now reactivate your account (R8)."
                    if ok else f"Suspended: {why}; then a Super-User can reactivate your account (R8).")
            ttk.Label(dep, text=text, style="Card.TLabel", foreground=GREEN if ok else RED,
                      wraplength=420).pack(anchor="w", pady=(4, 0))

        ttk.Label(self, text="Ledger", style="H2.TLabel").pack(anchor="w", pady=(16, 4))
        tree = ttk.Treeview(self, columns=("date", "type", "desc", "amount", "balance"), show="headings", height=12)
        for col, label, w in (("date", "Date", 170), ("type", "Type", 100), ("desc", "Description", 320),
                              ("amount", "Amount", 110), ("balance", "Balance", 110)):
            tree.heading(col, text=label)
            tree.column(col, width=w, anchor="w")
        for t in self.ctx.wallet.get_ledger(u["user_id"]):
            tree.insert("", "end", values=(t["timestamp"], t["type"], t["note"],
                                           f"{t['amount']:+,.2f}", f"{t['balance_after']:,.2f}"))
        tree.pack(fill="x")

    def on_deposit(self):
        self.banner.clear()
        try:
            res = self.ctx.wallet.deposit(self.session, self.amount.get())
        except ValueError:                                     # E1
            self.amount.configure(highlightbackground=RED)
            self.banner.show("Enter a valid amount (more than $0, at most 2 decimals, "
                             f"at most ${rules.MAX_DEPOSIT:,.0f}).", "error")
            return
        except (PermissionError, OSError) as e:                # E2: write error, nothing changed
            self.banner.show(f"Deposit failed: {e}", "error")
            return
        self.app.set_flash(f"Funds added. New balance: ${res.balance:,.2f}. {res.note}".strip(), "ok")
        self.app.show("wallet")


# ---------------------------------------------------------------- My Orders (A-14)
class OrdersScreen(Screen):
    def build(self):
        ttk.Label(self, text="My Orders", style="H1.TLabel").pack(anchor="w", pady=(0, 10))
        orders = self.ctx.purchases.list_orders(self.session.user["user_id"])
        if not orders:
            ttk.Label(self, text="No orders yet - use Buy Now on a book's page.", style="Muted.TLabel").pack(anchor="w")
            return
        ttk.Label(self, text="Double-click a row to open the book.", style="Muted.TLabel").pack(anchor="w")
        tree = ttk.Treeview(self, columns=("date", "title", "list", "disc", "paid"), show="headings", height=16)
        for col, label, w in (("date", "Date", 170), ("title", "Book", 360), ("list", "List price", 110),
                              ("disc", "VIP discount", 120), ("paid", "Paid", 110)):
            tree.heading(col, text=label)
            tree.column(col, width=w, anchor="w")
        for p in orders:
            tree.insert("", "end", iid=p["purchase_id"], values=(
                p["timestamp"], p["title"], f"${p['list_price']:.2f}",
                f"-${p['discount']:.2f}" if p["discount"] else "-", f"${p['price_paid']:.2f}"))
        book_of = {p["purchase_id"]: p["book_id"] for p in orders}
        tree.bind("<Double-1>", lambda _e: tree.focus() and self.open_book(book_of[tree.focus()]))
        tree.pack(fill="x", pady=6)
        total = sum(p["price_paid"] for p in orders)
        ttk.Label(self, text=f"{len(orders)} book(s), ${total:,.2f} in total.", style="Muted.TLabel").pack(anchor="w")


# ---------------------------------------------------------------- My Reviews + warnings (A-14, UC-11 step 3)
class MyReviewsScreen(Screen):
    def build(self):
        self.session.refresh()
        u = self.session.user
        ttk.Label(self, text="My Reviews", style="H1.TLabel").pack(anchor="w", pady=(0, 10))
        reviews = self.ctx.reviews.list_user_reviews(u["user_id"])
        if not reviews:
            ttk.Label(self, text="You have not written any reviews yet.", style="Muted.TLabel").pack(anchor="w")
        else:
            tree = ttk.Treeview(self, columns=("date", "title", "stars", "status", "text"), show="headings", height=9)
            for col, label, w in (("date", "Date", 160), ("title", "Book", 240), ("stars", "Rating", 90),
                                  ("status", "Status", 110), ("text", "Shown as", 380)):
                tree.heading(col, text=label)
                tree.column(col, width=w, anchor="w")
            for r in reviews:
                shown = r["display_text"] if r["status"] == rules.PUBLISHED else "(blocked - never shown)"
                tree.insert("", "end", iid=r["review_id"], values=(
                    r["timestamp"], r["title"], stars(r["rating"]), r["status"], shown))
            book_of = {r["review_id"]: r["book_id"] for r in reviews}
            tree.bind("<Double-1>", lambda _e: tree.focus() and self.open_book(book_of[tree.focus()]))
            tree.pack(fill="x")

        ttk.Label(self, text=f"Warnings ({u['warnings']})", style="H2.TLabel").pack(anchor="w", pady=(16, 2))
        if u["role"] == rules.RC:
            left = rules.RC_SUSPEND_ABOVE + 1 - u["warnings"]
            note = (f"{left} more warning(s) and your account will be suspended (R10)." if left > 0 else "")
        else:
            note = "VIP Customers lose VIP status after one blocked review (R10)."
        if note:
            ttk.Label(self, text=note, style="Muted.TLabel").pack(anchor="w")
        warnings = self.ctx.warnings.get_warnings(u["user_id"])
        if not warnings:
            ttk.Label(self, text="No warnings.", style="Muted.TLabel").pack(anchor="w")
            return
        titles = {r["review_id"]: r["title"] for r in reviews}
        wt = ttk.Treeview(self, columns=("date", "reason", "book"), show="headings", height=5)
        for col, label, w in (("date", "Date", 170), ("reason", "Reason", 200), ("book", "Review of", 360)):
            wt.heading(col, text=label)
            wt.column(col, width=w, anchor="w")
        for w in warnings:
            wt.insert("", "end", values=(w["timestamp"], w["reason"], titles.get(w["review_id"], "")))
        wt.pack(fill="x", pady=4)


# ---------------------------------------------------------------- AI Chatbot (UC-12, UC-13, R14)
def ai_mode_note(parent, ctx) -> None:
    """Orange strip saying the AI is MOCK / offline (CLAUDE.md: label every mock in the UI)."""
    if ctx.llm.is_mock or not ctx.llm.is_available():
        extra = (" Answers are picked from store data and book text, not written by a language model."
                 if ctx.llm.is_mock else "")
        tk.Label(parent, text=ctx.llm.mode_label + "." + extra, bg="#fff4e0", fg="#8a5300", font=(FONT, 11),
                 anchor="w", justify="left", wraplength=880, padx=8, pady=5).pack(fill="x", pady=(0, 8))


class ChatScreen(Screen):
    SOURCE_LABELS = {"RAG": "[Store data]", "GENERAL": "[General AI]", "ADMIN": "[Admin data]",
                     "DENIED": "[Not available]", "ERROR": "[Offline]"}
    SCOPE = {rules.VISITOR: "As a Visitor you can ask about the store: books, prices, VIP, fines, policies (R14).",
             rules.RC: "Ask about the store, your own account (balance, orders, warnings) or anything general (R14).",
             rules.VC: "Ask about the store, your own account (balance, orders, warnings) or anything general (R14).",
             rules.SU: "Ask about the store, general questions, or admin data: suspended accounts, sales, "
                       "warnings, balances, order lists (R14, UC-13)."}
    EXAMPLES = {rules.VISITOR: ["What does VIP status give me?", "Is there a mystery with a detective?",
                                "What happens if I don't have enough money?"],
                rules.RC: ["What is my balance?", "Am I VIP?", "Recommend a science book about the ocean"],
                rules.SU: ["Which accounts are suspended?", "What are the sales this month?",
                           "Which books are on the No-Order list?"]}

    def build(self):
        self.last_response = None
        ttk.Label(self, text="AI Chatbot", style="H1.TLabel").pack(anchor="w")
        ttk.Label(self, text=self.SCOPE[self.session.role], style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        ai_mode_note(self, self.ctx)
        if not self.ctx.ai_ready.is_set():
            self.banner.show("The AI index is still being prepared - store answers may be missing for a moment.", "info")
        ex = ttk.Frame(self)
        ex.pack(anchor="w", pady=(0, 6))
        ttk.Label(ex, text="Try:", style="Muted.TLabel").pack(side="left")
        for q in self.EXAMPLES[rules.RC if self.session.role == rules.VC else self.session.role]:   # VC asks like RC
            ttk.Button(ex, text=q, command=lambda q=q: self.use_example(q)).pack(side="left", padx=(6, 0))

        self.log = tk.Text(self, height=20, wrap="word", font=(FONT, 12), state="disabled",
                           relief="solid", borderwidth=1, padx=10, pady=8)
        self.log.tag_configure("you", foreground=NAVY, font=(FONT, 12, "bold"), spacing1=8)
        self.log.tag_configure("label", foreground=MUTED, font=(FONT, 10, "bold"), spacing1=4)
        self.log.tag_configure("bot", lmargin1=12, lmargin2=12)
        self.log.tag_configure("denied", foreground=RED, lmargin1=12, lmargin2=12)
        self.log.pack(fill="both", expand=True)

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(8, 0))
        self.entry = ttk.Entry(row, font=(FONT, 13))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<KeyRelease>", lambda _e: self.update_send())
        self.entry.bind("<Return>", lambda _e: self.on_send())
        self.send_btn = ttk.Button(row, text="Send", style="Primary.TButton", command=self.on_send, state="disabled")
        self.send_btn.pack(side="left", padx=(8, 0))
        self.busy = False
        self.entry.focus_set()

    def use_example(self, q):
        self.entry.delete(0, "end")
        self.entry.insert(0, q)
        self.update_send()

    def update_send(self):
        """UC-12 E4: Send stays disabled while the question is empty (or an answer is pending)."""
        ok = bool(self.entry.get().strip()) and not self.busy
        self.send_btn.configure(state="normal" if ok else "disabled")

    def write(self, text, tag):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.configure(state="disabled")
        self.log.see("end")

    def on_send(self):
        q = self.entry.get().strip()
        if not q or self.busy:
            return
        self.banner.clear()
        self.busy = True
        self.entry.delete(0, "end")
        self.update_send()
        self.write("You: " + q, "you")
        self.log.mark_set("thinking", "end-1c")          # where "…thinking" starts
        self.log.mark_gravity("thinking", "left")
        self.write("…thinking", "label")
        self.app.run_async(lambda: self.ctx.chatbot.ask(self.session, q), self.on_answer)

    def on_answer(self, resp, error):
        if not self.winfo_exists():                      # user left the screen meanwhile
            return
        self.log.configure(state="normal")
        self.log.delete("thinking", "end-1c")            # remove "…thinking"
        self.log.configure(state="disabled")
        self.busy = False
        self.update_send()
        if error is not None:
            self.banner.show(f"The assistant failed: {error}", "error")
            return
        self.last_response = resp
        label = self.SOURCE_LABELS.get(resp.source, resp.source)
        if self.ctx.llm.is_mock and resp.source in ("RAG", "GENERAL", "ADMIN"):
            label += " · MOCK AI"
        self.write(label, "label")
        self.write(resp.text, "denied" if resp.source in ("DENIED", "ERROR") else "bot")


# ---------------------------------------------------------------- Smart Reading Companion (UC-14, R15)
class CompanionScreen(BuyMixin, Screen):
    def build(self):
        self.quiz_vars, self.quiz = [], []
        book_id = self.kwargs["book_id"]
        ttk.Button(self, text="‹ Back to book", command=lambda: self.app.show("book", book_id=book_id)).pack(anchor="w")
        try:
            self.state = self.ctx.companion.open(self.session, book_id)
        except (CompanionError, PermissionError) as e:                  # E1
            self.banner.show(str(e), "error")
            self.state = None
            return
        st = self.state
        head = ttk.Frame(self)
        head.pack(fill="x", pady=(6, 4))
        ttk.Label(head, text=f"📖 {st.book['title']}", style="H1.TLabel").pack(side="left")
        if st.owned:
            ttk.Label(head, text="You own this book: every chapter is open.", foreground=GREEN).pack(side="left", padx=12)
        else:
            ttk.Label(head, text=f"Preview: chapter {rules.FREE_CHAPTERS} only (R15).",
                      foreground="#8a5300").pack(side="left", padx=12)
            ttk.Button(head, text="Buy Now", style="Primary.TButton", command=self.buy).pack(side="left")
        ai_mode_note(self, self.ctx)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.chapter_list = tk.Listbox(body, width=30, font=(FONT, 12), activestyle="none", exportselection=False)
        for n, title in st.chapters:
            self.chapter_list.insert("end", f"{n}. {title}" if st.readable(n) else f"🔒 {n}. {title}")
        self.chapter_list.pack(side="left", fill="y")
        self.chapter_list.bind("<<ListboxSelect>>", lambda _e: self.on_pick_chapter())
        self.text = tk.Text(body, wrap="word", font=("Georgia", 13), padx=14, pady=10, height=16,
                            relief="solid", borderwidth=1, spacing2=3)
        self.text.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tools = ttk.Frame(self)
        tools.pack(fill="x", pady=8)
        for label, cmd in (("Summarize chapter", self.on_summarize), ("Explain selection", self.on_explain),
                           ("Define selected word", self.on_define), ("Quiz me", self.on_quiz)):
            ttk.Button(tools, text=label, command=cmd).pack(side="left", padx=(0, 6))
        self.question = ttk.Entry(tools, width=36, font=(FONT, 12))
        self.question.pack(side="left", padx=(12, 6), ipady=2)
        self.question.bind("<Return>", lambda _e: self.on_ask())
        ttk.Button(tools, text="Ask", style="Primary.TButton", command=self.on_ask).pack(side="left")

        self.answer_box = ttk.Frame(self, style="Card.TFrame", padding=10)
        self.answer_box.pack(fill="both")
        self.answer = tk.Text(self.answer_box, wrap="word", font=(FONT, 12), height=7, relief="flat",
                              bg=CARD, state="disabled")
        self.answer.pack(fill="both")
        self.show_chapter(st.chapter)                                    # resume where they stopped

    # ---- reading
    def show_chapter(self, n):
        try:
            body = self.ctx.companion.load_chapter(self.state, n)
        except CompanionError as e:                                      # E2 (R15)
            self.show_error(e)
            self.chapter_list.selection_clear(0, "end")
            self.chapter_list.selection_set(self.state.chapter - 1)
            return
        self.banner.clear()
        self.chapter_list.selection_clear(0, "end")
        self.chapter_list.selection_set(n - 1)
        title = dict(self.state.chapters)[n]
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", f"Chapter {n}: {title}\n\n{body}")
        self.text.configure(state="disabled")                            # selectable, not editable

    def on_pick_chapter(self):
        sel = self.chapter_list.curselection()
        if sel and sel[0] + 1 != self.state.chapter:
            self.show_chapter(sel[0] + 1)

    def show_error(self, e):
        self.banner.clear()
        self.banner.show(str(e), "warn" if getattr(e, "buy", False) else "error")
        if getattr(e, "buy", False):                                     # E2: "with a Buy button"
            ttk.Button(self.banner, text="Buy Now", style="Primary.TButton", command=self.buy).pack(anchor="w")

    def buy(self):
        self.on_buy(self.state.book)

    def after_buy(self, book_id):                                        # back here, now owned
        self.app.show("companion", book_id=book_id)

    def selection(self) -> str:
        try:
            return self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    # ---- AI actions (run in a worker thread)
    def run(self, title, work, render=None):
        self.banner.clear()
        self.set_answer(f"{title}: thinking…")
        self.app.run_async(work, lambda result, error: self.on_result(title, result, error, render))

    def on_result(self, title, result, error, render):
        if not self.winfo_exists():
            return
        if error is not None:                                            # E2 / E3 / E4
            self.set_answer("")
            self.show_error(error)
            return
        if render:
            render(result)
        else:
            tag = " (MOCK AI)" if self.ctx.llm.is_mock else ""
            self.set_answer(f"{title}{tag}\n\n{result}")

    def set_answer(self, text):
        for w in self.answer_box.winfo_children():
            if w is not self.answer:
                w.destroy()
        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self.answer.insert("1.0", text)
        self.answer.configure(state="disabled")
        self.answer.pack(fill="both")

    def on_summarize(self):
        n = self.state.chapter
        self.run(f"Summary of chapter {n}", lambda: self.ctx.companion.summarize(self.state, n))

    def on_explain(self):
        sel = self.selection()
        self.run("Explanation", lambda: self.ctx.companion.explain(self.state, sel))

    def on_define(self):
        words = self.selection().split()
        word = words[0] if words else ""
        self.run(f"Meaning of '{word}'", lambda: self.ctx.companion.define(self.state, word))

    def on_ask(self):
        q = self.question.get()
        self.run("Answer", lambda: self.ctx.companion.ask(self.state, q))

    def on_quiz(self):
        n = self.state.chapter
        self.run(f"Quiz on chapter {n}", lambda: self.ctx.companion.quiz(self.state, n), self.render_quiz)

    def render_quiz(self, questions):
        """3 multiple-choice questions; the correct answers stay hidden until the reader
        clicks Check answers (UC-14 step 5)."""
        self.answer.pack_forget()
        self.quiz, self.quiz_vars = questions, []
        mock = " (MOCK AI: fill-in-the-blank from the text)" if self.ctx.llm.is_mock else ""
        ttk.Label(self.answer_box, text=f"Quiz on chapter {self.state.chapter}{mock}", style="Card.TLabel",
                  font=(FONT, 12, "bold")).pack(anchor="w")
        self.quiz_marks = []
        for i, q in enumerate(questions):
            var = tk.IntVar(value=-1)
            self.quiz_vars.append(var)
            ttk.Label(self.answer_box, text=f"{i + 1}. {q['q']}", style="Card.TLabel", wraplength=900).pack(anchor="w", pady=(6, 0))
            row = ttk.Frame(self.answer_box, style="Card.TFrame")
            row.pack(anchor="w")
            for j, opt in enumerate(q["options"]):
                ttk.Radiobutton(row, text=opt, value=j, variable=var).pack(side="left", padx=(0, 12))
            mark = ttk.Label(self.answer_box, text="", style="Card.TLabel")
            mark.pack(anchor="w")
            self.quiz_marks.append(mark)
        ttk.Button(self.answer_box, text="Check answers", command=self.check_quiz).pack(anchor="w", pady=(6, 0))

    def check_quiz(self):
        score = 0
        for q, var, mark in zip(self.quiz, self.quiz_vars, self.quiz_marks):
            right = q["options"][q["answer_index"]]
            if var.get() == q["answer_index"]:
                score += 1
                mark.configure(text="✔ Correct", foreground=GREEN)
            else:
                mark.configure(text=f"✘ The answer is: {right}", foreground=RED)
        self.banner.show(f"You got {score} of {len(self.quiz)} right.", "ok" if score == len(self.quiz) else "info")
        return score


# ---------------------------------------------------------------- not built yet
class PlaceholderScreen(Screen):
    def build(self):
        ttk.Label(self, text=self.kwargs.get("title", "Coming soon"), style="H1.TLabel").pack(anchor="w")
        tk.Label(self, text=f"STUB - this screen ({self.kwargs.get('uc', '')}) arrives in Phase "
                            f"{self.kwargs.get('phase', '?')}.", bg="#fff4e0", fg="#8a5300",
                 font=(FONT, 13), padx=12, pady=10, anchor="w").pack(fill="x", pady=12)
