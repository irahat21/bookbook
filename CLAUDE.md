# Smart Bookstore (BookOrbit AI) – Full Prototype

## Goal
Build a working end-to-end prototype of the whole app in
`docs/BookOrbit_AI_Phase2_Design_Report.pdf` (the SRS / design report).
It is the source of truth: use cases UC-01..UC-18 and business rules R1..R15
(Table 2). Runs locally only.

## Stack (named by the SRS, Section 1.1)
- Python 3.12 desktop app, Tkinter / ttk UI.
- Storage: JSON Lines `.txt` files in `data/` (one file per entity, Table 9).
  Only the `FileStore` class reads or writes them. No SQL database.
- AI: local Ollama (`llama3.2:3b`, `nomic-embed-text`); biometrics (YOLOv8-face,
  FaceNet, Resemblyzer) and cover search (OpenCLIP) are optional "real" modes.

## Python environment
- All packages go into a virtual environment at `.venv/` in the project
  folder. Never install anything globally or with the system Python.
- `.venv/` is in `.gitignore`; every dependency is listed in `requirements.txt`.
- Run everything with `.venv/bin/python`, e.g.
  `.venv/bin/python seed.py`, `.venv/bin/python app.py`,
  `.venv/bin/python -m unittest discover tests -v`.

## Rules
- Build in the phases below. After each phase: run the app, test it,
  fix errors, commit to local git, summarize, then STOP and wait for me.
- Never push to GitHub or any remote.
- Don't invent requirements. Log assumptions, resolved conflicts and deviations
  from the SRS pseudo-code in `docs/ASSUMPTIONS.md`, and clearly mark anything
  mocked or stubbed (in the UI and in `docs/COVERAGE.md`).
- `seed.py` resets `data/` with ~50 fake books (locally generated covers and
  short original chapter texts, no downloads), one Super-User account and demo
  RC / VC / suspended customers. Fake money only (wallet deposits, no payment gateway).
- Configuration goes in `.env` (see `.env.example`), never in code: `OLLAMA_URL`,
  model names, and `BIOMETRIC_MODE` / `LLM_MODE` / `COVER_MODE` = `mock` | `real`.
  If a model or service is missing, use the mock and label it MOCK.
- Business-rule thresholds are named constants in `bookorbit/rules.py`, each
  tagged with its R-number. Each rule gets a unit test.
- Reference SRS IDs (UC-xx, Rxx) in comments and commit messages.
- Explain anything non-obvious so I can understand and present it.

## Decisions already made (see docs/ASSUMPTIONS.md)
- No shopping cart: purchases are single-book "Buy Now" paid from the wallet (UC-08/09).
- No stock / inventory: books are digital (BOOK has no stock field).
- One review per customer per book.
- R15 chapter limit applies to every Reading Companion action on non-owned books.
- Pseudo-code bugs in lockout (`is_locked`), chatbot offline ordering and the
  Visitor "no context" answer are fixed and logged as deviations. R7 is kept as written but flagged.

## Phases
1. Accounts, catalog, search: UC-01, UC-02 (mock biometrics), UC-03, UC-04 (text), UC-05
2. Wallet, Buy Now, reviews: UC-07, UC-08, UC-09, UC-10, UC-11 (R5-R13)
3. AI features: UC-06, UC-12, UC-13, UC-14, UC-04 cover search, real-model switches
4. Admin: UC-15, UC-16, UC-17, UC-18
5. Polish + docs/COVERAGE.md (each UC / rule: done / partial / stubbed)
