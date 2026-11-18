"""Things that change once a day: the favicon's maths symbol and the kid's maths fact."""
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo


def local_today(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


# ---- favicon symbols ----

@dataclass(frozen=True)
class Symbol:
    glyph: str
    name: str
    size: int = 44     # font size; some glyphs need nudging to look centred
    y: int = 47


SYMBOLS = [
    Symbol("π", "pi"),
    Symbol("∞", "infinity", 48, 45),
    Symbol("Σ", "sigma (adding up)"),
    Symbol("√", "square root", 44, 46),
    Symbol("∫", "integral", 46, 48),
    Symbol("Δ", "delta (change)"),
    Symbol("φ", "phi (golden ratio)", 42, 46),
    Symbol("θ", "theta (angle)"),
    Symbol("≈", "approximately", 46, 45),
    Symbol("±", "plus or minus"),
    Symbol("∠", "angle"),
    Symbol("!", "factorial", 46, 48),
    Symbol("%", "percent", 40, 46),
    Symbol("e", "Euler's number", 48, 44),
]

# pi is drawn as a path so the original icon stays pixel-identical
_PI_PATH = ("M14 22 Q16 16 24 16 L50 16 L50 23 L42 23 L42 44 Q42 49 46 49 Q48 49 49 47 L52 49 Q49 55 43 55 "
            "Q35 55 35 46 L35 23 L28 23 L26 46 Q25 54 19 54 Q16 54 15 52 L17 47 Q18 48 19.5 48 Q21 48 21.4 45 "
            "L23 23 Q19 23 17.5 26 Z")


def symbol_for(day: date) -> Symbol:
    return SYMBOLS[day.toordinal() % len(SYMBOLS)]


def favicon_svg(s: Symbol) -> str:
    if s.glyph == "π":
        mark = f'<path d="{_PI_PATH}" fill="#fff"/>'
    else:
        mark = (f'<text x="31" y="{s.y}" text-anchor="middle" font-size="{s.size}" font-weight="700" '
                f'font-family="Georgia, \'Times New Roman\', \'DejaVu Serif\', serif" fill="#fff">'
                f'{escape(s.glyph)}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <title>Today's symbol: {escape(s.name)}</title>
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#3b6cf0"/><stop offset="1" stop-color="#7a3fd6"/></linearGradient></defs>
  <rect width="64" height="64" rx="14" fill="#4a5ae6"/>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  {mark}
  <path d="M52 4 L54.2 9.8 L60 12 L54.2 14.2 L52 20 L49.8 14.2 L44 12 L49.8 9.8 Z" fill="#ffd23f"/>
</svg>"""


# ---- daily maths facts ----

@dataclass(frozen=True)
class Fact:
    title: str
    body: str   # Markdown + $LaTeX$
    why: str


FACTS = [
    Fact("The 1089 trick",
         "Pick a 3-digit number whose first and last digits differ by at least 2, like 532. Reverse it and "
         "subtract the smaller from the bigger: $532 - 235 = 297$. Now add that to *its* reverse: "
         "$297 + 792 = 1089$. You **always** get 1089!",
         "The middle digit of the difference is always 9, and its first and last digits always add to 9."),
    Fact("Odd numbers make squares",
         "$1 + 3 + 5 + 7 = 16 = 4^2$. Adding up the first $n$ odd numbers always gives $n^2$.",
         "Each odd number is an L-shape that wraps around a square to make the next bigger square."),
    Fact("Young Gauss's shortcut",
         "$1 + 2 + 3 + \\dots + 100 = 5050$.",
         "Pair them up: $1 + 100$, $2 + 99$, $3 + 98$… That's 50 pairs, each adding to 101, and "
         "$50 \\times 101 = 5050$."),
    Fact("A palindrome of ones",
         "$111111111^2 = 12345678987654321$.",
         "When you multiply it out longhand, the columns count up from 1 to 9 and back down."),
    Fact("The nines test",
         "A number is divisible by 9 exactly when its digit sum is. $7362$: $7+3+6+2 = 18$, so $9$ divides "
         "$7362$.",
         "$10 = 9 + 1$, so every place value is a multiple of 9 plus 1. Only the digits are left over."),
    Fact("The elevens test",
         "Alternately add and subtract the digits. For $918082$: $9-1+8-0+8-2 = 22$, a multiple of 11, so "
         "11 divides $918082$.",
         "$10 = 11 - 1$, so the place values are alternately one more and one less than multiples of 11."),
    Fact("Triangles always make 180°",
         "The three angles of **any** triangle add up to $180^\\circ$.",
         "Tear off the three corners and line them up. They make a straight line."),
    Fact("The 3-4-5 triangle",
         "$3^2 + 4^2 = 9 + 16 = 25 = 5^2$, so a triangle with sides 3, 4 and 5 has a right angle.",
         "That's Pythagoras: in a right triangle, $a^2 + b^2 = c^2$. Builders used knotted ropes of 3, 4 and "
         "5 to make square corners."),
    Fact("0.999… is exactly 1",
         "$0.999\\ldots = 1$, not just *nearly* 1.",
         "$\\tfrac{1}{3} = 0.333\\ldots$, and multiplying by 3 gives $1 = 0.999\\ldots$"),
    Fact("Euler's polyhedron rule",
         "For any solid without holes: corners $-$ edges $+$ faces $= 2$. A cube: $8 - 12 + 6 = 2$.",
         "Try it on a pyramid: 5 corners, 8 edges, 5 faces."),
    Fact("Primes never run out",
         "There are infinitely many prime numbers.",
         "Multiply any list of primes and add 1. The new number leaves remainder 1 when divided by each of "
         "them, so some prime not on your list divides it."),
    Fact("Every number has one prime recipe",
         "$360 = 2^3 \\times 3^2 \\times 5$, and there's no other way to write it as a product of primes.",
         "This is why prime factors are so useful for counting factors: 360 has "
         "$(3+1)(2+1)(1+1) = 24$ factors."),
    Fact("Last digits go in circles",
         "The last digits of $2, 4, 8, 16, 32, 64, \\dots$ go $2, 4, 8, 6, 2, 4, 8, 6, \\dots$",
         "To find the last digit of $2^{2026}$, divide 2026 by 4. The remainder is 2, so it's the 2nd in the "
         "cycle: **4**."),
    Fact("Handshake counting",
         "If 10 people all shake hands once, there are $\\frac{10 \\times 9}{2} = 45$ handshakes.",
         "Each person shakes 9 hands, but that counts every handshake twice, so halve it."),
    Fact("The pigeonhole principle",
         "In any group of 13 people, at least two share a birth month.",
         "There are only 12 months. Put 13 pigeons in 12 holes and one hole gets two."),
    Fact("The birthday surprise",
         "With just 23 people in a room, it's more likely than not that two share a birthday.",
         "There are $\\frac{23 \\times 22}{2} = 253$ different pairs, and each pair is a chance for a match."),
    Fact("Fibonacci and the golden ratio",
         "$1, 1, 2, 3, 5, 8, 13, 21, \\dots$ Each number is the sum of the two before. Divide neighbours, "
         "$\\frac{21}{13} \\approx 1.615$, and you get closer and closer to $\\varphi \\approx 1.618$.",
         "Count the spirals on a pinecone or sunflower and you'll often find Fibonacci numbers."),
    Fact("Perfect numbers",
         "6 is *perfect*: its smaller factors add up to itself, $1 + 2 + 3 = 6$. So is "
         "$28 = 1 + 2 + 4 + 7 + 14$.",
         "The next ones are 496 and 8128. Nobody knows if there's an odd perfect number."),
    Fact("Squares can't end in 2, 3, 7 or 8",
         "Every square number ends in 0, 1, 4, 5, 6 or 9.",
         "The last digit of $n^2$ only depends on the last digit of $n$. Check all ten. "
         "So 2027 can't be a square!"),
    Fact("A kilo of bytes",
         "$2^{10} = 1024$, which is very close to $1000$.",
         "That's why $2^{20}$ is about a million and $2^{30}$ about a billion. Handy for estimating!"),
    Fact("Cubes add up to a square",
         "$1^3 + 2^3 + 3^3 + 4^3 = 100 = (1 + 2 + 3 + 4)^2$.",
         "It works for any $n$: the sum of the first $n$ cubes is the square of the sum of the first $n$ "
         "numbers."),
    Fact("Difference of two squares",
         "$a^2 - b^2 = (a - b)(a + b)$. So $99 \\times 101 = 100^2 - 1^2 = 9999$.",
         "Picture a big square with a small square cut from the corner, then slide one piece round to make a "
         "rectangle."),
    Fact("Squaring numbers ending in 5",
         "$35^2 = 1225$: take the 3, multiply by the next number ($3 \\times 4 = 12$), then write 25.",
         "$(10a + 5)^2 = 100a(a + 1) + 25$. Try $65^2$!"),
    Fact("Multiplying by 11",
         "$43 \\times 11 = 473$: write the 4, then $4 + 3 = 7$, then the 3.",
         "$43 \\times 11 = 430 + 43$. If the middle sum is 10 or more, carry the 1."),
    Fact("The magic of 142857",
         "$142857 \\times 2 = 285714$, $\\times 3 = 428571$, $\\times 4 = 571428$… the same digits keep "
         "going round in a circle! And $142857 \\times 7 = 999999$.",
         "142857 is the repeating part of $\\frac{1}{7} = 0.142857142857\\ldots$"),
    Fact("Odd squares and 8",
         "Every odd square leaves remainder 1 when divided by 8: $9, 25, 49, 81, \\dots$",
         "An odd square is $4n(n + 1) + 1$, and $n(n + 1)$ is always even."),
    Fact("Three in a row",
         "The product of any 3 consecutive whole numbers is divisible by 6. $7 \\times 8 \\times 9 = 504 = "
         "6 \\times 84$.",
         "Among any 3 in a row, one is a multiple of 3 and at least one is even."),
    Fact("π never ends",
         "$\\pi = 3.14159265\\ldots$ goes on forever without repeating. It's the circumference of any circle "
         "divided by its diameter.",
         "$\\frac{22}{7}$ is a good guess and $\\frac{355}{113}$ is correct to 6 decimal places."),
    Fact("Sliding a triangle's tip",
         "Triangles on the same base, with their tips on a line parallel to that base, all have the "
         "**same area**.",
         "Area $= \\frac{1}{2} \\times$ base $\\times$ height, and sliding the tip along the line keeps the "
         "height the same."),
    Fact("Walking round a shape",
         "The outside (exterior) angles of any convex polygon add up to $360^\\circ$.",
         "Walk all the way around it: you turn through one full turn."),
    Fact("Counting diagonals",
         "A polygon with $n$ sides has $\\frac{n(n - 3)}{2}$ diagonals. A hexagon has "
         "$\\frac{6 \\times 3}{2} = 9$.",
         "Each corner joins to all others except itself and its two neighbours, and each diagonal gets "
         "counted from both ends."),
    Fact("Your birthday's weekday moves",
         "Your birthday falls one weekday later each year, or two if a 29 February comes in between.",
         "$365 = 52 \\times 7 + 1$. A year is 52 weeks and **one** day."),
    Fact("The leap year rule",
         "A year is a leap year if it divides by 4, except century years, which must divide by 400. So 2000 "
         "was a leap year but 1900 wasn't.",
         "A year is really about 365.2425 days, and this rule matches that almost exactly."),
    Fact("Don't count twice",
         "Number in A or B $=$ number in A $+$ number in B $-$ number in both.",
         "If 20 kids like maths, 15 like art and 8 like both, then $20 + 15 - 8 = 27$ like at least one."),
    Fact("Choosing toppings",
         "With $n$ toppings you can make $2^n$ different pizzas (counting the plain one). 5 toppings make "
         "$2^5 = 32$.",
         "Each topping is a yes-or-no choice: $2 \\times 2 \\times 2 \\times 2 \\times 2$."),
    Fact("Ten factorial is six weeks",
         "$10! = 10 \\times 9 \\times \\dots \\times 1 = 3628800$, exactly the number of seconds in 6 weeks.",
         "$6 \\times 7 \\times 24 \\times 60 \\times 60 = 3628800$. Factorials grow very fast!"),
    Fact("Zeros at the end of 100!",
         "$100!$ ends in exactly 24 zeros.",
         "Each zero needs a $2 \\times 5$, and fives are rarer. There are 20 multiples of 5 up to 100, and 4 of "
         "them (25, 50, 75, 100) give an extra 5."),
    Fact("Squares win",
         "Of all rectangles with the same perimeter, the square has the biggest area.",
         "With perimeter 20: $5 \\times 5 = 25$ beats $6 \\times 4 = 24$ beats $7 \\times 3 = 21$. Making the "
         "sides more equal always helps."),
    Fact("The domino puzzle",
         "Cut two opposite corners off a chessboard. You can **never** cover the remaining 62 squares with "
         "31 dominoes.",
         "Every domino covers one black and one white square, but the two missing corners are the same "
         "colour."),
    Fact("Casting out nines",
         "Check $38 \\times 47 = 1786$: digit sums give $2 \\times 2 = 4$, and $1+7+8+6 = 22 \\to 4$. They match!",
         "A number and its digit sum leave the same remainder when divided by 9. If they don't match, the "
         "sum is wrong."),
    Fact("Angles inside a polygon",
         "The inside angles of an $n$-sided polygon add up to $(n - 2) \\times 180^\\circ$. A pentagon: "
         "$540^\\circ$.",
         "Pick one corner and draw diagonals from it. They cut the polygon into $n - 2$ triangles."),
    Fact("Squares on a chessboard",
         "A chessboard has $204$ squares, not 64!",
         "Count every size: $64 + 49 + 36 + 25 + 16 + 9 + 4 + 1 = 204$, the sum of $1^2$ to $8^2$."),
    Fact("Fold paper to the Moon",
         "If you could fold a 0.1 mm sheet of paper 42 times, it would be thicker than the distance to the "
         "Moon.",
         "Each fold doubles it: $2^{42} \\times 0.1$ mm is about 440,000 km. The Moon is about 384,000 km "
         "away."),
    Fact("The triangle inequality",
         "In any triangle, any two sides added together are longer than the third side. So sides 2, 3 and 6 "
         "can't make a triangle.",
         "A straight line is the shortest path, so going round two sides is always longer."),
    Fact("Pascal's triangle and powers of 2",
         "The rows of Pascal's triangle add up to $1, 2, 4, 8, 16, \\dots$ Row 4 is $1, 4, 6, 4, 1$, and those "
         "add up to $16$.",
         "Each number counts the ways to choose items, and choosing any number of 4 items has $2^4$ "
         "possibilities."),
    Fact("Last digits tell you",
         "A number is divisible by 4 if its last two digits are, and by 8 if its last three are. 7,135,128 is "
         "divisible by 8 because 128 is.",
         "$100$ is a multiple of 4 and $1000$ is a multiple of 8, so only the end matters."),
    Fact("The taxicab number",
         "$1729 = 1^3 + 12^3 = 9^3 + 10^3$, the smallest number that's a sum of two cubes in two different "
         "ways.",
         "Ramanujan spotted this instantly when his friend Hardy said his taxi number, 1729, was dull."),
    Fact("Even plus even, odd plus odd",
         "odd $+$ odd $=$ even, even $+$ even $=$ even, odd $+$ even $=$ odd.",
         "This *parity* idea solves many olympiad puzzles. A knight on a chessboard always lands on the "
         "opposite colour, so it needs an even number of moves to return home."),
]


def fact_for(day: date) -> Fact:
    # step by a number coprime to len(FACTS) so neighbouring days aren't neighbouring list entries
    n = len(FACTS)
    step = next(k for k in (7, 11, 13, 17, 19, 23) if n % k)
    return FACTS[(day.toordinal() * step) % n]
