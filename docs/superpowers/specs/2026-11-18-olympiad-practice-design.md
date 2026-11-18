# Olympiad Practice Tool — Design

Date: 2026-11-18
Status: draft, awaiting approval

## 1. Intent

A 12-year-old (just finished Primary, moving to Junior) practises past maths olympiad
papers: IMONST 1, SASMO, Kangaroo, ASMO. Today the parent marks his paper by hand, and for
each wrong answer they work it out together or ask an LLM. Roughly half his misses are
**careless** (he knew the method but slipped); the rest are **technique gaps** (he didn't
know the method).

The tool takes over marking, the first-pass explanation, and the careless-vs-technique
diagnosis, and keeps a running record of which techniques he keeps missing. The parent
still sits with him but starts from a diagnosis instead of a blank page.

**Success looks like:** after a paper, each miss is labelled careless or technique, with
a specific explanation; over weeks, the progress page tells the parent what to practise
next.

## 2. Goals / non-goals / anti-goals

**Goals**
- Import past-paper PDFs + answer keys with little manual effort.
- He does a paper on screen (laptop or phone), answers marked instantly.
- Separate careless slips from technique gaps for each miss.
- Kid-level explanations that point at his actual mistake.
- Suggest follow-up questions that use the same technique.
- Progress view the parent can open from a phone.
- Deployed on the public internet, behind a login.

**Non-goals (this version)**
- Talk-it-through voice explanations, stylus input (planned experiments for later).
- Multiple children / classroom use (the data model should not block it).
- Malay-language papers (import English only).
- Generating new questions with AI.

**Anti-goals: would be a failure even if it "works"**
- **Confidently wrong explanations.** Any explanation that doesn't reach the official
  answer must not be shown as truth.
- **Retyped questions with broken maths or missing diagrams.** He must always see the
  original rendering.
- **Making him type his working.** Working stays on paper.
- **Exposing answer keys to the child account** before he has submitted.
- **Making the papers publicly accessible.** They are copyrighted; the site is private.

## 3. What the sample paper taught us (IMONST 1, 2020)

Source: `imonst-2020-problems-w-answers.pdf` (33 pages).
- One PDF = 6 papers: Primary / Junior / Senior × Malay / English, plus answer keys at
  the back (one page per category).
- 20 questions per paper in Parts A–D worth 1/2/3/4 points.
- The same question appears in several categories (e.g. Primary Q6 = Junior Q1); about
  15 of the 20 Junior questions also appear in Primary or Senior.
- The PDF's **text layer is unreliable for maths**: △ → "4", 10⁸ → "108", 5⁵ → "55",
  fractions split across lines. But the "Problem N." anchors and their positions *are*
  reliable.
- IMONST answers are non-negative integers (up to 11 digits). Kangaroo/SASMO are multiple
  choice (A–E). ASMO has a mix.
- There are no worked solutions, only final answers.

## 4. Approaches considered

| | Approach | Trade-offs |
|---|---|---|
| **A (chosen)** | Python (FastAPI) server-rendered app, SQLite + files on one small host (Fly.io or Railway, ~USD 5/mo) | Best PDF tooling (PyMuPDF); one place to run and fix; plain UI. |
| B | Next.js on Vercel + Supabase | Free tier, more polished UI; but weaker PDF cropping in JS and two services to manage. |
| — | Native mobile app | Rejected: a responsive web page covers laptop + phone. |

For showing his working, a **photo of paper working** was chosen. Voice explanation
(tends to describe intent, not what was written) and stylus input (changes how he works)
are deferred to later experiments.

## 5. Users and access

- **Parent** account: import papers, review/fix imports, see everything, override
  diagnoses.
- **Child** account: pick and do papers, see feedback on his own attempts. Never sees
  answer keys for unsubmitted questions.
- Username + password, cookie session. Single household; accounts created by a CLI/seed
  command (no sign-up page).
- Phone photo upload uses a **short-lived, single-use link** (QR code) so his phone needs
  no login. *(Builder's call on expiry; ~15 min suggested.)*

## 6. Core flows

### 6.1 Importing a paper (parent)

1. Upload a PDF. Metadata form: contest (IMONST/SASMO/Kangaroo/ASMO/other), year,
   duration in minutes (optional).
2. Server renders pages to images (PyMuPDF, ~150 dpi).
3. Claude (vision) looks at the page images and returns the structure: sections
   (category, language, page range), parts with point values, the answer-key pages, and
   the answers per category/question.
4. **Cropping:** for PDFs with a text layer, find "Problem N." / "Question N." anchors via
   PyMuPDF word positions and crop from one anchor to the next (or to the bottom of the
   page or the next part heading). For scanned PDFs (no text layer), fall back to
   Claude-proposed bounding boxes. Questions that span a page break are stored as
   multiple images.
5. For each question, Claude, given the crop image, returns:
   - a clean transcription (Markdown + LaTeX), used only for AI prompts and search,
     never shown in place of the image;
   - answer type: integer / fraction / multiple choice (A–E) / text;
   - 1–3 technique tags from a fixed list (see §8).
6. **Duplicate detection:** questions within the same contest-year with the same answer
   and very similar transcriptions are linked as one "problem" appearing in several
   papers.
7. **Review screen:** grid of crops with detected number, points, answer, type, and tags.
   The parent can fix the answer, nudge the crop edges, merge/unlink duplicates, and
   then publish the paper. Only English sections the parent ticks are imported.

### 6.2 Doing a paper (child)

1. Picks a paper (contest → year → category; Junior pre-selected).
2. **Mode:** *Contest* (timer, no feedback until submit), or *Practice* (untimed, no
   feedback until submit). In both he answers everything, then submits, like the real
   contest.
   He can also do **a subset** (pick question numbers or a part, e.g. "Part C only")
   and can **save and resume** later. Unanswered questions don't count as misses.
3. Screen: one question at a time (crop image, full width) with an answer box suited to
   the answer type, and a question navigator showing answered/blank. Works on phone
   width.
4. **On submit:** marks every question and shows a score weighted by points.
5. **Retry round:** each wrong question gets one silent retry ("not quite, have another
   look"), with no hints. A correct retry is recorded as **careless (self-corrected)**.
6. **Still wrong → photo:** for each remaining miss, he photographs his working. On the
   laptop, a QR code opens the phone camera via the one-time link; the laptop's own
   camera/file picker also works. He can skip the photo ("I didn't really write
   anything").
7. Diagnosis runs per miss (§7) and results appear as they finish.

### 6.3 Feedback for a miss

- **Label:** Careless slip / Technique gap / Not sure.
- **Careless:** the specific line where it went wrong ("you wrote 7×8 = 54 in the second
  line"), then a "show full solution" option.
- **Technique:** a hint first ("try thinking about the remainders when you divide by
  9"), then a "show full solution" option, then the technique, named and explained in
  kid language, with **1–2 follow-up questions** from the bank sharing that technique tag.
  These should be ones he hasn't done recently and not the same problem as the miss.
  Follow-ups are answered inline and marked immediately.
- **Not sure / unverified:** "This one's tricky. Go through it with <parent's display name>." The parent sees
  these flagged.

### 6.4 Progress (parent, also visible to child)

- Papers taken: date, paper, score, time used.
- Misses split: careless (self-corrected), careless (diagnosed), technique, unsure, over
  time.
- Technique table: attempts / misses per tag, highlighting tags missed ≥ 2 times
  recently.
- Recent misses list linking to each feedback page. The parent can **override** a label;
  overrides feed the stats.

## 7. AI diagnosis and the "never confidently wrong" rule

Per miss, after the retry:

1. **Reference solution (cached per problem):** Claude solves the problem from the crop
   image, step by step. If its final answer ≠ official answer, generate again once; if it
   still disagrees, mark the problem **unverified**. No full solution is shown, and the
   miss goes to "go through it with your parent". A verified solution is stored and reused for every
   later miss on that problem.
2. **Diagnosis:** input = question crop, official answer, verified solution, his first
   and retry answers, his photo (if any). Output (structured JSON): label (careless /
   technique / unsure), the step where it went wrong (quoted from his working where
   possible), technique tag, hint, kid-friendly explanation.
3. Without a photo, the label comes from the answers alone and is usually "unsure"
   unless the wrong answer is a recognisable slip (e.g. off by one, sign error); the
   builder can decide how hard to push that.
4. Prompts set the voice: a friendly coach talking to a 12-year-old, short sentences,
   no jargon without explanation.

Models: use current Claude models (vision-capable). Builder picks the model per task
(stronger model for solving/diagnosing, cheaper for import tagging), guided by cost; the
target is a few cents per paper. The API key is in an environment variable.

## 8. Technique tags

A fixed, seeded list of ~30 tags the parent can extend, e.g.: arithmetic & order of
operations, fractions/ratios, percentages, rates & work, ages/word problems,
working backwards, pattern finding, sequences & series, divisibility & remainders,
primes & factors, last digit / modular arithmetic, digit sums, place value, parity,
pigeonhole, counting (casework), counting (combinations), complementary counting,
probability, angle chasing, areas & shading, Pythagoras, similar triangles, circles,
3D/nets/cubes, logic & truth-tellers, clocks & calendars, inequalities/estimation,
algebraic manipulation, optimisation (max/min). *(Final list is the builder's call.)*

## 9. Data model (sketch)

- `user` (id, name, role parent|child, password hash)
- `source_pdf` (id, filename, contest, year, uploaded_at)
- `paper` (id, source_pdf, category, language, duration_min, published)
- `problem` (id, transcription, answer, answer_type, verified_solution, verified flag, tags)
  — the deduplicated unit
- `paper_question` (paper, number, part, points, problem, crop image path(s))
- `attempt` (id, user, paper, mode, started_at, submitted_at, score)
- `response` (attempt, paper_question, first_answer, retry_answer, correct_first,
  correct_retry, photo path, diagnosis JSON, label, parent_override)
- `followup_response` (user, problem, answer, correct, from_response)
- `technique` (tag, name, kid_description)

## 10. Constraints

- Public URL, private content: everything behind login; uploaded PDFs, crops, and photos
  are never served without auth (except the one-time photo upload link, which only
  accepts an upload).
- Works on a laptop and a phone browser (responsive; camera via
  `<input type="file" accept="image/*" capture>`).
- Running cost target: hosting ~USD 5/month + AI a few cents per paper.
- Persistent storage for SQLite + files (Fly volume or equivalent) with a simple backup
  (builder's call: e.g. nightly copy to object storage, or Litestream).
- The existing Python venv in the repo folder can be replaced by a proper project setup.

## 11. Left to the builder

- Exact frameworks around FastAPI (templating, htmx or plain forms), CSS approach.
- Host choice between Fly.io / Railway / similar; backup mechanism.
- Model choice per task; prompt wording; JSON schemas.
- Answer normalisation (e.g. "1/2" = "0.5"? leading zeros, spaces in big numbers). Default:
  accept equivalent forms for fractions; strip spaces/commas for integers.
- Duplicate-detection thresholds.
- How long one-time upload links last.
- Image resolution / storage format.

## 12. Later iterations (noted, not designed)

- Voice "talk me through it" as an alternative to the photo.
- iPad/stylus working capture.
- Spaced repetition of missed problems.
- More than one child.
