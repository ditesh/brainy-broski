# Practice mode, Exam mode, and the pet in the burrow

## Why
The boy has started using the site. He (and his parent) want:
- **Practice** to feel like learning: check each question as he goes, see the answer when stuck, get help from his pet.
- **Exam** to feel like the real competition: a timer, no help, nothing marked until he hands the paper in.
- His pet beside him while answering, hidden in a **burrow** until he taps it, so it encourages and helps without
  distracting.

**Success:** he practises with the pet's help and comes back; exam runs feel like the real thing.
**Anti-goals:** help that hands out answers for free (he must try first); waiting minutes for help; exam mode
leaking any marking or help before hand-in; breaking pets, goals, results or progress built on the current data.

## Approaches
- **Extend today's attempts (chosen).** A paper attempt already stores a first answer, a second try and whether
  each was right, and these feed pet growth, results, redos, progress and goals. Practice checks fill those in as
  he goes; exam is today's "contest" mode. Everything downstream keeps working.
- A separate quiz system for practice: two sets of results, progress and pet rules to keep in step. Rejected.
- Marking every practice answer immediately with no "check" step: removes the choice the parent asked for
  ("optionally reveal"). Rejected.

## Decided with the parent
- Two modes: **Practice** (optional timer; check per question; give up to see the answer) and **Exam** (timer,
  marked only at hand-in, no pet, no checks).
- When a practice check is wrong: **one more try, then the answer** is revealed.
- Hints and solutions are made **only when he asks** (not ahead of time).

## Practice mode
- **Checking is optional.** Under the answer: `Check ✓` and `I give up`. He can also just move on; anything unchecked
  is marked at hand-in exactly as today.
- **Check, first time:** stores his answer as `first_answer`, marks `correct_first`. Right: "Correct! 🎉", the
  question is locked (green), and the pet pops out cheering. Wrong: "Not quite, have another go!" and the input
  is cleared for a second try.
- **Second try:** stored as `retry_answer` / `correct_retry` (the same fields the results-page retry uses today, so
  the results page offers no further retry for it). Right: "Got it on the second go! 💪". Wrong: the answer is
  revealed: "The answer is 18." Either way the question is locked.
- **I give up** (before checking): reveals the answer and locks the question. If he had typed an answer, it is
  checked first as his first answer; with no answer it counts as a miss (`gave_up`), with **no negative marking**
  (it's practice), and it is offered in "redo your misses".
- **Locked questions** can't be changed (the server refuses edits after a check; the second try is the only change
  allowed after a wrong first check).
- **Multiple choice:** tapping an option selects it (saved, highlighted, stays on the question); `Check ✓` then
  checks it. Without checks, moving on works as today.
- **Hand-in** marks any unchecked answers as today; checked ones keep their marks. Score = first answers, as today.
- **Optional timer:** off by default. When starting, "⏱️ Use a timer (N min)" (the paper's real time) can be ticked.
  In practice the timer only shows time left; at zero it says "Time's up! Keep going or hand in." It never hands
  in for him.
- **Pets grow at hand-in** as today (growth counts handed-in papers). In-page the pet only cheers.

## The burrow (practice only)
- Beside the question (to the right on wide screens; below the question on phones) is a small burrow: a mound with
  a dark hole, gently twitching grass. Tapping it (or Enter) makes his buddy jump out; tapping the pet's "Bye!"
  sends it back. No buddy yet: a friendly robot (as in the games).
- Out of the burrow, the pet offers:
  - **Hint** — instant, free: names the technique from the question's tags ("This one smells like working
    backwards! 🕵️") with its kid-friendly sentence. No tags: "Read it again slowly and draw a picture!".
  - **Another hint** — the first step of the checked solution.
  - **Show me the solution** — the checked step-by-step solution and the answer. This counts as giving up if he
    hasn't finished the question (see above) and locks it.
- **Hint 2 and the solution come from Claude, only when asked.** The first time anyone asks on a question, the
  pet does a thinking animation ("Hmm, let me think… 🤔") while Claude writes and checks a solution against the
  official answer (the existing reference-solution step). It is saved on the problem, so later asks — by him or
  on a redo — are instant. If Claude can't produce a solution that matches the official answer: the pet says so
  and offers the answer only. If Claude is unreachable: "My brain's foggy — try again in a bit."
- **Record:** each answer records `hints_used` (0–2) and `solution_seen`. The results page marks "used a hint" /
  "saw the solution" per question, so the parent sees where he needed help. Hints don't affect pet growth;
  seeing the solution before getting it right means a miss (as giving up).
- The pet reacts: cheers on a right check, an encouraging line on a wrong one ("So close!"), tickles as on other
  pages.

## Exam mode
- Today's "contest" mode, renamed **Exam** everywhere he sees it ("⏱️ Exam (90 min, like the real thing)").
  Stored value stays `contest` (no data change).
- Timer counts down and hands in at zero (as today). No checks, no give-up, no burrow. Marked only at hand-in.
- Papers with no known duration offer Practice only (as today).
- Multiple choice: tapping an option saves it and moves to the next question (as now).

## Data changes (all nullable / additive)
- `Attempt.timer_on` (practice timer chosen).
- `Response.checked_at`, `Response.gave_up`, `Response.hints_used`, `Response.solution_seen`.
- Solutions reuse `Problem.reference_solution` / `verified`; "first step" = its first numbered step.

## How practice checks fit what comes after hand-in (my calls, open to the parent)
- **Scoring is the same in both modes**, negative marking included, so practice and exam scores on a paper compare
  like for like (stars, best score, "beat your best"). The one exception: a blank give-up never loses points
  (blanks never do).
- **An in-page second try is a retry**, with the same effects as the results-page retry today: right on the second
  go is labelled "careless, self-corrected"; wrong twice goes through the usual after-hand-in help (Claude's
  diagnosis, photo of working, follow-up problem).
- **Give-ups and saw-the-solution misses** are stored as misses (`correct_first = False`, so they're in "redo your
  misses" and count as misses in progress), but there's nothing to diagnose: they skip Claude's diagnosis and the
  photo request, and show as "Gave up" / "Saw the solution" on results and progress instead of a diagnosis label.

## Left to the builder (my calls, open to the parent)
- Burrow artwork (SVG, matching the pets' style), animations, sounds (ding on right, soft squeak on wrong, the
  existing jingle when the pet pops out), reduced-motion fallbacks.
- htmx partial updates for check / give up / hints so the page doesn't jump; polling every 2 s while the pet thinks.
- Guarding against two solution jobs for the same problem at once.
