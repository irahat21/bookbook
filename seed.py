"""Reset data/ with demo data (CLAUDE.md: ~50 fake books, one Super-User, demo customers).

Everything is generated locally - book covers, demo face photos and voice clips -
so nothing is downloaded. Run:  .venv/bin/python seed.py

Demo accounts (sign in by choosing the matching file in data/samples/):
  sue_admin  Super-User
  alice      Registered Customer, $50 balance, 3 purchases: her next purchase makes her VIP (R5)
  victor     VIP Customer, $120 balance, promoted by his 4th purchase (R5)
  sid        Registered Customer, SUSPENDED: tried to buy with $0, fined $1.00 (R7) -> wallet-only
  wes        Registered Customer with 2 warnings: one more blocked review suspends him (R10)
  bella, carlos, dana, eli, fay   Registered Customers who wrote the seeded reviews (1 purchase each)

Purchases, the promotion, the fine/suspension, the warnings and the reviews all go
through the real services (PurchaseService, ReviewService, ...), so every counter,
ledger entry and status change is consistent. clock.frozen() gives them fixed timestamps.
"""
import hashlib
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from bookorbit import clock, rules
from bookorbit.ai import media
from bookorbit.ai.biometrics import FACE, VOICE
from bookorbit.app_context import build_context
from bookorbit.config import PROJECT_ROOT, load_config
from bookorbit.errors import PurchaseError
from bookorbit.services.session import Session

RNG = random.Random(322)          # fixed seed: every reset gives the same data
BASE_TIME = datetime(2026, 10, 1, 9, 0, 0)

# 50 original (made-up) books: 10 categories x 5 titles
CATALOG = {
    "Fiction": ["The Lantern Keeper's Daughter", "Salt and Static", "A House of Folded Letters",
                "The Quiet Orchard", "Tuesdays on Marrow Street"],
    "Mystery": ["The Clockmaker's Alibi", "Nine Keys to Harrow Hall", "Murder at the Tidewater Inn",
                "The Vanishing Cartographer", "Ink on the Lighthouse Stairs"],
    "Science Fiction": ["Orbit of the Glass Moons", "The Last Signal from Kepler Bay",
                        "Starlight Freight Company", "The Copper Gardeners of Mars", "Echoes in Hyperlane Six"],
    "Fantasy": ["The Ember Crown", "Songs of the Hollow Forest", "The Dragon Who Collected Maps",
                "A Spell for Rainy Kingdoms", "The Moonbound Archivist"],
    "Romance": ["Letters from the Lavender Coast", "Second Spring in Verona Lane", "The Bookshop Proposal",
                "Hearts Over Harbor Bridge", "A Winter Waltz"],
    "History": ["Rivers of Empire", "The Silk Road Ledgers", "Bridges of the Industrial Age",
                "The Forgotten Fleet of 1588", "Bread and Barricades"],
    "Biography": ["The Woman Who Measured Storms", "Notes of a Midnight Pianist", "The Inventor's Notebook",
                  "A Life Among Glaciers", "The Chess Teacher of Odessa"],
    "Self-Help": ["Small Steps, Steady Days", "The Calm Desk Method", "Habits of the Patient Mind",
                  "Saying No Gracefully", "The Five-Minute Morning"],
    "Science": ["The Secret Life of Fungi", "Atoms in Your Coffee Cup", "Maps of the Deep Ocean",
                "How Bridges Stand Up", "The Curious Physics of Everyday Things"],
    "Poetry": ["Paper Boats and Thunder", "Salt Psalms", "The Orchard Sonnets",
               "City Lights, Country Stars", "Small Hours"],
}
KEYWORDS = {
    "Fiction": ["family", "small town", "secrets", "friendship", "coming of age"],
    "Mystery": ["detective", "murder", "clues", "suspense", "whodunit"],
    "Science Fiction": ["space", "robots", "future", "aliens", "time travel"],
    "Fantasy": ["magic", "dragons", "quest", "kingdom", "adventure"],
    "Romance": ["love", "second chances", "summer", "letters", "wedding"],
    "History": ["empire", "war", "trade", "revolution", "europe"],
    "Biography": ["memoir", "inventor", "artist", "explorer", "true story"],
    "Self-Help": ["habits", "productivity", "mindfulness", "focus", "wellbeing"],
    "Science": ["biology", "physics", "ocean", "engineering", "nature"],
    "Poetry": ["verse", "nature", "city", "love", "seasons"],
}
FIRST = ["Ada", "Bram", "Celia", "Dorian", "Elsa", "Felix", "Greta", "Hugo", "Iris", "Jonah",
         "Kira", "Leon", "Mira", "Nils", "Opal", "Pavel", "Quinn", "Rosa", "Silas", "Tova"]
LAST = ["Ashdown", "Bellweather", "Corrigan", "Dunmore", "Everly", "Fairbank", "Galloway",
        "Hartwell", "Ironside", "Juniper", "Kestrel", "Lockridge", "Merriweather", "Northcott"]
BLURB = {
    "Fiction": "A tender story about {k1} and {k2}, told over one unforgettable year.",
    "Mystery": "A {k1} story full of {k2}: every page hides a new clue.",
    "Science Fiction": "An adventure through {k1} and {k2} at the edge of the known galaxy.",
    "Fantasy": "A sweeping tale of {k1}, {k2} and an unlikely hero.",
    "Romance": "A warm, witty romance about {k1} and {k2}.",
    "History": "A lively history of {k1} and {k2}, built on letters and ledgers.",
    "Biography": "A {k1} portrait of a remarkable life - a {k2} you won't forget.",
    "Self-Help": "Practical, kind advice on {k1} and {k2} for busy people.",
    "Science": "An accessible tour of {k1} and {k2} for curious readers.",
    "Poetry": "A collection of short poems about {k1} and {k2}.",
}
REVIEW_TEXT = {
    5: ["Absolutely loved it - could not put it down.", "A new favourite, I will reread this.",
        "Beautifully written from start to finish."],
    4: ["Really enjoyable, a couple of slow chapters.", "Great read, would recommend to friends.",
        "Smart and engaging, worth the price."],
    3: ["Decent, but it did not fully grab me.", "Some good moments, some flat ones.",
        "Fine for a weekend read."],
    2: ["The pacing never worked for me.", "I expected more from the premise.",
        "Hard to finish, sadly."],
    1: ["Not for me at all.", "Very disappointing.", "Could not get into it."],
}
DEMO_USERS = [
    # username, full name, role, voice pitch (Hz) for the MOCK voiceprint (unique per 10 Hz).
    # Everyone starts as an ACTIVE RC; VIP and SUSPENDED states are earned through the services.
    ("sue_admin", "Sue Admin", rules.SU, 180),
    ("alice", "Alice Morgan", rules.RC, 220),
    ("victor", "Victor Hale", rules.RC, 130),
    ("sid", "Sid Turner", rules.RC, 150),
    ("wes", "Wes Barlow", rules.RC, 170),
    ("bella", "Bella Cruz", rules.RC, 240),
    ("carlos", "Carlos Ibanez", rules.RC, 110),
    ("dana", "Dana Okafor", rules.RC, 200),
    ("eli", "Eli Novak", rules.RC, 120),
    ("fay", "Fay Lindqvist", rules.RC, 260),
]
# Decision A-11 / Phase 3: 10 books (one per category) get a short original text in
# seed_texts/, written for this project, so the Reading Companion (UC-14) and the RAG
# index have something to read. The other 40 books have no text (UC-14 E1).
SEED_TEXTS = PROJECT_ROOT / "seed_texts"
BOOK_TEXTS = {
    "The Lantern Keeper's Daughter": "the_lantern_keepers_daughter.txt",
    "The Clockmaker's Alibi": "the_clockmakers_alibi.txt",
    "Orbit of the Glass Moons": "orbit_of_the_glass_moons.txt",
    "The Dragon Who Collected Maps": "the_dragon_who_collected_maps.txt",
    "The Bookshop Proposal": "the_bookshop_proposal.txt",
    "Bridges of the Industrial Age": "bridges_of_the_industrial_age.txt",
    "The Woman Who Measured Storms": "the_woman_who_measured_storms.txt",
    "Small Steps, Steady Days": "small_steps_steady_days.txt",
    "The Secret Life of Fungi": "the_secret_life_of_fungi.txt",
    "Paper Boats and Thunder": "paper_boats_and_thunder.txt",
}

# UC-04 cover search demo: "phone photos" of these covers go to data/samples/covers/
COVER_PHOTOS = {"The Dragon Who Collected Maps": "photo_dragon_maps",
                "The Clockmaker's Alibi": "photo_clockmakers_alibi",
                "The Secret Life of Fungi": "photo_secret_life_of_fungi"}

# Balances each customer ends the seed with (alice and victor deposit extra to pay for
# their purchases first, so they end exactly here).
END_BALANCE = {"alice": 50.0, "victor": 120.0, "wes": 20.0}
START_DEPOSIT = {"bella": 20.0, "carlos": 20.0, "dana": 20.0, "eli": 20.0, "fay": 20.0}

# Decision A-22: mild placeholder taboo words (no real profanity - this is a class demo).
# The SRS prototype (Section 5.2) uses "dumb" as its example. Super-Users edit the list in UC-16.
TABOO_WORDS = ["crap", "darn", "dumb", "garbage", "heck", "idiot", "lame", "moron", "stupid", "trash"]
# wes's two blocked reviews (4 taboo words each -> BLOCKED, one warning each; R9, R10)
BLOCKED_TEXTS = ["What a dumb, stupid plot. Lame characters and a darn silly ending.",
                 "Total garbage. Trash pacing, an idiot hero and a crap twist."]


def ts(offset_minutes: int) -> str:
    return (BASE_TIME + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- images / audio
def _hue_rgb(h: float, s: float, v: float) -> np.ndarray:
    import colorsys
    return np.array(colorsys.hsv_to_rgb(h, s, v)) * 255


def make_cover(book_id: str, category_index: int) -> bytes:
    """120x180 abstract cover: category hue, a band and a circle placed by the book's hash."""
    h = int(hashlib.sha256(book_id.encode()).hexdigest(), 16)
    w, hgt = 120, 180
    yy, xx = np.mgrid[0:hgt, 0:w]
    hue = (category_index / 10 + (h % 7) / 70) % 1.0
    img = np.zeros((hgt, w, 3)) + _hue_rgb(hue, 0.55, 0.55)
    band_y = 30 + h % 90
    img[(yy > band_y) & (yy < band_y + 18)] = _hue_rgb((hue + 0.08) % 1, 0.35, 0.85)
    cx, cy, r = 20 + (h >> 8) % 80, 110 + (h >> 16) % 50, 14 + (h >> 24) % 18
    img[(xx - cx) ** 2 + (yy - cy) ** 2 < r * r] = _hue_rgb((hue + 0.5) % 1, 0.6, 0.95)
    return media.encode_png(img.astype(np.uint8), {"book_id": book_id})


def make_cover_photo(cover_png: bytes, variant: int) -> bytes:
    """A "phone photo" of a cover for UC-04 cover search: slightly cropped, tilted and
    brighter or darker, on a grey table; variant 0 is saved as JPEG, 1 as PNG."""
    import io
    from PIL import Image, ImageEnhance
    img = Image.open(io.BytesIO(cover_png)).convert("RGB")
    w, h = img.size
    img = img.crop((6, 8, w - 5, h - 7)).resize((240, 360))
    img = ImageEnhance.Brightness(img).enhance(1.15 if variant == 0 else 0.85)
    img = img.rotate(3 if variant == 0 else -2, expand=True, fillcolor=(205, 205, 200))
    out = io.BytesIO()
    img.save(out, "JPEG" if variant == 0 else "PNG", **({"quality": 70} if variant == 0 else {}))
    return out.getvalue()


def make_face_photo(person: str | None, faces: int, variant: int) -> bytes:
    """Simple cartoon face(s). The PNG text tags tell the MOCK detector who and how many."""
    rng = np.random.default_rng(int(hashlib.sha256(f"{person}{variant}".encode()).hexdigest()[:8], 16))
    w, h = 160, 160
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3)) + np.array([200, 215, 230]) + rng.integers(-12, 12, (h, w, 3))
    centers = {1: [(80, 80)], 2: [(45, 80), (115, 80)]}.get(faces, [])
    r = 50 if faces == 1 else 32
    for cx, cy in centers:
        img[(xx - cx) ** 2 + (yy - cy) ** 2 < r * r] = [235, 195, 160]
        for ex in (cx - r // 3, cx + r // 3):
            img[(xx - ex) ** 2 + (yy - (cy - r // 4)) ** 2 < (r // 8) ** 2] = [40, 40, 40]
        img[(abs(yy - (cy + r // 3)) < 3) & (abs(xx - cx) < r // 3)] = [150, 60, 60]
    tags = {"faces": faces}
    if person:
        tags["person"] = person
    return media.encode_png(np.clip(img, 0, 255).astype(np.uint8), tags)


def make_voice(pitch: int, seconds: float, variant: int) -> bytes:
    rate = 16000
    t = np.arange(int(rate * seconds)) / rate
    rng = np.random.default_rng(pitch * 10 + variant)
    wave_ = 0.5 * np.sin(2 * np.pi * pitch * t) + 0.15 * np.sin(2 * np.pi * pitch * 2 * t)
    return media.encode_wav(wave_ + 0.05 * rng.standard_normal(len(t)), rate)


# ---------------------------------------------------------------- main
def main() -> None:
    cfg = load_config()
    data_dir = Path(cfg["DATA_DIR"]).resolve()
    if data_dir != (PROJECT_ROOT / "data").resolve() and "--force" not in sys.argv:
        sys.exit(f"Refusing to wipe {data_dir} (not the project's data/ folder). Use --force.")
    if data_dir.exists():
        shutil.rmtree(data_dir)
    ctx = build_context(cfg)
    fs = ctx.fs
    for sub in ("covers", "samples", "biometrics", "texts"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    samples = data_dir / "samples"
    # store policies: the chatbot's POLICY chunks (SRS 4.21 build_index reads data/policies.txt)
    shutil.copyfile(SEED_TEXTS / "policies.txt", data_dir / "policies.txt")

    # --- users (+ biometric templates enrolled through the same engine as UC-01) ---
    users, minute = {}, 0
    for username, name, role, pitch in DEMO_USERS:
        uid = fs.next_id("users", "U")
        enroll_face = make_face_photo(username, 1, 0)
        enroll_voice = make_voice(pitch, 3.0, 0)
        (samples / f"{username}_face.png").write_bytes(make_face_photo(username, 1, 1))
        (samples / f"{username}_voice.wav").write_bytes(make_voice(pitch, 3.0, 1))
        ctx.bio.enroll(uid, FACE, enroll_face)
        ctx.bio.enroll(uid, VOICE, enroll_voice)
        user = {"user_id": uid, "username": username, "full_name": name, "email": f"{username}@example.com",
                "role": role, "status": rules.ACTIVE, "balance": 0.0, "warnings": 0,
                "purchase_count": 0, "total_spent": 0.0, "promo_purchases": 0, "promo_spent": 0.0,
                "created_at": ts(minute)}
        fs.append("users", user)
        users[username] = user
        minute += 5

    # extra demo samples for the exceptional scenarios of UC-01 / UC-02
    (samples / "stranger_face.png").write_bytes(make_face_photo("stranger", 1, 0))
    (samples / "no_face.png").write_bytes(make_face_photo(None, 0, 0))
    (samples / "two_faces.png").write_bytes(make_face_photo("crowd", 2, 0))
    (samples / "new_user_face.png").write_bytes(make_face_photo("new_user", 1, 0))
    (samples / "new_user_voice.wav").write_bytes(make_voice(300, 3.0, 0))
    (samples / "stranger_voice.wav").write_bytes(make_voice(90, 3.0, 0))
    (samples / "short_voice.wav").write_bytes(make_voice(220, 1.0, 0))

    # --- books ---
    su_id = users["sue_admin"]["user_id"]
    used_authors = set()
    for ci, (category, titles) in enumerate(CATALOG.items()):
        for title in titles:
            bid = fs.next_id("books", "B")
            while True:
                author = f"{RNG.choice(FIRST)} {RNG.choice(LAST)}"
                if author not in used_authors:
                    used_authors.add(author)
                    break
            kws = RNG.sample(KEYWORDS[category], 3)
            cover = data_dir / "covers" / f"{bid}.png"
            cover.write_bytes(make_cover(bid, ci))
            text_path = None
            if title in BOOK_TEXTS:                       # UC-14 / R15: book with a full text
                text_path = f"texts/{bid}.txt"            # relative to data/, like cover_path
                shutil.copyfile(SEED_TEXTS / BOOK_TEXTS[title], data_dir / text_path)
            fs.append("books", {
                "book_id": bid, "title": title, "author": author, "category": category,
                "keywords": ", ".join(kws), "pub_year": RNG.randint(1950, 2025),
                "price": round(RNG.choice([4.99, 7.99, 9.99, 12.99, 14.99, 16.99, 19.99, 24.99, 34.99]), 2),
                "description": BLURB[category].format(k1=kws[0], k2=kws[1]),
                "cover_path": f"covers/{bid}.png", "cover_vec_path": None, "text_path": text_path,
                "added_by": su_id, "browse_count": RNG.randint(0, 60), "purchase_count": 0,
                "rating_count": 0, "weighted_avg": 0.0, "list_status": rules.LIST_NONE,
                "indexed": False, "added_at": ts(minute)})
            minute += 1

    # sample photos for UC-04 cover search (data/samples/covers/)
    cover_samples = samples / "covers"
    cover_samples.mkdir()
    by_title = {b["title"]: b for b in fs.load("books")}
    for i, (title, name) in enumerate(COVER_PHOTOS.items()):
        png = fs.resolve(by_title[title]["cover_path"]).read_bytes()
        (cover_samples / f"{name}.{'jpg' if i % 2 == 0 else 'png'}").write_bytes(make_cover_photo(png, i % 2))
    (cover_samples / "not_a_cover.png").write_bytes(make_face_photo(None, 0, 7))    # UC-04 E4
    (cover_samples / "not_an_image.txt").write_text("This is not a picture.\n")       # UC-04 E3

    for word in TABOO_WORDS:
        fs.append("taboo_words", {"word": word, "added_by": su_id, "added_at": ts(minute)})

    # --- review plan: one per customer per book (ASSUMPTIONS A-09); clean text only ---
    reviewer_names = ["alice", "victor", "bella", "carlos", "dana", "eli", "fay"]
    books = {b["book_id"]: b for b in fs.load("books")}
    book_ids = list(books)
    loved, disliked = book_ids[0:50:9][:4], book_ids[3:50:11][:2]   # demo R13 lists
    plan = []                                                       # (book_id, username, rating)
    for bid in book_ids:
        if bid in loved:
            who, ratings = reviewer_names[:5], [5, 5, 4, 5, 5]
        elif bid in disliked:
            who, ratings = reviewer_names[2:7], [1, 2, 1, 1, 2]
        else:
            who = RNG.sample(reviewer_names, RNG.randint(0, 3))
            ratings = [RNG.choice([2, 3, 3, 4, 4, 4, 5, 5]) for _ in who]
        plan += [(bid, name, rating) for name, rating in zip(who, ratings)]
    planned = {name: [bid for bid, n, _ in plan if n == name] for name in reviewer_names}

    # --- money: deposits and Buy Now through the real services (UC-07, UC-08, R5, R7) ---
    sessions = {name: Session(fs) for name in users}
    for name, sess in sessions.items():
        sess.start(fs.find("users", "username", name))
    to_buy = {
        "victor": loved,                                 # 4th purchase -> VIP (R5)
        "alice": planned["alice"][:3],                   # 3 purchases: the next one promotes her
        # one affordable book each, so their reviews of it count as verified (weight 2.0, R12)
        **{n: [b for b in planned[n] if books[b]["price"] <= 14.99][:1] for n in START_DEPOSIT},
    }
    t = 60 * 24                                          # purchases start one day after the books
    for name in ["alice", "victor", "wes", *START_DEPOSIT]:
        cost = sum(books[b]["price"] for b in to_buy.get(name, []))
        amount = START_DEPOSIT.get(name, END_BALANCE.get(name, 0.0) + cost)
        with clock.frozen(ts(t)):
            ctx.wallet.deposit(sessions[name], f"{amount:.2f}")
        for bid in to_buy.get(name, []):
            t += 37
            with clock.frozen(ts(t)):
                ctx.purchases.purchase(sessions[name], bid)
        t += 60
    with clock.frozen(ts(t)):                            # R7: sid tries to buy with $0.00
        try:
            ctx.purchases.purchase(sessions["sid"], book_ids[0])
        except PurchaseError:
            pass                                         # fined $1.00 -> balance -$1.00 -> SUSPENDED

    # --- reviews through ReviewService (moderation, verified weight, ratings, R13 lists) ---
    review_minute = 60 * 24 * 30
    for bid, name, rating in plan:
        with clock.frozen(ts(review_minute)):
            ctx.reviews.submit(sessions[name], bid, rating, RNG.choice(REVIEW_TEXT[rating]))
        review_minute += RNG.randint(30, 600)
    # wes: two blocked reviews -> 2 warnings (R9, R10); a 3rd would suspend him
    for bid, text in zip(book_ids[5:7], BLOCKED_TEXTS):
        review_minute += 90
        with clock.frozen(ts(review_minute)):
            ctx.reviews.submit(sessions["wes"], bid, 1, text)
    ctx.ratings.recalculate_all()

    u = {n: fs.find("users", "username", n) for n in users}
    assert u["victor"]["role"] == rules.VC and u["alice"]["role"] == rules.RC
    assert u["sid"]["status"] == rules.SUSPENDED and u["wes"]["warnings"] == 2
    lists = [b["list_status"] for b in fs.load("books")]
    assert lists.count(rules.LIST_TO_ORDER) == 4 and lists.count(rules.LIST_NO_ORDER) == 2, lists

    print(f"Seeded {len(fs.load('users'))} users, {len(fs.load('books'))} books, "
          f"{len(fs.load('purchases'))} purchases, {len(TABOO_WORDS)} taboo words, "
          f"{len(fs.load('reviews'))} reviews into {data_dir}")
    print(f"Demo sign-in samples: {samples}")


if __name__ == "__main__":
    main()
