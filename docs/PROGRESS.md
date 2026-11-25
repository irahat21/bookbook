# Progress / handoff notes

Read with `CLAUDE.md` (rules, stack, phases), `docs/ASSUMPTIONS.md` (decisions,
deviations, mocks) and `docs/SRS.md` (text extract of the design report: grep it for
UC-xx / Rxx / class names instead of opening the PDF). This file only holds what those don't.

## Status (2026-11-24)
- **Phase 1 done** (`8f87665`): UC-01..UC-05.
- **Phase 2 done** (`72a5755`): UC-07..UC-11, rules R5-R13.
- **Phase 3 done**: UC-06, UC-12, UC-13, UC-14, UC-04 cover search, real-model switches
  (R4, R14, R15). Eight local commits, one per step (`4a85d0b` .. the step-8 docs commit).
  171 tests (3 of them live-Ollama tests that skip without Ollama).
- **Next: Phase 4** (UC-15..UC-18, admin screens). Hooks already in place:
  `RAGRetriever.index_book`, `CoverIndex.add` (UC-15), `StatusManager.reopen` (UC-17).

## Quick start
```bash
.venv/bin/python -m pip install -r requirements.txt   # numpy + Pillow (Pillow is new in Phase 3)
.venv/bin/python seed.py                              # resets data/ (deletes it first)
.venv/bin/python -m unittest discover tests -v        # ~5 s
.venv/bin/python app.py
```
Ollama is **not installed** on this Mac, so the AI runs in MOCK mode (sidebar: "MOCK AI").
At start-up the sidebar shows "⏳ Preparing AI index…" for about a second while the RAG and
cover indexes are built in a background thread (SRS 4.24).

## Demo accounts (MOCK sign-in: choose the file in `data/samples/`)
| Username | State after `seed.py` | Good for demoing |
|----------|-----------------------|------------------|
| `sue_admin` | Super-User | admin chatbot (UC-13): "Which accounts are suspended?", "Give me an admin report" (E3) |
| `alice` | RC, $50, 3 purchases | her next Buy Now promotes her to VIP (R5); Recommendations (Fiction); companion preview on a book she doesn't own (R15) |
| `victor` | VC, $120, promoted by his 4th purchase | VIP price (R6); owns *The Lantern Keeper's Daughter* (B-0001) and *Bridges of the Industrial Age* (B-0028), both with full text: every companion chapter |
| `sid` | RC, SUSPENDED, -$1.00 | wallet-only mode (R8) |
| `wes` | RC, $20, 2 warnings, no purchases | one more blocked review suspends him (R10); "Popular right now" (UC-06 E1) |
| `bella`, `carlos`, `dana`, `eli`, `fay` | RC, $10.01, 1 purchase each | buying a $24.99 book: fined $1, not suspended (R7) |

Books with a full text (Reading Companion, A-11): B-0001, B-0006, B-0011, B-0018, B-0023,
B-0028, B-0031, B-0036, B-0041, B-0046 (one per category). All others show UC-14 E1.

Cover search samples (`data/samples/covers/`): `photo_dragon_maps.jpg`,
`photo_clockmakers_alibi.png`, `photo_secret_life_of_fungi.jpg` (found first),
`not_a_cover.png` (E4: no match), `not_an_image.txt` (E3).

Chatbot demo questions are on the chat screen as buttons. Visitor: "Tell me a joke" ->
"I can only answer questions about the store" (E2); "What is my balance?" -> not available (E1).

Taboo words (A-22): crap, darn, dumb, garbage, heck, idiot, lame, moron, stupid, trash.

## Code map for Phase 3
- `bookorbit/ai/llm.py` `LLMClient` (SRS 4.22): `OllamaLLM` (real, stdlib HTTP), `MockLLM`,
  `OfflineLLM`; `get_llm(cfg)` picks one from `LLM_MODE`. `bookorbit/ai/mock_llm.py` = the mock's tricks.
- `bookorbit/ai/rag.py` `RAGRetriever` (4.21): chunks in `rag_chunks.txt`, vectors in `data/rag/`.
- `bookorbit/ai/texts.py`: Gutenberg stripping + chapter splitting (shared by RAG and companion).
- `bookorbit/services/chatbot.py` `ChatbotService` (4.20, UC-12/13, R14 = `rules.CHAT_PERMITTED`).
- `bookorbit/services/companion.py` `ReadingCompanion` (4.23, UC-14, R15 = `rules.FREE_CHAPTERS`).
- `bookorbit/ai/recommendations.py` `RecommendationEngine.personalized` (4.10, UC-06, R4).
- `bookorbit/ai/covers.py` `CoverIndex` (4.9) + `CatalogService.search_by_cover` (UC-04).
- `bookorbit/app_context.py`: `start_ai_indexing(ctx)` runs `covers.build()` + `rag.build_index()`
  in a thread and sets `ctx.ai_ready`.
- UI: `ChatScreen`, `CompanionScreen`, `RecommendationsScreen`, camera button
  (`cover_button` / `run_cover_search`). Slow AI calls go through `MainWindow.run_async`.
  `BuyMixin` = the Buy Now flow shared by the book page and the companion.

## Switching to real Ollama (LLM_MODE=real)
Ollama is a separate desktop app/server, not a Python package, so nothing is added to `.venv`.
On this Mac (M2, 8 GB RAM) `llama3.2:3b` fits, but expect a few seconds per answer and
10-20 s for the first one while the model loads.

1. **Install Ollama**: download it from ollama.com and open the app, or `brew install ollama`
   and then start the server:
   ```bash
   ollama serve
   ```
2. **Pull the two models** (about 2 GB and about 300 MB):
   ```bash
   ollama pull llama3.2:3b
   ```
   ```bash
   ollama pull nomic-embed-text
   ```
3. **Check that Ollama answers and lists both models**:
   ```bash
   curl http://localhost:11434/api/tags
   ```
4. **Turn real mode on**: copy `.env.example` to `.env` (if you have no `.env` yet) and set
   `LLM_MODE=real`. `OLLAMA_URL`, `OLLAMA_MODEL` and `OLLAMA_EMBED_MODEL` must match step 2.
5. **Run the live tests**; they must now *run*, not show "skipped":
   ```bash
   .venv/bin/python -m unittest tests.test_llm_live -v
   ```
6. **Start the app** with `.venv/bin/python app.py` and check:
   - the sidebar says **"Local AI: Ollama llama3.2:3b"** instead of "MOCK AI". If it says
     "MOCK AI (Ollama or its models not found …)", Ollama isn't running or a model is missing;
   - "⏳ Preparing AI index…" lasts longer the first time: every chunk is re-embedded with
     nomic-embed-text because the embedding model changed (A-30); about 130 chunks;
   - chatbot: the example questions are answered in sentences, not quoted fragments, still
     labelled [Store data] / [General AI] / [Admin data]; a customer's "Tell me a joke" now gets
     a real [General AI] answer;
   - Reading Companion: summaries, explanations and quizzes written by the model; quizzes
     still show 4 options with hidden answers;
   - quit Ollama while the app runs, then ask something: "[Offline] The assistant is offline"
     (UC-12 E3); the companion still shows chapter text (UC-14 E4). Restart Ollama to continue.
7. **If store questions come back as [General AI]**, retrieval found nothing above
   `MIN_SIM_REAL = 0.45` (the SRS value, `bookorbit/ai/rag.py`). Measure like A-29:
   `ctx.rag.retrieve_scored(question, {"PUBLIC"})` shows the scores; lower the constant if
   relevant chunks score just under 0.45, and log the change in ASSUMPTIONS.
8. **To go back**, set `LLM_MODE=mock` (or remove it). The index is rebuilt with MOCK vectors
   at the next start. `LLM_MODE=offline` imitates a stopped Ollama for the offline demo.

`COVER_MODE=real` and `BIOMETRIC_MODE=real` are written but have never run (M-09). Real
biometrics would also need every user to re-register with real photos and recordings.

## Known quirks
- **Tk test hang (macOS):** creating a second `tk.Tk()` in one process after
  destroying the first can freeze inside `update()`. Keep every UI check in the single
  test `tests/test_ui_smoke.py::test_all_roles_in_one_window` (add steps there; don't
  add new Tk test methods or classes). Phase 3 steps: `visitor_chat`, `cover_search`,
  `phase3_flows`, `companion_flows`.
- **Background indexing in tests:** the smoke test waits for `ctx.ai_ready` in setUp and
  tearDown so the indexing thread never writes into a deleted temp folder.
- **Worker threads in tests:** the smoke test replaces `MainWindow.run_async` with a direct
  call, like `confirm` / `inform`.
- **Dialogs:** screens call `app.confirm(...)` / `app.inform(...)` instead of `messagebox`
  directly, so the smoke test can answer them (a real modal dialog would block the test).
- **Guard against hangs:** macOS has no `timeout` command. When a test might hang, run it with
  `-X faulthandler` and `faulthandler.dump_traceback_later(N, exit=True)`.
- **File paths in records** (`cover_path`, `cover_vec_path`, `text_path`, `vector_path`) are
  relative to `data/`; always open them through `fs.resolve(...)`.
- **Using the app writes to `data/`** (chat log, reading progress, index files). Run
  `seed.py` before a demo for a clean state.
- **MOCK thresholds are measured, not principled:** chatbot retrieval 0.15 (A-29), cover
  search 0.70 (A-33). Both were measured on the seeded data; new content may need a re-check.
- **No visual check of the GUI:** screenshots would need macOS Accessibility and
  Screen Recording permissions, which weren't granted. Verification = unit tests, the smoke
  test (real screens), a scripted run of the real window on the seeded data, and the user
  trying the app.
- `FileStore.lock` is an `RLock`. Wrap read-check-write sequences in `with fs.lock:`.
- `tests/helpers.TempStoreCase` gives each test a fresh temporary `data/`, plus
  `add_book`, `add_text_book`, `write_policies`, `add_user`, `session_for`, `user` and `taboo(...)`.
- `docs/SRS.md` was made with `pypdf` (installed only in a scratch folder, not in `.venv`).
