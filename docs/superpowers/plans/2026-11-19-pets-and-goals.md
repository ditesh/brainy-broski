# Pets, Weekly Goals and Celebrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the child a self-set weekly goal, a collection of animated technique pets that grow with mastery, and celebratory results with sound.

**Architecture:** Goal progress and pet growth are *derived* from existing `Response`/`FollowupResponse` rows (single source of truth, matching `technique_table`'s first-answer rule); only goal history, bonus eggs, buddy and mute are stored. Creatures are SVG built from Jinja macros on a shared rig (8 body types × 3 stages + technique features), animated with CSS, with small vanilla JS for eye-tracking, tickles, replays and Web Audio sounds.

**Tech Stack:** FastAPI, Jinja2, htmx, SQLite/SQLAlchemy (`ensure_schema` for new nullable columns, `create_all` for new tables), vanilla JS, CSS, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-pets-and-goals-design.md`

## Global Constraints

- Weeks run Monday–Sunday in `settings.timezone` (Asia/Kuala_Lumpur). DB datetimes are naive UTC (`utcnow()`).
- Goal: whole number 1–200. First goal applies to the current week; later changes apply from next Monday.
- Counts toward goal: distinct problems with a non-blank first answer in a *submitted* attempt that week, plus follow-up problems answered that week. Right or wrong both count.
- Growth: correct first time = weight (1–3: rank of the question's points among the distinct point values in its paper; single value → 2); correct on retry or later correct after a first miss = 1, once per problem; correct follow-up = 1 per follow-up problem; wrong = 0. Only tags in `app/techniques.py`.
- Stages: egg 0–1, baby 2–14, grown-up 15+.
- Bonus egg: once per met week, +2 growth to a random shown pet still at 0 (else the pet closest to 15).
- No pets or celebrations on question pages. No guilt copy. Tap works everywhere hover does. Honour `prefers-reduced-motion`.
- Use CSS tokens in `app/static/app.css` (font sizes via `--fs-*`; `tests/test_typography.py` enforces). Dark mode must stay readable.
- Child-facing copy short and warm. Tests run with `.venv/bin/pytest -q`; the full suite stays green after every task.

## Review Focus

- A paper submitted Sunday 23:30 local (15:30 UTC) counts for that week; Monday 00:30 local (Sunday 16:30 UTC) counts for the next — Task 1 `test_week_boundary_uses_local_time`.
- A brand-new child (no answers, no goal, maybe no published papers) gets working home, pets and results pages with mystery eggs and a goal prompt, no crash — Task 5 `test_pets_page_for_brand_new_child`.
- Unsubmitted/expired-unsubmitted attempts and blank answers neither count toward the goal nor grow pets — Task 1 `test_unsubmitted_and_blank_do_not_count`, Task 3 `test_blank_and_unsubmitted_do_not_grow`.
- Re-opening results (by child or parent) never awards a second bonus egg and only celebrates growth from *that* attempt — Task 6 `test_reopening_results_awards_once`.
- A problem with several tags grows each; unknown tags are ignored; an untagged problem still counts toward the goal — Task 3 `test_multi_tag_and_unknown_tags`.

---

### Task 1: Weekly goal model and maths

**Files:**
- Create: `app/goals.py`
- Modify: `app/models.py` (new `WeeklyGoal`)
- Test: `tests/test_goals.py`

**Interfaces:**
- Produces:
  - `class WeeklyGoal(Base)`: `id`, `user_id` FK, `week_start: date`, `target: int`; unique `(user_id, week_start)`.
  - `week_start(d: date) -> date` (Monday of d).
  - `local_date(dt_utc: datetime, tz: str) -> date`.
  - `target_for(db, user, week: date) -> int | None` (latest row with `week_start <= week`).
  - `set_goal(db, user, target: int, today: date) -> WeeklyGoal` (no rows → this Monday; else upsert next Monday). Raises `ValueError` outside 1–200.
  - `pending_goal(db, user, today) -> int | None` (a row for next Monday, if any).
  - `count_for_week(db, user, week: date, tz: str) -> int`.
  - `streak(db, user, today: date, tz: str) -> int`.
  - `@dataclass GoalStatus(target: int | None, done: int, met: bool, streak: int, pending: int | None)` and `goal_status(db, user, today, tz) -> GoalStatus`.

- [ ] **Step 1: Write failing tests** in `tests/test_goals.py`, using `junior_paper` + `child` and helpers that create submitted attempts with chosen `submitted_at` (UTC) and answers via `start_attempt`/`save_answer`/`submit` then backdate:
  - `test_first_goal_applies_now` — `set_goal(…, 15, today=Wed)` → `target_for(this Monday) == 15`.
  - `test_later_change_applies_next_week` — then `set_goal(…, 20, Wed)` → this week 15, next Monday 20, `pending_goal == 20`; calling again with 25 replaces (still one row for next Monday).
  - `test_goal_range` — `set_goal` with 0 and 201 raises `ValueError`.
  - `test_counts_distinct_answered_problems` — 3 answered (2 right, 1 wrong) + 1 blank in one attempt, and the same 3 again in a retake that week → 3.
  - `test_followups_count` — a `FollowupResponse` created this week adds 1.
  - `test_unsubmitted_and_blank_do_not_count` — unsubmitted attempt with answers → 0.
  - `test_week_boundary_uses_local_time` — submitted `2026-11-22 15:30` UTC counts for week of 2026-11-16; `2026-11-22 16:30` UTC counts for 2026-11-23.
  - `test_streak` — target 2; met in weeks −3, −2, −1, missed −4 → streak 3 on a day this week before meeting it; 4 after meeting this week; a missed week −1 → 0 (or 1 if this week met).
- [ ] **Step 2: Run** `.venv/bin/pytest -q tests/test_goals.py` — Expected: collection error (`app.goals` missing).
- [ ] **Step 3: Implement** `WeeklyGoal` and `app/goals.py`. Counting: query submitted attempts whose local submit date falls in the week; collect `paper_question.problem_id` where `first_answer` is non-blank; union follow-up `problem_id`s by local `created_at`. Weeks with no target are not met.
- [ ] **Step 4: Run** the file, then full suite — Expected: all pass.
- [ ] **Step 5: Commit** `feat: weekly goals (model, counting, streak)`.

### Task 2: Goal on the home page, Me page and parent Progress

**Files:**
- Create: `app/routes/goals.py`, `app/templates/_goal_card.html`
- Modify: `app/main.py` (router), `app/routes/practice.py` (pass `goal`), `app/templates/practice_home.html`, `app/templates/account.html`, `app/routes/progress.py` + `app/templates/progress.html`, `app/static/app.css`
- Test: `tests/test_goal_ui.py`

**Interfaces:**
- Consumes: Task 1 `goal_status`, `set_goal`.
- Produces: `POST /goal` (form `target`, child only, 403 for parents) → redirects to `next` form field if it starts with `/`, else `/practice`; on bad value re-renders practice home with status 400 and a friendly error. `_goal_card.html` takes `goal: GoalStatus` and renders an SVG ring (`class="goal-ring"`) with text `"{done} of {target} this week"`, streak `"{n} weeks in a row 🔥"` when `streak >= 2`, and pending `"From next week: {pending}"`.

- [ ] **Step 1: Failing tests:**
  - `test_home_prompts_for_goal_without_blocking` — no goal → `name="target"` form on `/practice` *and* paper list still present.
  - `test_set_goal_from_home` — POST `target=15` → home shows `"0 of 15 this week"`.
  - `test_bad_goal_rejected` — `"0"`, `"201"`, `"abc"` → 400 with "1 to 200".
  - `test_parent_cannot_set_goal` — 403.
  - `test_me_page_shows_goal_and_pending` — after a change: `"From next week: 20"`.
  - `test_parent_progress_shows_goal` — parent `/progress?user=<child>` shows `"of 15 this week"`.
- [ ] **Step 2: Run** — Expected: FAIL (404 / missing text).
- [ ] **Step 3: Implement** routes, card (include on home above the papers; on Me page as its own `.card` section with the form), parent read-only summary on Progress. Ring is pure SVG (stroke-dasharray), tokens only.
- [ ] **Step 4: Run** file + full suite — pass.
- [ ] **Step 5: Commit** `feat: set and see the weekly goal`.

### Task 3: Pet growth and bonus eggs

**Files:**
- Create: `app/pets/__init__.py`, `app/pets/growth.py`
- Modify: `app/models.py` (`PetBonus`; `User.buddy_tag: str | None`, `User.sound_on: bool | None`)
- Test: `tests/test_pet_growth.py`

**Interfaces:**
- Consumes: `app.progress._submitted_responses`, `_tags`; Task 1 `goal_status`, `week_start`.
- Produces:
  - `class PetBonus(Base)`: `id`, `user_id`, `tag`, `amount: int`, `week_start: date`, `created_at`; unique `(user_id, week_start)`.
  - `HATCH, GROWN = 2, 15`; `stage(points: int) -> str` in `{"egg","baby","grown"}`.
  - `question_weight(pq: PaperQuestion) -> int`.
  - `@dataclass PetState(tag: str, points: int, stage: str, last_grew: datetime | None)`.
  - `growth(db, user, as_of: datetime | None = None) -> dict[str, PetState]` (all 30 tags present; events after `as_of` excluded; retries dated by their attempt's `submitted_at`).
  - `shown_tags(db, user) -> list[str]` (tags on problems of published papers, plus any with points > 0, in `TECHNIQUES` order).
  - `settle_week(db, user, today: date, tz: str) -> PetBonus | None` — if this week's goal is met and no bonus exists for the week, create one (random choice seeded by `f"{user.id}:{week}"`); returns the new bonus or None.
  - `buddy(db, user, states) -> str | None` — `user.buddy_tag` if hatched, else most recent `last_grew` among hatched, else None.

- [ ] **Step 1: Failing tests:**
  - `test_weight_by_point_rank` — Junior parts A1/B2/C3/D4 → weights 1, 2, 3, 3; a single-value paper → 2.
  - `test_first_correct_grows_by_weight` / `test_wrong_does_not_grow`.
  - `test_retry_correct_grows_one` and `test_later_correct_after_miss_grows_one_once` (redo + another retake → still +1 total).
  - `test_retake_after_first_correct_adds_nothing`.
  - `test_followup_correct_grows_one`.
  - `test_multi_tag_and_unknown_tags` — problem tags `["parity","pigeonhole","made-up"]` → both grow, no `"made-up"` key; untagged problem: no growth but `count_for_week` counts it.
  - `test_blank_and_unsubmitted_do_not_grow`.
  - `test_as_of_excludes_later_events`.
  - `test_stages` — 0,1 egg; 2,14 baby; 15 grown.
  - `test_bonus_awarded_once_per_met_week` — goal 2, meet it → `settle_week` returns bonus (+2 to an egg in `shown_tags`); call again → None; growth reflects +2.
  - `test_bonus_when_no_eggs_left_goes_to_closest_to_grown`.
  - `test_buddy_choice_and_default`.
- [ ] **Step 2: Run** — Expected: collection error.
- [ ] **Step 3: Implement.** Growth algorithm (the part tests don't fully determine):

```python
# per problem, in time order of attempt.submitted_at
first = earliest response with correct_first not None
if first.correct_first: add weight(first.pq) to each tag
else:
    recovered = first.correct_retry or any later response for the problem with correct_first True
    if recovered: add 1 to each tag (timestamp = when it happened)
# follow-ups: first correct FollowupResponse per problem_id → +1 per tag
# bonuses: + amount to tag, at created_at
```

- [ ] **Step 4: Run** file + full suite — pass.
- [ ] **Step 5: Commit** `feat: technique pet growth and bonus eggs`.

### Task 4: Creatures — catalogue, SVG rig, animation, parent preview

**Files:**
- Create: `app/pets/creatures.py`, `app/templates/pets/_pet.html` (macro), `app/templates/pets/_bodies.html` (8 bodies × 3 stages), `app/templates/pets/_features.html`, `app/templates/pets/preview.html`, `app/static/pets.css`, `app/static/pets.js`
- Modify: `app/templates/base.html` (load `pets.css`/`pets.js`), `app/routes/` new `pets.py` with `GET /parent/pets/preview` (parent only), `app/main.py`
- Test: `tests/test_creatures.py`

**Interfaces:**
- Produces:
  - `BODY_TYPES = ("blob","boxy","bird","dragonling","jelly","bean","star","fuzzball")`.
  - `@dataclass(frozen=True) Creature(tag, name, body, main, light, dark, feature, badge, catchphrase)`; `CREATURES: dict[str, Creature]`.
  - Jinja macro `pet(creature, stage, size=160, interactive=True)` in `pets/_pet.html` → `<div class="pet-slot" data-tag=… data-stage=… data-say=…>` containing one `<svg>` whose parts carry the rig classes: `breathe`, `pupils`, `lid`, `mouth-smile`, `mouth-o`, `jump`, plus `tail`/`wings` when drawn, `feature`, `badge`; colours via CSS custom properties `--pet-main/--pet-light/--pet-dark` on the slot. Gradient ids must be unique per instance (prefix with a per-call counter).
  - `pets.js` exports on `window.BBPets`: eye-tracking (pointermove), tickle on click/tap (bubble with `data-say`), `play(el, "hatch"|"happy"|"grow")`.

- [ ] **Step 1: Failing tests:**
  - `test_one_creature_per_technique` — keys == every tag in `TECHNIQUES`.
  - `test_names_unique_and_every_body_used_at_least_twice`.
  - `test_badge_short` — `len(badge) <= 4`; catchphrase ≤ 24 chars.
  - `test_evenix_is_parity` — `CREATURES["parity"].name == "Evenix"` and badge `"2k"`.
  - `test_every_creature_renders_each_stage_with_rig` — parent preview page HTML contains 90 `pet-slot`s and, for baby/grown, the rig classes `pupils`, `lid`, `mouth-smile`; no duplicate `id="…"` attributes.
  - `test_preview_parent_only` — child gets 403.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Base the drawings and CSS on the approved mockup `.superpowers/brainstorm/28527-1795077297/content/pet-animation-v2.html` (breathe, blink, wag, float, perk on hover, giggle, hatch, happy jump with sparkles, grow glow; reduced-motion off). Each creature's feature must express its technique (e.g. Evenix: paired horns/wings, "2k"; pigeonhole: peeking from boxes; working-backwards: rewind-arrow tail). Hover effects also trigger on `:focus-visible`; slots are `tabindex="0"` with `role="button"` and an `aria-label` of the name and stage.
- [ ] **Step 4: Run** file + full suite — pass. Then screenshot the preview page for a visual check: run the app locally (`.venv/bin/uvicorn app.main:create_app --factory`) with a parent user, and capture `/parent/pets/preview` with headless Chrome (`--headless --screenshot --window-size=1280,4000`); inspect the image, fix anything ugly, unreadable in dark mode, or indistinct.
- [ ] **Step 5: Commit** `feat: 30 technique creatures on a shared animated rig`.

### Task 5: My pets page, buddy and the home buddy

**Files:**
- Modify: `app/routes/pets.py` (`GET /pets`, `POST /pets/buddy`), `app/templates/pets/index.html` (create), `app/templates/base.html` (child tab `🐾 Pets` → `/pets`, using the existing `tab()` macro), `app/templates/practice_home.html` + `app/routes/practice.py` (buddy beside goal card)
- Test: `tests/test_pets_page.py`

**Interfaces:**
- Consumes: Task 3 `growth`, `shown_tags`, `buddy`, `stage`; Task 4 `CREATURES`, `pet` macro.
- Produces: `/pets` (child; parents redirected to `/parent/pets/preview`): grid of shown pets with name, technique name, stage, progress text (`"6 / 15 to grow up"`, `"1 / 2 to hatch"`, `"Grown-up"`), a details panel per pet (technique, how it grows, link `/practice?technique=<tag>` only if a published paper has it — otherwise no link), and `"{n} more to discover"` mystery eggs. `POST /pets/buddy` (`tag`; must be hatched, else 400).

- [ ] **Step 1: Failing tests:**
  - `test_pets_page_for_brand_new_child` — no answers → 200, all shown pets are eggs, mystery count = 30 − len(shown), home still renders.
  - `test_pets_grow_from_answers` — answer a parity question right → that pet shows progress.
  - `test_pick_buddy` / `test_cannot_pick_unhatched_buddy` (400).
  - `test_buddy_on_home` — home contains the buddy's `pet-slot`; no buddy → none, no error.
  - `test_pets_tab_for_child_only` — child nav has `href="/pets"`, parent nav doesn't.
  - `test_no_pets_on_question_pages` — attempt page has no `pet-slot`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** If `/practice?technique=` filtering doesn't exist, drop the link rather than add filtering (YAGNI); keep the test accordingly.
- [ ] **Step 4: Run** file + full suite — pass.
- [ ] **Step 5: Commit** `feat: my pets page and buddy`.

### Task 6: Results celebrations

**Files:**
- Modify: `app/routes/practice.py` (`attempt_results`), `app/templates/results.html`, `app/static/pets.js`
- Create: `app/pets/celebrate.py`
- Test: `tests/test_celebrations.py`

**Interfaces:**
- Consumes: Task 3 `growth(as_of=…)`, `settle_week`; Task 1 `goal_status`, `count_for_week`.
- Produces: `celebration(db, user, attempt, today, tz) -> Celebration` with `grew: list[(tag, gained, before_stage, after_stage)]` (only owner's attempts; computed as growth at `submitted_at` minus growth just before it), `goal_met_now: bool` (count before this attempt < target ≤ count after, within the attempt's week), `bonus: PetBonus | None` (from `settle_week`, only when the attempt is in the current week), `beat_best: bool` (score > every earlier submitted score on the same paper, and at least one earlier exists).

- [ ] **Step 1: Failing tests:**
  - `test_results_show_pets_that_grew` — `"+N"` and the creature's name for each grown tag; hatch → `data-play="hatch"`; reaching 15 → `data-play="grow"`.
  - `test_goal_met_celebration_and_bonus_egg` — the attempt that crosses the target shows the goal celebration and the bonus pet.
  - `test_reopening_results_awards_once` — GET results twice (and once as parent) → exactly one `PetBonus`; second view still lists the same growth (it's per-attempt), and doesn't show a second bonus.
  - `test_beat_best_confetti` — second try with a higher score → `data-confetti`; first try or equal score → not (unless the existing 3-star rule applies).
  - `test_parent_view_has_no_celebration_sounds` — parent viewing child results: no `data-sound` triggers.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**; pets appear below the scorecard, play their animation on load in sequence (via `BBPets.play`), each with a `data-sound` (`ding`/`crack`/`fanfare`, `jingle` for goal).
- [ ] **Step 4: Run** file + full suite — pass.
- [ ] **Step 5: Commit** `feat: celebrate pet growth, goals and personal bests on results`.

### Task 7: Sound

**Files:**
- Create: `app/static/sound.js`
- Modify: `app/templates/base.html` (load; `<body data-sound="on|off">` for children), `app/routes/pets.py` (`POST /sound`), `app/templates/practice_home.html` + `results.html` (🔊/🔇 toggle button), `app/static/pets.js` (tickle → `squeak`)
- Test: `tests/test_sound.py`

**Interfaces:**
- Produces: `window.BBSound.play(name)` for `ding`, `crack`, `fanfare`, `jingle`, `squeak` (Web Audio oscillators/envelopes, ≤ 1.5 s each, gentle volume); no-op when `body[data-sound="off"]`; if the AudioContext is suspended, resume on the first `pointerdown`/`keydown` and play the most recent queued sound then. Elements with `data-sound` play when their animation starts. `POST /sound` (`on` = `"1"`/`"0"`, child only) stores `User.sound_on`; default on.

- [ ] **Step 1: Failing tests:**
  - `test_sound_on_by_default` — child page has `data-sound="on"`.
  - `test_toggle_sound` — POST `on=0` → `data-sound="off"` on next page; persists across a new login session.
  - `test_toggle_on_home_and_results` — both pages have the toggle form.
  - `test_sound_js_defines_all_sounds` — `sound.js` text contains each of the five names.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** file + full suite — pass. Manual check in a browser: tickle squeaks, results play, mute silences.
- [ ] **Step 5: Commit** `feat: sounds with a mute toggle`.

### Task 8: Whole-feature check

- [ ] Run the full suite: `.venv/bin/pytest -q` → all pass.
- [ ] Run locally with a child and parent account; walk: set goal → do a part of a paper → results celebrate → pets page → buddy on home → mute. Screenshot home, pets, results (light and dark) with headless Chrome and inspect.
- [ ] Do **not** push: deploying is the user's call.
