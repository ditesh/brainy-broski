"""A child's fun "all about me" profile, and a maths fact about their favourite number."""
from math import isqrt

AVATARS = ["🦊", "🐼", "🐯", "🦉", "🐙", "🦖", "🐬", "🦄", "🚀", "⚽", "🎮", "🤖"]
TEXT_FIELDS = [  # (field, label, placeholder)
    ("favourite_game", "Favourite game", "e.g. Minecraft"),
    ("favourite_food", "Favourite food", "e.g. Nasi lemak"),
    ("favourite_animal", "Favourite animal", "e.g. Tiger"),
    ("superpower", "If I had a superpower, it would be…", "e.g. Flying"),
]
TEXT_MAX = 60
NUMBER_MAX = 1_000_000


class ProfileError(ValueError):
    pass


def clean_profile(form: dict) -> dict:
    """Keep only known fields, trimmed; drop blanks. Raises ProfileError with a kid-friendly message."""
    out: dict = {}
    if form.get("avatar") in AVATARS:
        out["avatar"] = form["avatar"]
    for field, label, _ in TEXT_FIELDS:
        v = (form.get(field) or "").strip()
        if len(v) > TEXT_MAX:
            raise ProfileError(f"{label} is a bit long — keep it under {TEXT_MAX} letters.")
        if v:
            out[field] = v
    n = (form.get("favourite_number") or "").strip().replace(",", "")
    if n:
        if not n.isdigit() or int(n) > NUMBER_MAX:
            raise ProfileError(f"Favourite number should be a whole number from 0 to {NUMBER_MAX:,}.")
        out["favourite_number"] = int(n)
    return out


def _is_prime(n: int) -> bool:
    return n >= 2 and all(n % d for d in range(2, isqrt(n) + 1))


def _is_fib(n: int) -> bool:
    sq = lambda x: isqrt(x) ** 2 == x
    return sq(5 * n * n + 4) or sq(5 * n * n - 4)


def number_fact(n: int) -> str:
    """One cheerful true fact about n, the most special one first."""
    if n == 0:
        return "0 is the only number that is neither positive nor negative — and zero was a huge invention!"
    if n == 1:
        return "1 is neither prime nor composite, and every number is a multiple of 1."
    if n in (6, 28, 496, 8128):
        return f"{n} is a perfect number: it equals the sum of its other factors!"
    if _is_prime(n):
        return f"{n} is a prime number — only 1 and {n} divide it."
    r = isqrt(n)
    if r * r == n:
        return f"{n} is a perfect square: {r} × {r}."
    c = round(n ** (1 / 3))
    if c ** 3 == n:
        return f"{n} is a perfect cube: {c} × {c} × {c}."
    t = (isqrt(8 * n + 1) - 1) // 2
    if t * (t + 1) // 2 == n:
        return f"{n} is a triangular number: 1 + 2 + … + {t}."
    if _is_fib(n):
        return f"{n} is a Fibonacci number — each one is the sum of the two before it."
    factors = sum(1 if d * d == n else 2 for d in range(1, isqrt(n) + 1) if n % d == 0)
    return f"{n} has {factors} factors. Can you find them all?"
