# Brainy Broski: pets, weekly goals and celebrations — design

Status: draft for approval · 2026-11-19

## Why

Brainy Broski is an olympiad practice app (IMONST, SASMO, Kangaroo, ASMO) built for one 12-year-old. He sees it
for the first time on 2026-11-20. Dad wants him to *want* to open it and keep coming back — the pull Duolingo has —
without turning olympiad training into a speed or volume game. Olympiad learning happens while stuck on a hard
problem, so rewards must make hard problems exciting, never something to dodge.

Success: he returns on his own across weeks, chases the techniques he hasn't grown yet, and is pleased rather
than guilted by the app.

## Goals

- He sets his own weekly goal (problems per week) and sees progress toward it.
- A collection of original, animated "technique pets" that grow as he masters each technique.
- Delight at the right moments: pets react to him, results celebrate growth, sounds give the "ding".

## Non-goals (for now)

- Separate mini-games, pet adventures (possible later: grown pets go on maths-puzzle adventures).
- Stars, coins, shops or a second currency.
- Leaderboards or competing with others.
- Parent-set or parent-approved goals (Dad decided: the child sets the goal, for now).

## Anti-goals (would make this a failure even if it works)

- Rewarding speed, guessing, or sticking to easy papers.
- Guilt mechanics: pets that get sad, hungry or die; scolding for missed weeks.
- Anything that interrupts him *while solving* a question.

## Decided in conversation

- **Weekly goal, set by the child.** Number of problems per week.
- **Technique pets**, one per technique (`app/techniques.py`, 30 tags), growing egg → baby → grown-up.
- **Art style: our own drawn creatures** (not emoji, not mythical-beast theme), cute, as in the approved mockup
  (`.superpowers/brainstorm/*/content/pet-animation-v2.html`).
- **Animated**: always breathe and blink; eyes follow the pointer; perk up on hover; giggle with a speech bubble on
  click/tap. Big moments: hatching, a right-answer jump with sparkles, growing up with a glow.
- **Placement**: a "My pets" page with the collection; his current buddy beside the goal ring on the practice home;
  pets that grew pop up on the results screen. Nothing during questions.
- **No stars, no separate games** (the pets are the playful layer).
- **Sound on**, with a mute toggle.
- **Approach: ~8 shared body types, mixed and matched** (see Approaches).

## Approaches considered (for the creature art)

1. 30 fully unique creatures drawn from scratch — most magical, ~90 drawings, uneven quality risk, animation
   wiring per creature.
2. **~8 body types mixed and matched (chosen)** — each technique = body type + palette + technique-themed feature
   and badge. All 30 look distinct, one shared animation rig, about a third of the drawing.
3. ~8 family pets (groups of techniques) — least work, but a smaller collection and it stops showing which
   technique is weak.

Chosen because it keeps "one pet per technique" (the collection doubles as a map of his maths) at a quality and
effort we can sustain, and every pet gets the full set of reactions for free.

## The design

### Weekly goal

- Set on the practice home (first visit prompts him, but never blocks practice) and on his "Me" page: a whole
  number, 1–200.
- The first goal applies immediately, and counts the whole current week. Later changes apply from the next week, so the target can't be lowered at the
  last minute. Weeks run Monday–Sunday in the app's timezone (`settings.timezone`, Asia/Kuala_Lumpur).
- **What counts:** a question he gave a real (non-blank) answer to in a submitted attempt, and follow-up problems he
  answered, during that week. The same problem counts once per week. Right or wrong both count: the goal rewards
  effort; pets reward mastery.
- Home shows a ring: "9 of 15 this week".
- **Meeting the goal** gives a **bonus egg** (once per week) and extends the **weekly streak** ("4 weeks in a row
  🔥"). The streak counts consecutive met weeks up to last week, plus this week once met. A missed week resets the
  streak quietly, with no scolding.

### Technique pets

- One pet per technique tag. Shown pets are the techniques that appear in at least one published paper's problems;
  the rest appear as a count of mystery eggs ("7 more to discover").
- **Growth** comes from his existing answers (no separate ledger), using the same "first answer to each problem"
  rule as `technique_table` in `app/progress.py`, so pets and the Progress page always agree:
  - correct the first time: growth = the question's weight (below), for each of its technique tags;
  - correct on retry, or a correct follow-up problem: 1;
  - a problem he missed at first and later gets right (in "Redo my misses" or a retake): 1, once per problem —
    so going back to misses is rewarded (builder's call, see below);
  - wrong: 0 (never negative).
  - **Weight** makes hard problems worth more: rank the distinct point values within the paper; lowest = 1, next = 2,
    highest and above = 3. A paper with a single point value gives 2.
- **Bonus eggs** (from weekly goals) add growth that is stored: 2 growth to a pet still at 0, chosen at random from
  shown pets that are still eggs; if none are eggs, +2 to the pet closest to growing up.
- **Stages:** egg (0–1), baby (2–14), grown-up (15+). (Matches the mockup: "2 to hatch", "6/15".)
- **Buddy:** he can pick any hatched pet as his buddy; default is the pet that grew most recently.

### Where the pets show up

- **Practice home:** goal ring, buddy beside it (interactive), streak.
- **My pets page** (`/pets`, linked from the top bar for children): grid of the collection, each pet animated and
  interactive, its name, technique name, stage and progress bar. Tapping a pet shows its technique, how it grows,
  and a "practise this" link to papers with that technique, if any.
- **Results screen:** after the score, the pets that grew in this attempt pop up with "+N" and play the jump; a pet
  that hatched plays the hatch sequence; a pet that grew up plays the glow. If this attempt met the weekly goal: a
  goal celebration plus the bonus egg. If he beat his best score on this paper: confetti.
- Nothing appears on question pages.
- **Parent's Progress page:** shows his goal, this week's count and the streak (read-only).

### Creatures (art and animation)

- **8 body types** (for example: round blob, boxy, bird, dragonling, jelly, bean, star, fuzzball). Each has three stage
  drawings: egg (patterned shell with a hint of the badge), baby (small, shell bits on the head), grown-up (bigger,
  with the full feature: wings, horns or tail).
- **Each technique's creature** = body type + 3-colour palette + a technique feature + badge + name + catchphrase
  for the tickle bubble. Examples: Evenix (parity: everything comes in pairs, "2k" badge, "Even steven!");
  a pigeon in little boxes (pigeonhole); a rewind-arrow tail (working backwards).
- **One shared rig**, so every pet supports every reaction: named parts for body, belly, eyes, pupils, eyelids,
  mouth (smile/open), feet, optional tail and wings, a feature slot and a badge slot.
- Drawn as SVG, animated with CSS; small JS only for eye-tracking and tickles. No animation libraries.
- Honour `prefers-reduced-motion` (no movement, pets still visible).

### Sound

- Short sounds synthesised in the browser (Web Audio): a ding when a pet grows, an egg crack, a grow-up fanfare,
  a goal-met jingle, a squeak on tickle. No audio files.
- 🔊/🔇 toggle on the practice home and results page, saved to his profile so it follows him across devices.
  Browsers may block sound until he taps; the page should then play sounds from his first tap rather than fail.

## Constraints

- Existing stack: FastAPI + Jinja2 + htmx + SQLite/SQLAlchemy; new nullable columns via `ensure_schema`, new tables
  via `create_all`. TDD; the suite must stay green. Deploys go through CI on push to main.
- Keep the app's design tokens (`app/static/app.css`: colours, `--fs-*` font sizes) and dark mode.
- Phone/tablet friendly: everything works by tap; no hover-only information.
- Child-facing text: short, friendly, encouraging.

## Left to the builder

- The exact 8 body types, the 30 creatures' names, palettes, features and catchphrases (Dad reviews them on the
  My pets page; a parent-only preview of all 30 at every stage helps him do that).
- The sounds' exact tones.
- Storage shapes (goal history, bonus eggs, buddy, mute) and how "grew in this attempt" is computed (e.g. growth
  with and without the attempt's responses).
- Exact layouts, within the placement above.

## Calls made while writing this up (check these)

- Getting a missed problem right later (redo or retake) gives 1 growth, once per problem.
- Hard-problem weight is the rank of the question's points within its paper (1–3), since point scales differ by contest.
- Stage thresholds: hatch at 2 growth, grown-up at 15.
- The goal prompt never blocks practice; a first goal set mid-week counts the whole week.
- Bonus eggs go to a random pet that is still an egg (or else the one closest to growing up).
- Mute setting is stored on his profile, not just the browser.
- Parent Progress page shows his goal, this week's count and streak.
