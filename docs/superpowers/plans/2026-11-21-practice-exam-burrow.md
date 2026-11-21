# Practice / Exam modes and the Burrow Pet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Practice mode with per-question checking (one retry, then the answer), give-up, optional timer and a burrow pet
that gives hints and solutions; Exam mode = today's contest mode, renamed, with no help.

**Architecture:** Extend `Attempt`/`Response` (additive nullable columns) and `app/practice/service.py`; a new
`app/helper.py` for hints/solutions (reusing `ensure_reference_solution`); htmx partials on the attempt page; a
burrow partial + SVG/CSS/JS. Downstream (results, feedback, upload, progress) learns to skip "helped out" misses.

**Tech Stack:** FastAPI, Jinja2, htmx, SQLAlchemy/SQLite, pytest + FakeAI. Run tests with
`.venv/bin/python -m pytest` (the venv's script shebangs point at the old folder name).

**Spec:** `docs/superpowers/specs/2026-11-21-practice-exam-burrow-design.md`

## Global Constraints
- Stored mode values stay `"practice"` / `"contest"`; the UI says **Practice** / **Exam**.
- All new columns nullable (added by `ensure_schema`): `Attempt.timer_on`, `Response.checked_at`, `Response.gave_up`,
  `Response.hints_used`, `Response.solution_seen`.
- Scoring identical in both modes, negative marking included; a blank give-up never loses points.
- Exam: no check, give-up, hint, solution or burrow; marked only at hand-in; auto hand-in at zero (as today).
- Practice timer never hands in.
- Copy: "Correct! 🎉", "Not quite, have another go!", "Got it on the second go! 💪", "The answer is {answer}.",
  "Hmm, let me think… 🤔", "My brain's foggy — try again in a bit.", "Time's up! Keep going or hand in.",
  hint 1: "This one smells like {technique name lowercased}! 🕵️ {about}", no tags: "Read it again slowly and draw a picture!".
- Pets grow only at hand-in (unchanged `growth`).

## Review Focus
1. A locked answer edited through the plain `POST /attempts/{id}/answer` → refused (400), answer unchanged. (Task 1)
2. Exam attempts posting to check / give-up / hint / solution → 403, nothing stored. (Tasks 2, 3)
3. Practice attempt with `timer_on` past the paper's duration still accepts answers and isn't handed in. (Task 2)
4. Two "show me the solution" requests before the first solve finishes → one Claude call. (Task 3)
5. Check / give-up / hint on a handed-in attempt → redirect to results, nothing changed. (Task 2)

---

### Task 1: Checking, giving up and locking in the service layer

**Files:**
- Modify: `app/models.py` (Attempt, Response), `app/practice/service.py`
- Test: `tests/test_practice_check.py`

**Interfaces:**
- Produces:
  - `Attempt.timer_on: bool | None`; `Response.checked_at: datetime | None`, `gave_up: bool | None`,
    `hints_used: int | None`, `solution_seen: bool | None`.
  - `Response.locked -> bool` (property): `gave_up` or `correct_first` is True or `correct_retry` is not None
    or `solution_seen`.
  - `Response.helped_out -> bool` (property): `gave_up` or (`solution_seen` and not (`correct_first` or `correct_retry`)).
  - `start_attempt(db, user, paper, mode, question_numbers, redo_of=None, timer_on=False) -> Attempt`.
  - `check_answer(db, attempt, number, raw) -> Literal["right", "wrong", "right_second", "wrong_second"]`;
    raises `ValueError` if exam mode, handed in, locked, or `raw` blank.
  - `give_up(db, attempt, number, raw: str | None = None) -> Response` (checks a typed, unchecked `raw` first as the
    first answer; then sets `gave_up` only if the question wasn't already right; locks). Raises `ValueError` in exam/handed-in.
  - `save_answer` raises `ValueError` when the response is locked or has been checked (`checked_at` set).
  - `submit`: `gave_up` with blank `first_answer` → `correct_first=False`, no penalty; checked responses keep their marks.
  - `misses(attempt)` excludes `helped_out`.

- [ ] **Step 1: Write the failing tests** in `tests/test_practice_check.py` (use `junior_paper`, `child`; answers from `q.problem.answer`):
  - `test_check_right_locks` → result `"right"`, `correct_first is True`, `locked`, `save_answer` raises.
  - `test_check_wrong_then_right_second` → `"wrong"` then `"right_second"`; `correct_first False`, `correct_retry True`,
    `retry_answer` set, `label == Label.careless_self_corrected`.
  - `test_check_wrong_twice` → `"wrong_second"`, locked, `correct_retry is False`.
  - `test_check_refused_in_exam` (mode `"contest"`) and `test_check_blank_refused` → `ValueError`.
  - `test_give_up_blank_is_a_miss_without_penalty`: paper question with `penalty=1`, give up blank, submit → `correct_first False`,
    `gave_up`, score unaffected by penalty, response in `start_redo` numbers, not in `misses()`.
  - `test_give_up_checks_typed_answer_first`: typed right answer → not `gave_up`, `correct_first True`.
  - `test_submit_keeps_checked_marks_and_marks_unchecked`.
  - `test_locked_answer_cannot_be_saved_via_route` (Review Focus 1): `child_client` POST `/attempts/{id}/answer` on a
    checked question → 400, answer unchanged.
  - `test_timer_on_stored`.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_practice_check.py -q` → FAIL (missing names).
- [ ] **Step 3:** Implement the interfaces above. The second-try path reuses `submit_retry`'s labelling (extract a shared
  `_apply_retry(response, raw)`; `submit_retry` keeps its handed-in guard). The `/answer` route maps `ValueError` to 400 (it does already).
- [ ] **Step 4:** Run the test file, then the full suite → PASS.
- [ ] **Step 5:** Commit `feat: practice checks, give-up and locked answers in the service layer`.

### Task 2: Practice / Exam on the attempt page

**Files:**
- Modify: `app/routes/practice.py`, `app/templates/attempt.html`, `app/templates/practice_home.html`, `app/static/app.css`
- Create: `app/templates/_check_panel.html`
- Test: `tests/test_practice_modes.py`

**Interfaces:**
- Consumes: Task 1 service functions.
- Produces: `POST /attempts/{id}/check` (form `q`, `answer`) and `POST /attempts/{id}/giveup` (form `q`, `answer`):
  with `HX-Request` → 200 `_check_panel.html` fragment (`id="check-panel-{n}"`); without → 303 to `/attempts/{id}?q={n}`;
  exam → 403; handed in → 303 to results; bad input → 400. `_check_panel.html` needs `a, r, pq, verdict` and is also
  included by `attempt.html` for the current question.
- `POST /practice/start` accepts `timer=1` (practice only) → `timer_on=True`.

- [ ] **Step 1: Failing tests** in `tests/test_practice_modes.py`:
  - `test_start_form_says_practice_and_exam`: home HTML has "Practice" and "Exam (" and no "Contest"; a "Use a timer" checkbox.
  - `test_practice_page_has_check_and_give_up` / `test_exam_page_has_neither` (`Check ✓`, `I give up`).
  - `test_check_fragment_right` / `_wrong` / `_wrong_twice_reveals_answer` (copy from Global Constraints, `HX-Request: 1`).
  - `test_give_up_reveals_answer`.
  - `test_exam_check_forbidden` (Review Focus 2), `test_check_after_hand_in_redirects` (Review Focus 5).
  - `test_practice_timer_never_hands_in` (Review Focus 3): `timer_on`, `started_at` moved back past `duration_min` →
    GET shows the page (200, `data-deadline` present, `data-soft`), POST answer still saves.
  - `test_locked_question_shows_verdict_not_input`.
  - `test_mcq_tap_in_practice_stays_on_question`: MCQ option buttons carry the current question in `go` (practice), next in exam.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. `deadline()` also returns a time for practice with `timer_on`; `is_expired` only applies
  to contest. Template timer script: `data-soft` → shows "Time's up! Keep going or hand in." instead of submitting.
  Rename "Contest" option label to "⏱️ Exam ({N} min, like the real thing)"; home "· timed" → "· exam".
- [ ] **Step 4:** Test file, full suite → PASS. Screenshot practice + exam pages (light/dark) and look.
- [ ] **Step 5:** Commit `feat: practice mode checks answers as you go; contest mode becomes Exam`.

### Task 3: Hints and solutions from the pet

**Files:**
- Create: `app/helper.py`, `app/templates/_burrow_say.html`
- Modify: `app/routes/practice.py` (or new `app/routes/helper.py` registered in `app/main.py`)
- Test: `tests/test_helper.py`

**Interfaces:**
- Consumes: `ensure_reference_solution(db, problem, crop_paths, ai) -> bool` (`app/diagnosis/service.py`),
  `give_up` (Task 1), `TECHNIQUES`.
- Produces:
  - `hint_one(problem) -> str` (Global Constraints copy; first tag in `TECHNIQUES` order).
  - `first_step(solution: str) -> str` (text of step "1." of a numbered solution).
  - `solution_state(problem) -> Literal["ready", "failed", "missing"]` (`verified` True / False / None).
  - `request_solve(app, problem_id) -> None`: background solve with a module-level in-flight set guard (one job per problem).
  - Routes (practice only; exam → 403; handed in → 303 results): `POST /attempts/{id}/help` form `q`, `kind` in
    `hint|hint2|solution` → `_burrow_say.html` fragment. `hint` → instant, `hints_used = max(1, …)`. `hint2`/`solution`
    → if `ready`, the step / full solution (+ "The answer is …" for solution); if `missing`, starts `request_solve`, returns
    the thinking fragment with `hx-get` polling `GET /attempts/{id}/help?q=&kind=` every 2s; if `failed` → answer only
    with "I couldn't work out the steps for this one…". `solution` calls `give_up(db, a, n, typed)` when not locked and sets
    `solution_seen`; `hint2` sets `hints_used = 2`.
  - AI error while solving → fragment "My brain's foggy — try again in a bit." (no polling).
- [ ] **Step 1: Failing tests** (FakeAI with `ReferenceSolution`): `test_hint_one_names_technique`, `test_hint_one_no_tags`,
  `test_first_step`, `test_hint_records_use`, `test_solution_ready_shows_steps_and_locks`,
  `test_solution_missing_starts_one_solve_and_polls` (two POSTs → `fake_ai.calls(ReferenceSolution) == 1`; Review Focus 4),
  `test_solution_unverifiable_gives_answer_only`, `test_help_forbidden_in_exam`, `test_ai_error_foggy`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Background solve opens its own session (pattern: `app/routes/parent_import._job`), commits the solution.
- [ ] **Step 4:** Test file, full suite → PASS.
- [ ] **Step 5:** Commit `feat: the pet gives hints and checked solutions on request`.

### Task 4: The burrow

**Files:**
- Create: `app/templates/_burrow.html`, `app/static/burrow.js`; Modify: `app/static/pets.css`, `app/templates/attempt.html`,
  `app/templates/base.html` (load `burrow.js`), `tests/test_pets_page.py::test_no_pets_on_question_pages` (now: none in exam)
- Test: `tests/test_burrow.py`

**Interfaces:**
- Consumes: Task 3 routes; `_buddy(db, user)` from `app/routes/practice.py`; `pet` macro.
- Produces: `.burrow` (button, `aria-expanded`) beside the question in practice only; out-of-burrow panel with
  Hint / Another hint / Show me the solution buttons (`hx-post` to `/attempts/{id}/help`), "Bye!" button; robot when no buddy;
  page JS calls `BBPets.play(slot, "happy")` on `.verdict-right` swaps (htmx `afterSwap`).
- [ ] **Step 1: Failing tests**: `test_burrow_in_practice`, `test_no_burrow_in_exam`, `test_burrow_robot_without_buddy`,
  `test_burrow_has_three_help_buttons`, updated `test_no_pets_on_question_pages` (exam attempt).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement: SVG mound + hole, pet hidden below the rim; `.out` class animates the jump; reduced-motion: no
  animation, just show. Sounds: `jingle` on pop-out. Wide screens: two-column (question | burrow); phones: burrow below.
- [ ] **Step 4:** Test file, full suite → PASS. Screenshots: closed, open with hint, thinking, solution; light/dark; 500px.
- [ ] **Step 5:** Commit `feat: the pet lives in a burrow beside practice questions`.

### Task 5: Results, feedback and progress after help

**Files:**
- Modify: `app/templates/results.html`, `app/routes/upload.py` (`_photo_allowed`), `app/templates/progress.html`
- Test: `tests/test_helped_results.py`

**Interfaces:**
- Consumes: `Response.helped_out`, `gave_up`, `solution_seen`, `hints_used`; `misses()` (Task 1).
- [ ] **Step 1: Failing tests**: `test_results_mark_gave_up` ("Gave up", no "Try again" form, no photo button),
  `test_results_mark_saw_solution`, `test_results_mark_used_hint` ("used a hint"), `test_photo_refused_for_gave_up` (400),
  `test_feedback_page_skips_gave_up`, `test_progress_lists_gave_up`, `test_redo_includes_gave_up`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Test file, full suite → PASS.
- [ ] **Step 5:** Commit `feat: results and progress show where he needed help`.
