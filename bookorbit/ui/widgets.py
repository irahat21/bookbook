"""Shared look and small widgets (navy sidebar layout of SRS Section 5)."""
import tkinter as tk
from tkinter import ttk

NAVY = "#1c2a4a"
NAVY_HI = "#2c3f68"
ORANGE = "#f0a63c"
BG = "#f4f6fa"
CARD = "#ffffff"
TEXT = "#1c2333"
MUTED = "#6b7385"
RED = "#c0392b"
GREEN = "#1e8449"
FONT = "Helvetica"


def setup_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(FONT, 12), background=BG)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD)
    style.configure("H1.TLabel", font=(FONT, 22, "bold"))
    style.configure("H2.TLabel", font=(FONT, 16, "bold"))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Error.TLabel", foreground=RED, font=(FONT, 11))
    style.configure("Primary.TButton", background=NAVY, foreground="white", padding=(12, 6))
    style.map("Primary.TButton", background=[("disabled", "#9aa3b5"), ("active", NAVY_HI)])
    style.configure("Treeview", rowheight=24, font=(FONT, 11))
    style.configure("Treeview.Heading", font=(FONT, 11, "bold"))


class Tooltip:
    """Hover text, used e.g. for disabled buttons (UC-04 E5, UC-05 E3)."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg="#fffbe6", fg=TEXT, relief="solid", borderwidth=1,
                 font=(FONT, 11), padx=6, pady=3, wraplength=280, justify="left").pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Banner(ttk.Frame):
    """Message strip at the top of a screen (SRS 4.24: handlers show errors in a banner).
    The frame is always packed; it has zero height until show() puts a label in it."""

    COLORS = {"error": ("#fdecea", RED), "ok": ("#e8f6ee", GREEN),
              "info": ("#eef2fb", NAVY), "warn": ("#fff4e0", "#8a5300")}

    def __init__(self, parent):
        super().__init__(parent)
        self.label = tk.Label(self, text="", anchor="w", padx=10, pady=6, font=(FONT, 12),
                              wraplength=880, justify="left")
        self.text = ""

    def show(self, text: str, kind: str = "info"):
        bg, fg = self.COLORS[kind]
        self.text = text
        self.label.configure(text=text, bg=bg, fg=fg)
        self.label.pack(fill="x", pady=(0, 8))

    def clear(self):
        self.text = ""
        self.label.pack_forget()
        for w in self.winfo_children():            # e.g. the "Buy Now" button of UC-14 E2
            if w is not self.label:
                w.destroy()


def stars(avg: float) -> str:
    full = int(round(avg))
    return "★" * full + "☆" * (5 - full)


def draw_cover(parent, book: dict, cover_file, images: list) -> tk.Canvas:
    """120x180 canvas: the generated cover PNG with the title drawn on top."""
    canvas = tk.Canvas(parent, width=120, height=180, highlightthickness=0)
    try:
        img = tk.PhotoImage(file=str(cover_file))
        images.append(img)                      # keep a reference or Tk drops the image
        canvas.create_image(0, 0, anchor="nw", image=img)
    except tk.TclError:                         # missing/unreadable cover: plain block
        canvas.create_rectangle(0, 0, 120, 180, fill="#8899aa", outline="")
    canvas.create_rectangle(0, 8, 120, 62, fill="#000000", stipple="gray50", outline="")
    canvas.create_text(60, 35, text=book["title"], fill="white", width=110,
                       font=(FONT, 10, "bold"), justify="center")
    return canvas


class BookCard(tk.Frame):
    """Cover (generated PNG with the title drawn on top), title, author and rating."""

    def __init__(self, parent, book: dict, on_click, images: list, cover_file=None):
        super().__init__(parent, bg=CARD, highlightbackground="#d9dee8", highlightthickness=1,
                         cursor="hand2", width=146, height=262)
        self.pack_propagate(False)
        canvas = draw_cover(self, book, cover_file, images)
        canvas.configure(bg=CARD, cursor="hand2")
        canvas.pack(pady=(8, 4))
        title = tk.Label(self, text=book["title"], bg=CARD, fg=TEXT, font=(FONT, 11, "bold"),
                         wraplength=136, justify="center", cursor="hand2")
        title.pack()
        sub = tk.Label(self, text=book["author"], bg=CARD, fg=MUTED, font=(FONT, 10), cursor="hand2")
        sub.pack()
        rating = (f"★ {book['weighted_avg']:.1f} ({book['rating_count']})"
                  if book["rating_count"] else "No ratings yet")
        rate = tk.Label(self, text=rating, bg=CARD, fg="#b7791f", font=(FONT, 10), cursor="hand2")
        rate.pack()
        for w in (self, canvas, title, sub, rate):
            w.bind("<Button-1>", lambda _e: on_click(book["book_id"]))


class ScrollFrame(ttk.Frame):
    """A vertically scrollable frame; put children in .inner."""

    def __init__(self, parent, height=300):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, height=height)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
