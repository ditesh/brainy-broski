# Brain-break games

**Why:** keep the boy coming back and staying on the site, without games replacing the problems.
The parent said "just go ahead", so the calls below are mine.

## Approaches considered
- **Maths games he earns by answering questions (chosen).** Practice first, play after; the games themselves use
  olympiad thinking, so the play still teaches.
- Free arcade area: most engaging, but competes with the problems, which is the anti-goal.
- Games as the practice itself (gamified questions): a much bigger change to the core flow; not now.

## Design
- **Earning:** every 3 questions answered today (same counting as the weekly goal: real answers on submitted papers
  and follow-ups, local day) earns 2 game rounds. Rounds left = earned − rounds started today. Unused rounds expire
  at midnight. Parents can always play (a preview); their rounds aren't recorded.
- **Home page:** a "🎮 Brain break" card: "Answer N more questions to unlock a brain break" or
  "You have N games to play →".
- **Games page `/games`:** both games, rounds left, and his record (Stone Duel wins, Target puzzles solved).
- **Starting a round** (POST) uses up one round and records a `GamePlay` row; the result is posted back once.
- **Stone Duel (Nim):** a pile of 15–23 stones; take 1, 2 or 3; whoever takes the last stone wins. His buddy is the
  opponent (a plain robot if no buddy yet), playing the winning move 70% of the time so he can win and start to see
  the pattern. After his second loss, the buddy drops a hint: "leave me a multiple of 4…".
- **Target (make the number):** four numbers 1–9 and a target (24); tap number, operation, number to combine two
  tiles; undo and reset. Puzzles are generated on the server and always solvable. "Show me" reveals a solution
  (counts as a loss).
- **Sound and pets:** a win plays the fanfare and the buddy does its happy jump; a loss plays a soft squeak.
- No new libraries; plain JS in `app/static/games.js`. Pet growth stays maths-only: games don't grow pets.

## Left to the builder
Layout and styling, in line with the pets pages; light and dark mode; phone width.
