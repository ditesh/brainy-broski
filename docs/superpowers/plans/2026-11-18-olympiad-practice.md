# Olympiad Practice Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A private, deployed web app where a child does past olympiad papers on screen, gets misses diagnosed as careless vs technique (using photos of paper working), and a parent sees progress.

**Architecture:** One FastAPI process renders Jinja2 pages (htmx for small dynamic bits), stores data in SQLite via SQLAlchemy, and keeps PDFs, crops, and photos on disk under `DATA_DIR`. PyMuPDF renders and crops PDFs. All Claude calls go through one thin wrapper (`app/ai/client.py`) that tests replace with a fake. Long jobs (import, diagnosis) run as FastAPI `BackgroundTasks` and record their status in the DB; pages poll with htmx.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, htmx 1.9.12 (unpkg, pinned), SQLAlchemy 2.x, SQLite, PyMuPDF, Pillow, `anthropic` SDK, pydantic v2, argon2-cffi, qrcode, pytest + httpx `TestClient`. Deployed with Docker on Fly.io and a mounted volume.

**Spec:** `docs/superpowers/specs/2026-11-18-olympiad-practice-design.md`

## Global Constraints

- Every page and every file under `DATA_DIR` requires login, **except** `GET/POST /u/{token}` (one-time photo upload), which accepts only an image upload for one response.
- Child role never receives an official answer, reference solution, or crop of an answer-key page for a question in an attempt that is not submitted (spec §5, anti-goals).
- Questions are always shown as **crop images**, never as transcribed text (anti-goal: retyped questions).
- An explanation/solution is shown only if the problem is `verified` (the reference solution reached the official answer); otherwise show "This one's tricky. Go through it with {parent display name}." (spec §6.3, §7).
- Import English sections only; the parent ticks categories (spec §6.1.7).
- Default category on the paper picker: `Junior`.
- Score is weighted by `points` per question (spec §6.2.4).
- Model: `CLAUDE_MODEL` env var, default `claude-opus-5-5`. Thinking is adaptive and cannot be disabled on this model; set `output_config.effort` per call (import tagging `low`, reference solve `high`, diagnosis `medium`). Always check `stop_reason == "refusal"` before reading content.
- Layout works at 360 px phone width with no horizontal scroll.
- Child-facing copy: short sentences, friendly coach voice, no unexplained jargon.
- Secrets only via env: `ANTHROPIC_API_KEY`, `SECRET_KEY`.

## Review Focus

1. **Answer typing variations.** "11 111 111 100", "11,111,111,100", "011", "+5", "(b)", "b", "2/4" vs "1/2", "0.5" vs "1/2" should be marked the way a human marker would. Pinned in Task 3.
2. **Real phone photos.** A 12 MP JPEG with EXIF rotation, a PNG screenshot, or an unsupported file (HEIC, PDF). The photo should be stored upright and resized to ≤2000 px; unsupported types get a friendly error, not a 500. Pinned in Task 9.
3. **Child pokes at URLs.** Feedback, answers, or review pages for an unsubmitted attempt, another user's attempt, or `/parent/*` should return 403/404 with no answer leaked. Pinned in Tasks 2 and 8.
4. **Claude call fails.** Network error, rate limit, or refusal during import or diagnosis. The import is marked `failed` with a retry button; the diagnosis is labelled `unsure`. Nothing crashes, and nothing is shown as a verified solution. Pinned in Tasks 6 and 10.
5. **Crop boundaries.** The last question on a page must not include the page-number footer. A question that runs onto the next page yields two images. A page with a "Part C (3 points each)" heading between questions must not put that heading in the previous question's crop. Pinned in Task 4.

---

## File Structure

```
pyproject.toml
Dockerfile, fly.toml, .dockerignore, README.md
app/
  config.py          Settings from env
  db.py              engine, SessionLocal, Base, get_db dependency
  models.py          all ORM tables + enums
  cli.py             create-user, seed-techniques, init-db
  main.py            create_app(): middleware, routers, templates, static
  auth.py            hashing, login/logout routes, current_user, require_parent, require_child_or_parent
  answers.py         normalise/compare answers (pure)
  techniques.py      seed list of technique tags + kid descriptions
  pdf/render.py      page rendering, anchor finding, cropping
  ai/client.py       AIClient protocol, AnthropicAIClient, AIError, AIRefusal
  ai/schemas.py      pydantic output models
  ai/prompts.py      system prompts
  importer/pipeline.py   run_import(source_pdf_id)
  importer/dedupe.py     link duplicates
  practice/service.py    attempts: start, save answer, submit, retry
  uploads.py         one-time tokens, image normalisation, storage
  diagnosis/service.py   ensure_reference_solution, diagnose_response
  followups.py       pick_followups, answer_followup
  progress.py        stats queries
  routes/parent_import.py, routes/parent_review.py, routes/practice.py,
  routes/feedback.py, routes/upload.py, routes/progress.py, routes/files.py
  templates/         base.html + one template per page
  static/app.css
tests/
  conftest.py        app + tmp DATA_DIR + in-memory DB + FakeAI + login helpers
  fixtures/make_pdf.py   builds synthetic contest PDFs with PyMuPDF (no copyrighted files in repo)
  test_*.py          one per module
```

---

### Task 1: Project scaffold, config, DB schema, CLI

**Files:**
- Create: `pyproject.toml`, `app/config.py`, `app/db.py`, `app/models.py`, `app/cli.py`, `app/main.py`, `app/techniques.py`, `tests/conftest.py`, `tests/test_models.py`, `.gitignore`
- Delete: the stray venv in repo root (`bin/`, `include/`, `lib/`, `pyvenv.cfg`) after confirming it holds no user files; use `.venv/` instead.

**Interfaces:**
- Produces:
  - `Settings` (pydantic-settings) with `database_url: str = "sqlite:///./data/app.db"`, `data_dir: Path = Path("./data")`, `secret_key: str`, `anthropic_api_key: str | None`, `claude_model: str = "claude-opus-5-5"`, `upload_token_minutes: int = 15`; `get_settings() -> Settings`.
  - `Base`, `make_engine(url) -> Engine`, `SessionLocal`, `get_db() -> Iterator[Session]`.
  - ORM models (table: key columns):
    - `User`: id, username (unique), display_name, role (`Role.parent|child`), password_hash
    - `SourcePdf`: id, filename, path, contest (str), year (int), duration_min (int|None), status (`ImportStatus.pending|running|needs_review|failed|done`), error (str|None), uploaded_at, structure (JSON|None)
    - `Paper`: id, source_pdf_id, category (str), language (str), duration_min, published (bool)
    - `Problem`: id, transcription, answer (str), answer_type (`AnswerType.integer|fraction|mcq|text`), reference_solution (str|None), verified (bool|None — None = not yet attempted), tags (JSON list[str])
    - `PaperQuestion`: id, paper_id, number (int), part (str), points (int), problem_id, crop_paths (JSON list[str]), crop_boxes (JSON list[[page, x0, y0, x1, y1]])
    - `Attempt`: id, user_id, paper_id, mode (`contest|practice`), question_numbers (JSON list[int]), started_at, submitted_at (None until submit), score (int|None), max_score (int|None)
    - `Response`: id, attempt_id, paper_question_id, first_answer, retry_answer, correct_first (bool|None), correct_retry (bool|None), photo_path, diagnosis (JSON|None), diagnosis_status (`none|pending|done|failed`), label (`Label.careless_self_corrected|careless|technique|unsure|None`), parent_override (Label|None)
    - `UploadToken`: token (pk), response_id, expires_at, used_at
    - `FollowupResponse`: id, user_id, problem_id, from_response_id, answer, correct, created_at
    - `Technique`: tag (pk), name, kid_description
  - CLI (`python -m app.cli`): `init-db`, `create-user USERNAME --role parent|child --display-name NAME` (prompts for password), `seed-techniques`.
  - `create_app(settings: Settings | None = None) -> FastAPI` with `GET /health -> {"ok": true}`.
  - `TECHNIQUES: list[tuple[tag, name, kid_description]]`: the spec §8 list, ~30 entries.

- [ ] **Step 1:** `git init`, add `.gitignore` (`.venv/`, `data/`, `__pycache__/`, `.env`), create `.venv` with Python 3.12, write `pyproject.toml` with the Tech Stack deps plus `pydantic-settings`, `python-multipart`, `itsdangerous`, and dev deps `pytest`, `httpx`.
- [ ] **Step 2: Write failing tests** in `tests/test_models.py`:
  ```python
  def test_health(client): assert client.get("/health").json() == {"ok": True}
  def test_create_user_and_hash(db):
      u = create_user(db, "dad", "Dad", Role.parent, "pw")
      assert u.password_hash != "pw" and verify_password("pw", u.password_hash)
  def test_seed_techniques_idempotent(db):
      seed_techniques(db); seed_techniques(db)
      assert db.query(Technique).count() == len(TECHNIQUES) >= 25
  ```
  `conftest.py` provides `settings` (tmp `data_dir`, `sqlite://` in-memory with `StaticPool`), `db`, `client`, and `fake_ai` (Task 5 fills it in; for now a stub).
- [ ] **Step 3:** Run `pytest -q`. Expected: FAIL (imports missing).
- [ ] **Step 4:** Implement the files above. `create_user`, `verify_password`, and `hash_password` (argon2) live in `app/auth.py`; `seed_techniques(db)` lives in `app/techniques.py`.
- [ ] **Step 5:** Run `pytest -q`. Expected: PASS.
- [ ] **Step 6:** Commit `feat: scaffold app, schema, CLI`.

### Task 2: Login, roles, route guards

**Files:** Modify `app/auth.py`, `app/main.py`; create `app/templates/base.html`, `app/templates/login.html`, `app/static/app.css`, `tests/test_auth.py`

**Interfaces:**
- Consumes: `User`, `Role`, `get_db`.
- Produces: `current_user(request, db) -> User` (redirects to `/login` if absent), `require_parent` and `require_user` FastAPI dependencies, `login_as(client, username, password)` test helper in conftest, session via Starlette `SessionMiddleware(secret_key)`. `GET /` redirects the parent to `/parent` and the child to `/practice`.

- [ ] **Step 1: Write failing tests:**
  ```python
  def test_login_redirects_by_role(client, parent, child):
      assert login_as(client, "dad", "pw").headers["location"] == "/parent"
  def test_bad_password_shows_error(client, parent):
      r = client.post("/login", data={"username": "dad", "password": "x"})
      assert r.status_code == 401 and "Wrong username or password" in r.text
  def test_anonymous_redirected(client): assert client.get("/practice", follow_redirects=False).headers["location"] == "/login"
  def test_child_blocked_from_parent_pages(client, child):
      login_as(client, "kid", "pw")
      assert client.get("/parent").status_code == 403
  ```
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. `base.html` loads `app.css` and `https://unpkg.com/htmx.org@1.9.12`, with a top bar (user name, logout) and a mobile viewport meta. CSS: system font, max-width 760px container, 16px gutters, large tap targets.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: login and role guards`.

### Task 3: Answer normalisation and marking

**Files:** Create `app/answers.py`, `tests/test_answers.py`

**Interfaces:**
- Produces: `normalise(raw: str, answer_type: AnswerType) -> str | None` (None = unparseable), `is_correct(given: str, official: str, answer_type: AnswerType) -> bool`.

Rules: **integer**: strip spaces, commas, underscores, and a leading `+`; drop leading zeros; allow `-`. **fraction**: parse `a/b`, a decimal, or an integer with `fractions.Fraction`; compare by value. **mcq**: strip, drop surrounding `()`, uppercase, must be a single letter A–E. **text**: casefold, collapse whitespace.

- [ ] **Step 1: Write failing tests** (Review Focus 1):
  ```python
  @pytest.mark.parametrize("given", ["11111111100", "11 111 111 100", "11,111,111,100", "011111111100"])
  def test_big_integer_forms(given): assert is_correct(given, "11111111100", AnswerType.integer)
  def test_plus_sign(): assert is_correct("+5", "5", AnswerType.integer)
  def test_wrong_integer(): assert not is_correct("54", "56", AnswerType.integer)
  def test_garbage_integer_is_wrong_not_error(): assert not is_correct("abc", "5", AnswerType.integer)
  @pytest.mark.parametrize("given", ["1/2", "2/4", "0.5", " 1 / 2 "])
  def test_fraction_equivalents(given): assert is_correct(given, "1/2", AnswerType.fraction)
  @pytest.mark.parametrize("given", ["b", "B", "(b)", " B "])
  def test_mcq_forms(given): assert is_correct(given, "B", AnswerType.mcq)
  def test_mcq_out_of_range(): assert normalise("F", AnswerType.mcq) is None
  def test_empty_is_none(): assert normalise("  ", AnswerType.integer) is None
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: answer normalisation`.

### Task 4: PDF rendering and question cropping

**Files:** Create `app/pdf/render.py`, `tests/fixtures/make_pdf.py`, `tests/test_render.py`

**Interfaces:**
- Produces:
  - `render_pages(pdf_path: Path, out_dir: Path, dpi: int = 150) -> list[Path]` (one PNG per page, `page-{n:03}.png`, 1-based)
  - `has_text_layer(pdf_path) -> bool`
  - `find_anchors(pdf_path, pages: list[int]) -> list[Anchor]` where `Anchor(number: int, page: int, y: float)`. Matches words `Problem N.`, `Question N.`, `Soalan N.`, and `N.` at the left margin, in reading order.
  - `find_cut_lines(pdf_path, page) -> list[float]`: y of headings matching `^Part [A-Z]` / `^Section` / `^Bahagian`, plus the top of the footer (any text block in the bottom 8% of the page).
  - `crop_questions(pdf_path, anchors, out_dir, dpi=150) -> dict[int, list[CropBox]]`, where `CropBox(page, x0, y0, x1, y1, path)`. Each question runs from its anchor's y (minus 4 pt) to the next anchor, cut line, or footer on the same page. If its page ends first, it continues on the next page from the top margin to the first anchor or cut line there. Full page width minus margins.
  - `crop_box(pdf_path, page, box, out_path, dpi=150) -> Path` (used when the parent nudges a crop).
- `make_pdf.py`: `build_contest_pdf(path, layout)` writes a PDF with text "Part A (1 point each)", "Problem 1. …", a page-number footer, an answer page "Problem 1. 21", etc. Used by Tasks 4, 6, and 7.

- [ ] **Step 1: Write failing tests** (Review Focus 5):
  ```python
  def test_anchors_found_in_order(sample_pdf): assert [a.number for a in find_anchors(sample_pdf, [1, 2])] == [1, 2, 3, 4, 5, 6]
  def test_last_question_excludes_footer(sample_pdf, tmp_path):
      crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [1]), tmp_path)
      footer_y = page_height(sample_pdf, 1) * 0.92
      assert crops[3][0].y1 < footer_y
  def test_part_heading_not_in_previous_crop(sample_pdf, tmp_path):  # "Part B" heading sits between Q5 and Q6 on page 2
      crops = crop_questions(sample_pdf, find_anchors(sample_pdf, [2]), tmp_path)
      assert crops[5][0].y1 <= heading_y(sample_pdf, 2, "Part B")
  def test_question_spanning_pages_has_two_images(spanning_pdf, tmp_path):
      crops = crop_questions(spanning_pdf, find_anchors(spanning_pdf, [1, 2]), tmp_path)
      assert [c.page for c in crops[2]] == [1, 2]
  def test_scanned_pdf_detected(image_only_pdf): assert has_text_layer(image_only_pdf) is False
  def test_render_pages_count(sample_pdf, tmp_path): assert len(render_pages(sample_pdf, tmp_path)) == 3
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement with `fitz` (`page.get_text("words")` for anchors, `page.get_pixmap(clip=rect, dpi=dpi)` for crops).
- [ ] **Step 4:** Run. Expected: PASS. Then run one manual check against the real IMONST 2020 PDF (download it to a scratch dir; do not commit it): Junior English pages 21–24 should give 20 anchors, with no footer in any crop.
- [ ] **Step 5:** Commit `feat: pdf rendering and cropping`.

### Task 5: Claude wrapper and output schemas

**Files:** Create `app/ai/client.py`, `app/ai/schemas.py`, `app/ai/prompts.py`, `tests/test_ai_client.py`; fill in `fake_ai` in `tests/conftest.py`

**Interfaces:**
- Produces:
  - `class AIError(Exception)`; `class AIRefusal(AIError)`.
  - `Protocol AIClient`: `structured(schema: type[T], system: str, images: list[Path], text: str, effort: str) -> T`.
  - `AnthropicAIClient(api_key, model)`: builds a user message of base64 image blocks (media type from extension) followed by a text block, and calls `client.messages.parse(model=..., max_tokens=16000, system=..., messages=..., output_format=schema, output_config={"effort": effort})`. If `stop_reason == "refusal"` it raises `AIRefusal`; on `anthropic.APIError` / `APIConnectionError` it raises `AIError`; it returns `response.parsed_output`. Before writing, check against the installed SDK that `parse` accepts `output_config` alongside `output_format`. If not, pass effort via `extra_body`.
  - `get_ai(settings) -> AIClient` (FastAPI dependency; tests override it with `FakeAI`).
  - `FakeAI` (tests): queue of canned results/exceptions per schema type; records calls.
  - Schemas (pydantic):
    - `PdfStructure`: `sections: list[Section(category: str, language: Literal["en","ms","other"], first_page: int, last_page: int, parts: list[Part(name: str, points: int, first_question: int, last_question: int)])]`, `answer_keys: list[AnswerKey(category: str, page: int, answers: dict[int, str])]`
    - `QuestionAnalysis`: `transcription: str`, `answer_type: AnswerType`, `tags: list[str]` (1–3, must be known tags, unknown dropped)
    - `ReferenceSolution`: `steps: list[str]`, `final_answer: str`
    - `Diagnosis`: `label: Literal["careless","technique","unsure"]`, `wrong_step: str | None`, `technique_tag: str | None`, `hint: str`, `explanation: str`
  - `prompts.py` constants (one paragraph each): `STRUCTURE_SYSTEM` (find categories/languages/parts/answer-key pages from page images), `ANALYSE_SYSTEM` (transcribe the question to Markdown+LaTeX, classify the answer type, pick tags only from the provided list), `SOLVE_SYSTEM` (solve step by step at a level a strong 12-year-old can follow; the final answer is in the same form as the contest answer), `DIAGNOSE_SYSTEM` (friendly coach for a 12-year-old: compare the child's working with the reference solution, find the first wrong step and quote it, label careless if the method was right but execution slipped and technique if the method was missing or wrong, return `unsure` without a photo unless the wrong answer is an obvious slip, give a hint that doesn't reveal the answer, short sentences).

- [ ] **Step 1: Write failing tests** (mock `anthropic.Anthropic` with `unittest.mock`):
  ```python
  def test_images_sent_before_text(mock_sdk, tmp_png):
      AnthropicAIClient("k", "claude-opus-5-5").structured(ReferenceSolution, "sys", [tmp_png], "solve", "high")
      content = mock_sdk.messages.parse.call_args.kwargs["messages"][0]["content"]
      assert [b["type"] for b in content] == ["image", "text"]
  def test_refusal_raises(mock_sdk_refusal, tmp_png):
      with pytest.raises(AIRefusal): AnthropicAIClient("k", "m").structured(ReferenceSolution, "s", [], "t", "low")
  def test_api_error_wrapped(mock_sdk_conn_error):
      with pytest.raises(AIError): ...
  def test_unknown_tags_dropped(): assert QuestionAnalysis(transcription="x", answer_type="integer", tags=["parity", "nonsense"]).tags == ["parity"]
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. The tag validator reads the known tags from `app.techniques.TECHNIQUES`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: claude wrapper and schemas`.

### Task 6: Import pipeline

**Files:** Create `app/importer/pipeline.py`, `app/importer/dedupe.py`, `tests/test_import.py`

**Interfaces:**
- Consumes: `render_pages`, `has_text_layer`, `find_anchors`, `crop_questions` (Task 4); `AIClient`, `PdfStructure`, `QuestionAnalysis` (Task 5); `normalise` (Task 3).
- Produces:
  - `detect_structure(source_pdf_id, db, ai) -> PdfStructure`: renders pages, sends all page images in one call (`effort="low"`), stores the JSON on `SourcePdf.structure`, and sets status `needs_review`.
  - `run_import(source_pdf_id, categories: list[str], db, ai, settings) -> None`: for each chosen English section it creates a `Paper` (unpublished). For each question it crops; if there is no text layer it uses one extra `structured` call per page returning boxes (add a `PageBoxes` schema: `list[Box(number, x0, y0, x1, y1)]` in page-fraction coordinates). It calls `QuestionAnalysis` per crop (`effort="low"`), takes the answer from the answer key (normalised), and creates `Problem` + `PaperQuestion`, then calls `link_duplicates`. Status becomes `done`. On `AIError` it sets status `failed` and stores `error`, keeping papers already created as unpublished.
  - `link_duplicates(db, source_pdf_id) -> int`: within one source PDF, questions with an equal normalised answer **and** `difflib.SequenceMatcher` ratio ≥ 0.9 on whitespace-collapsed transcriptions share one `Problem` (keep the lowest id, repoint the others, delete the orphans). Returns the number merged.

- [ ] **Step 1: Write failing tests** (FakeAI + synthetic PDF with Primary and Junior English sections, where Junior Q1 = Primary Q6):
  ```python
  def test_import_creates_papers_for_ticked_categories(db, fake_ai, contest_pdf_record):
      run_import(src.id, ["Junior"], db, fake_ai, settings)
      assert [p.category for p in db.query(Paper)] == ["Junior"]
      assert db.query(PaperQuestion).count() == 20
  def test_answers_come_from_key(...): assert pq(1).problem.answer == "4"
  def test_points_from_parts(...): assert pq(16).points == 4
  def test_duplicates_linked_across_categories(...):  # import Primary + Junior
      assert pq("Junior", 1).problem_id == pq("Primary", 6).problem_id
  def test_ai_failure_marks_failed_and_keeps_going_safe(db, fake_ai_raising, ...):
      run_import(...); assert src.status == ImportStatus.failed and src.error
      assert all(not p.published for p in db.query(Paper))
  def test_malay_sections_never_imported(...): assert all(p.language == "en" for p in db.query(Paper))
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: import pipeline`.

### Task 7: Parent import and review screens

**Files:** Create `app/routes/parent_import.py`, `app/routes/parent_review.py`, `app/routes/files.py`, templates `parent_home.html`, `import_upload.html`, `import_sections.html`, `review.html`, `review_question.html`; `tests/test_parent_ui.py`

**Interfaces:**
- Consumes: Task 6 functions, `crop_box`, `require_parent`, `get_ai`.
- Produces routes (all `require_parent` except files):
  - `GET /parent`: list of source PDFs with status, papers, and a link to progress.
  - `GET/POST /parent/import`: upload form (file, contest select, year, duration). POST saves to `DATA_DIR/pdfs/{id}.pdf` and starts `detect_structure` in the background.
  - `GET /parent/import/{id}`: polls status (htmx `hx-trigger="every 2s"` while running), then shows the English sections as checkboxes. POST starts `run_import`. A `failed` status shows the error and a **Retry** button.
  - `GET /parent/papers/{paper_id}/review`: grid of questions (crop images, number, points, answer, type, tags, duplicate badge).
  - `POST /parent/questions/{pq_id}`: update answer / answer_type / points / tags; `POST /parent/questions/{pq_id}/crop` with `dy0, dy1` nudges (±20 pt) re-crops via `crop_box`; `POST /parent/questions/{pq_id}/unlink` splits a shared Problem. `POST /parent/questions/{pq_id}/link` with `other_pq_id` merges two questions into one Problem (the official answers must be equal, or it returns 400).
  - `POST /parent/papers/{paper_id}/publish`.
  - `GET /files/{path:path}`: serves files under `DATA_DIR` to any logged-in user, with a path traversal guard. Child access is limited to `crops/` and that child's own `photos/`.

- [ ] **Step 1: Write failing tests:**
  ```python
  def test_upload_starts_structure_detection(parent_client, fake_ai, contest_pdf_bytes): ...status in {running, needs_review}
  def test_review_edit_answer(parent_client, imported_paper): post answer "5" -> problem.answer == "5"
  def test_publish_makes_paper_visible_to_child(...)
  def test_child_cannot_fetch_pdf_or_review(child_client, imported_paper):
      assert child_client.get(f"/parent/papers/{imported_paper.id}/review").status_code == 403
      assert child_client.get("/files/pdfs/1.pdf").status_code == 403
  def test_files_path_traversal_blocked(parent_client): assert parent_client.get("/files/../app.db").status_code == 404
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Background tasks open their own DB session (not the request's).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: parent import and review UI`.

### Task 8: Doing a paper: attempts, answering, submit, retry

**Files:** Create `app/practice/service.py`, `app/routes/practice.py`, templates `practice_home.html`, `attempt.html`, `attempt_question.html`, `results.html`; `tests/test_practice.py`

**Interfaces:**
- Consumes: `is_correct`, models.
- Produces:
  - `start_attempt(db, user, paper, mode, question_numbers: list[int] | None) -> Attempt` (None = all questions)
  - `save_answer(db, attempt, number, raw) -> None` (idempotent; refused after submit)
  - `submit(db, attempt) -> Attempt`: marks every answered question, sets `score` (sum of points where `correct_first`) and `max_score` (sum of points of the chosen questions). Blank answers get `correct_first=None` and are not counted as misses.
  - `submit_retry(db, response, raw) -> Response`: allowed once, only when `correct_first is False`. A correct retry sets `label=careless_self_corrected`.
  - `misses(attempt) -> list[Response]`: responses with `correct_first is False and correct_retry is not True`.
  - Routes: `GET /practice` (picker: contest → year → category, default `Junior`; lists in-progress attempts to resume), `POST /practice/start`, `GET /attempts/{id}?q=N` (one question, an answer box suited to its type: numeric keyboard via `inputmode="numeric"` for integer, A–E buttons for mcq; a navigator; a timer in contest mode computed from `started_at` + `duration_min`, which auto-submits at zero), `POST /attempts/{id}/answer` (htmx autosave), `POST /attempts/{id}/submit`, `GET /attempts/{id}/results` (score; each miss with a retry box; after the retry, a "Take a photo of your working" button linking to Task 9 and a "Skip photo" button).

- [ ] **Step 1: Write failing tests** (Review Focus 3):
  ```python
  def test_score_weighted_by_points(db, junior_paper, child):
      a = start_attempt(db, child, junior_paper, "practice", None)
      save_answer(db, a, 1, "4"); save_answer(db, a, 16, "53"); save_answer(db, a, 2, "99")
      submit(db, a); assert (a.score, a.max_score) == (1 + 4, 50)
  def test_subset_max_score(db, junior_paper, child): start_attempt(..., [11, 12]) -> max_score == 6
  def test_blank_not_a_miss(...): assert response(3).correct_first is None and response(3) not in misses(a)
  def test_retry_correct_is_careless_self_corrected(...)
  def test_retry_only_once(...): second submit_retry raises ValueError
  def test_cannot_answer_after_submit(...)
  def test_child_cannot_see_results_before_submit(child_client, attempt): assert child_client.get(f"/attempts/{attempt.id}/results").status_code == 404
  def test_child_cannot_open_other_users_attempt(child2_client, attempt): assert child2_client.get(f"/attempts/{attempt.id}").status_code == 404
  def test_attempt_page_never_contains_official_answer(child_client, attempt):  # answer "11111111100" is distinctive
      assert "11111111100" not in child_client.get(f"/attempts/{attempt.id}?q=14").text
  def test_resume_keeps_answers(...)
  def test_unpublished_paper_not_listed(...)
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: attempts, marking, retry round`.

### Task 9: Photo upload (QR to phone, or laptop)

**Files:** Create `app/uploads.py`, `app/routes/upload.py`, templates `photo.html`, `phone_upload.html`; `tests/test_uploads.py`

**Interfaces:**
- Consumes: `Response`, `UploadToken`, `settings.upload_token_minutes`.
- Produces:
  - `new_upload_token(db, response) -> UploadToken` (`secrets.token_urlsafe(16)`, expires in `upload_token_minutes`)
  - `store_photo(db, response, file_bytes: bytes) -> Path`: opens with Pillow, applies `ImageOps.exif_transpose`, converts to RGB, resizes so the longest side is ≤2000 px, saves JPEG q=85 to `photos/{user_id}/{response_id}.jpg`, sets `response.photo_path`. It raises `UnsupportedImage` for anything Pillow can't open.
  - Routes: `GET /responses/{id}/photo` (logged in, owner; shows a QR code as inline SVG via `qrcode` for `{base_url}/u/{token}`, plus `<input type=file accept="image/*" capture="environment">` for the laptop; htmx polls until a photo arrives, then enqueues diagnosis via Task 10's `enqueue_diagnosis`). `POST /responses/{id}/photo` (laptop upload). `GET/POST /u/{token}` (no login: a page with a big "Take photo" button; POST stores the photo and marks the token used; an expired or used token gets "This link has expired — make a new one on the laptop."). `POST /responses/{id}/skip-photo` enqueues diagnosis without a photo.

- [ ] **Step 1: Write failing tests** (Review Focus 2):
  ```python
  def test_exif_rotated_photo_stored_upright(db, miss_response, rotated_jpeg_bytes):  # 4000x3000 with Orientation=6
      p = store_photo(db, miss_response, rotated_jpeg_bytes)
      w, h = Image.open(p).size; assert h > w and max(w, h) == 2000
  def test_png_accepted(...)
  def test_unsupported_file_friendly_error(client_phone, token): r = post pdf bytes -> r.status_code == 400 and "photo" in r.text.lower()
  def test_token_single_use(client, token): first POST 200, second POST 410
  def test_token_expires(db, token, freezer): advance 16 min -> 410
  def test_token_route_cannot_read_anything(client, token): assert client.get(f"/u/{token}").text has no answer/crop paths
  def test_other_child_cannot_open_photo_page(...)
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement (add `freezegun` to dev deps).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: photo upload via QR or laptop`.

### Task 10: Diagnosis and feedback page

**Files:** Create `app/diagnosis/service.py`, `app/routes/feedback.py`, templates `feedback.html`, `feedback_card.html`; `tests/test_diagnosis.py`

**Interfaces:**
- Consumes: `AIClient`, `ReferenceSolution`, `Diagnosis`, `is_correct`, `Problem`, `Response`.
- Produces:
  - `ensure_reference_solution(db, problem, crop_paths, ai) -> bool`: if `problem.verified is not None`, return it. Otherwise call `SOLVE_SYSTEM` (`effort="high"`) up to 2 times. On the first result where `is_correct(final_answer, problem.answer, type)`, store the joined steps and set `verified=True`. Otherwise set `verified=False`. An `AIError` leaves `verified=None` (retry later) and returns False.
  - `diagnose_response(db, response_id, ai) -> None`: sets `diagnosis_status=pending`, then calls `ensure_reference_solution`. If it is not verified: `label=unsure`, `diagnosis={"unverified": True}`, `status=done`. Otherwise it calls `DIAGNOSE_SYSTEM` (`effort="medium"`) with images `[*crops, photo?]`, text containing the official answer, the reference solution, the first and retry answers, and whether a photo is present. It stores `Diagnosis.model_dump()` and `label`. On `AIError` it sets `label=unsure` and `diagnosis_status=failed` (the parent can re-run).
  - `enqueue_diagnosis(background_tasks, response_id)`: schedules it with its own DB session.
  - Routes: `GET /attempts/{id}/feedback` (one card per miss, each polling until done), `GET /responses/{id}/feedback` (the card). The card shows the label chip; for careless, the quoted wrong step; for technique, the hint, then a "Show full solution" `<details>`, then the technique name + kid description, then follow-ups (Task 11). For unsure or unverified it shows the "This one's tricky. Go through it with {parent display name}." text, using the first parent user's `display_name`. `POST /parent/responses/{id}/rediagnose` (parent).

- [ ] **Step 1: Write failing tests** (Review Focus 4):
  ```python
  def test_verified_solution_cached(db, fake_ai, problem): two calls -> fake_ai.calls(ReferenceSolution) == 1
  def test_second_try_can_verify(...): first final_answer wrong, second right -> verified True
  def test_unverified_never_shows_solution(child_client, response_unverified):
      html = child_client.get(f"/responses/{response_unverified.id}/feedback").text
      assert "Go through it with Dad" in html and "Show full solution" not in html   # parent display_name = "Dad" in fixture
  def test_ai_error_gives_unsure(db, fake_ai_raising, response): diagnose_response(...); assert response.label == Label.unsure
  def test_refusal_gives_unsure(...)
  def test_diagnosis_sends_photo_last(db, fake_ai, response_with_photo): assert fake_ai.last_call.images[-1].name.endswith(".jpg")
  def test_careless_card_quotes_step(child_client, careless_response): assert "7 × 8 = 54" in html
  def test_feedback_404_before_submit(...)
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Render the solution and explanation as Markdown + LaTeX on the page using KaTeX 0.16.11 auto-render (jsDelivr, pinned) and `markdown-it-py` server-side.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: diagnosis and feedback`.

### Task 11: Follow-up questions

**Files:** Create `app/followups.py`, template `followup.html`; extend `app/routes/feedback.py`; `tests/test_followups.py`

**Interfaces:**
- Consumes: `Problem.tags`, `PaperQuestion`, `FollowupResponse`, `is_correct`, `ensure_reference_solution`.
- Produces:
  - `pick_followups(db, user, response, tag: str, n: int = 2) -> list[PaperQuestion]`: published papers only; the problem has `tag`; problem ≠ the missed problem; excludes problems the user answered (in attempts or follow-ups) in the last 30 days; one `PaperQuestion` per problem, preferring the same category as the missed paper, then any. Uses a stable random order seeded by `response.id`.
  - `answer_followup(db, user, response, pq, raw) -> FollowupResponse`.
  - Routes: `POST /responses/{id}/followups/{pq_id}` (htmx). It shows "Correct!" or "Not quite — the answer is X", plus the verified solution if one exists, otherwise the parent message.
- Only shown for `label == technique` with a `technique_tag`. With none available: "No more practice questions for this technique yet."

- [ ] **Step 1: Write failing tests:**
  ```python
  def test_excludes_same_problem_and_duplicates(...)  # Junior Q1 duplicate of Primary Q6 never offered for a Q1 miss
  def test_excludes_recently_answered(...)
  def test_prefers_same_category(...)
  def test_unpublished_excluded(...)
  def test_none_available_message(child_client, ...)
  def test_followup_wrong_reveals_answer(child_client, ...)
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: follow-up questions`.

### Task 12: Progress page and parent overrides

**Files:** Create `app/progress.py`, `app/routes/progress.py`, template `progress.html`; `tests/test_progress.py`

**Interfaces:**
- Consumes: `Attempt`, `Response`, `FollowupResponse`, `Technique`.
- Produces:
  - `effective_label(response) -> Label | None` (= `parent_override or label`)
  - `paper_history(db, user) -> list[Row(date, paper_title, score, max_score, minutes)]`
  - `miss_breakdown(db, user, since: date | None) -> dict[Label, int]` and `miss_breakdown_by_week(db, user, weeks=8) -> list[(week_start, dict[Label, int])]`
  - `technique_table(db, user, recent_days=30) -> list[Row(tag, name, attempts, misses, recent_misses, flagged: bool)]` where `flagged = recent_misses >= 2`. Attempts count paper responses + follow-ups whose problem has the tag.
  - Routes: `GET /progress` (child: own; parent: `?user=` selects a child, default the first child). It has a stacked bar of labels per week (inline SVG, no chart lib), the technique table sorted by flagged then misses, the paper history, and recent misses linking to feedback. `POST /parent/responses/{id}/override` sets `parent_override`.

- [ ] **Step 1: Write failing tests:**
  ```python
  def test_override_changes_breakdown(db, ...): override technique -> careless; miss_breakdown counts careless
  def test_flagged_after_two_recent_misses(...)
  def test_followups_count_toward_technique_attempts(...)
  def test_child_cannot_override(child_client, ...) -> 403
  def test_child_sees_only_own_progress(child_client, ...): ?user=<other> ignored
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: progress page and overrides`.

### Task 13: Deployment

**Files:** Create `Dockerfile`, `.dockerignore`, `fly.toml`, `README.md`; `tests/test_settings.py`

**Interfaces:**
- Consumes: `create_app`, `app.cli`.
- Produces: an image running `uvicorn app.main:app --host 0.0.0.0 --port 8080` with `DATA_DIR=/data` and `DATABASE_URL=sqlite:////data/app.db`. `fly.toml` mounts the volume `data` at `/data`, uses a single machine (`min_machines_running = 1`, no autoscale beyond 1, since SQLite needs one writer), sets `force_https = true`. An `entrypoint.sh` runs `python -m app.cli init-db && python -m app.cli seed-techniques` (both idempotent) and then uvicorn. It runs at container start rather than as a Fly `release_command`, because release commands don't see the volume. The README covers local dev, `fly launch --no-deploy`, `fly volumes create data --size 1`, `fly secrets set SECRET_KEY=... ANTHROPIC_API_KEY=...`, `fly deploy`, creating users with `fly ssh console -C "python -m app.cli create-user ..."`, and backups (Fly's daily volume snapshots, kept 5 days; plus `scripts/backup.sh`, which runs `sqlite3 /data/app.db ".backup /data/backups/app-$(date +%F).db"` and can be fetched with `fly ssh sftp get`).

- [ ] **Step 1: Write failing test:**
  ```python
  def test_missing_secret_key_fails_fast(monkeypatch): monkeypatch.delenv("SECRET_KEY", raising=False); with pytest.raises(ValidationError): Settings()
  ```
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the files.
- [ ] **Step 4:** Verify: `docker build -t olympiad . && docker run --rm -e SECRET_KEY=x -p 8080:8080 -v $PWD/data:/data olympiad`, then `curl localhost:8080/health` should return `{"ok":true}`. Run the full `pytest -q`. Expected: all PASS.
- [ ] **Step 5:** End-to-end smoke test with the real API key, locally: create users, import the IMONST 2020 PDF, tick Junior, review, publish, do Part A with two deliberately wrong answers, retry one correctly, photograph working for the other, and confirm the labels and feedback appear.
- [ ] **Step 6:** Commit `chore: docker and fly deployment`.
