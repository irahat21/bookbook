# BookOrbit AI – Smart Bookstore prototype

Local desktop prototype of the BookOrbit AI design report
(`docs/BookOrbit_AI_Phase2_Design_Report.pdf`): Python 3.12 + Tkinter, data in
JSON Lines text files under `data/`.

## Setup (once)
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Run
```bash
.venv/bin/python seed.py      # reset data/: 50 fake books (10 with full text), demo users, sample files
.venv/bin/python app.py       # start the app
.venv/bin/python -m unittest discover tests -v
```

## Demo sign-in (MOCK biometrics)
Sign In → type a username → **Choose sample file…** → pick the matching file in
`data/samples/` → **Capture & Verify**.

| Username | Role | Face / voice sample |
|----------|------|---------------------|
| `sue_admin` | Super-User | `sue_admin_face.png` / `sue_admin_voice.wav` |
| `alice` | Registered Customer | `alice_face.png` / `alice_voice.wav` |
| `victor` | VIP Customer | `victor_face.png` / `victor_voice.wav` |
| `sid` | Suspended customer (wallet-only) | `sid_face.png` / `sid_voice.wav` |

Exceptional cases: `stranger_face.png` (no match → 3 tries → 5-minute lock),
`no_face.png`, `two_faces.png`, `short_voice.wav` (asked to recapture, not counted).
To register, use `new_user_face.png` / `new_user_voice.wav`.

## AI features (Phase 3)
- **AI Chatbot** (sidebar, every role): store questions, your own account, general and
  (Super-User) admin questions, within R14. Answers are labelled [Store data] / [General AI] /
  [Admin data].
- **Reading Companion** (book page, customers): read chapters; summarize, explain a selected
  passage, define a word, quiz yourself, ask questions. Non-owned books: chapter 1 only (R15).
- **Recommendations** (customers): 3 books based on what you bought and viewed (R4).
- **Cover search**: the 📷 Cover button; try the photos in `data/samples/covers/`.

AI modes are set in `.env` (copy `.env.example`):

| Setting | `mock` (default) | `real` |
|---------|------------------|--------|
| `LLM_MODE` | MOCK: answers picked from store data / book text | local Ollama (`llama3.2:3b`, `nomic-embed-text`), see `docs/PROGRESS.md`. `offline` imitates a stopped Ollama |
| `COVER_MODE` | MOCK: colour + layout matching | OpenCLIP (written, **not tested**) |
| `BIOMETRIC_MODE` | MOCK: sample files | YOLOv8-face + FaceNet + Resemblyzer (written, **not tested**) |

A missing model always falls back to the MOCK, and the sidebar says so. The optional
packages for the real cover / biometric modes are in `requirements-real.txt` (not installed).

See `docs/ASSUMPTIONS.md` for every assumption, deviation and mock, and `docs/PROGRESS.md`
for handoff notes and the Ollama guide.

## Layout
```
bookorbit/
  rules.py            business-rule constants (R1-R15)
  persistence/        FileStore (the only code that touches data/)
  services/           Session, Auth, Catalog, Reviews, Ratings, Wallet, Purchases,
                      Chatbot (UC-12/13), ReadingCompanion (UC-14)
  ai/                 LLMClient (+ mock), RAGRetriever, CoverIndex, RecommendationEngine,
                      BiometricEngine, text / media helpers
  ui/                 MainWindow + screens (Tkinter)
seed.py, seed_texts/ (10 book texts + store policies), app.py, tests/
```
