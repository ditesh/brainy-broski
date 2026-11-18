from sqlalchemy.orm import Session

# (tag, name, kid-friendly description)
TECHNIQUES: list[tuple[str, str, str]] = [
    ("arithmetic", "Careful arithmetic", "Doing the sums step by step, and checking the order of operations: brackets, then × and ÷, then + and −."),
    ("fractions-ratios", "Fractions and ratios", "Turning 'parts of a whole' into fractions, and using ratios to compare amounts."),
    ("percentages", "Percentages", "Percent means 'out of 100'. Change it to a fraction or decimal to work with it."),
    ("rates-work", "Rates and work", "If someone does a job in 3 hours, they do 1/3 of the job each hour. Add the rates when people work together."),
    ("word-problems", "Setting up word problems", "Turn the story into numbers: name the unknown, write what you know as equations."),
    ("working-backwards", "Working backwards", "Start from the end result and undo each step until you reach the start."),
    ("pattern-finding", "Finding patterns", "Try small cases, write the results in a list, and look for what repeats or grows."),
    ("sequences-series", "Sequences and sums", "Spot how each term grows, and use pairing tricks to add many terms quickly."),
    ("divisibility-remainders", "Divisibility and remainders", "Use divisibility rules and think about what is left over after dividing."),
    ("primes-factors", "Primes and factors", "Break numbers into prime factors; counting factors comes from the powers."),
    ("last-digit", "Last digit tricks", "Only the last digits matter for the last digit. Powers repeat their last digit in a cycle."),
    ("digit-sums", "Digit sums and place value", "Think about each digit's place (ones, tens, hundreds) and what the digits add up to."),
    ("parity", "Odd and even", "Ask whether things are odd or even. Odd + odd = even, and that can rule answers out fast."),
    ("pigeonhole", "Pigeonhole principle", "If you put more pigeons than holes, some hole gets two. Use it to prove something must happen."),
    ("casework", "Counting by cases", "Split the problem into separate cases, count each one, then add them up."),
    ("combinations", "Combinations and arrangements", "Count choices with multiplication: ways for the first × ways for the second..."),
    ("complementary-counting", "Counting what you don't want", "Sometimes it's easier to count everything, then subtract the cases you don't want."),
    ("probability", "Probability", "Probability = favourable outcomes ÷ all equally likely outcomes."),
    ("angle-chasing", "Angle chasing", "Fill in angles one by one using straight lines (180°), triangles (180°) and special shapes."),
    ("areas", "Areas and shading", "Split shapes into rectangles and triangles, or take the big shape minus the bits you don't want."),
    ("pythagoras", "Pythagoras", "In a right triangle, a² + b² = c², where c is the longest side."),
    ("similar-triangles", "Similar triangles", "Triangles with the same angles have sides in the same ratio."),
    ("circles", "Circles", "Use radius, diameter, π, and the facts that tangents and radii meet at right angles."),
    ("3d-shapes", "3D shapes and cubes", "Picture the solid, count faces, edges and corners, and think about nets and slices."),
    ("logic", "Logic puzzles", "List what each statement says, try each possibility, and cross out the ones that clash."),
    ("clocks-calendars", "Clocks and calendars", "Count in hours, minutes and days carefully; days of the week repeat every 7."),
    ("estimation", "Estimation and bounds", "Find numbers just below and just above to trap the answer, like squares around a square root."),
    ("algebra", "Algebra", "Use a letter for the unknown, then rearrange and simplify the equation."),
    ("optimisation", "Biggest and smallest", "To find a maximum or minimum, try the extreme cases and explain why you can't do better."),
    ("invariants", "Things that never change", "Look for a quantity that stays the same no matter what moves you make."),
]

TECHNIQUE_TAGS: set[str] = {t[0] for t in TECHNIQUES}


def seed_techniques(db: Session) -> None:
    from app.models import Technique
    for tag, name, desc in TECHNIQUES:
        t = db.get(Technique, tag)
        if t is None:
            db.add(Technique(tag=tag, name=name, kid_description=desc))
    db.commit()
