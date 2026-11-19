"""The technique creatures: one per technique, built from 8 body types plus a palette, feature and badge."""
from dataclasses import dataclass

BODY_TYPES = ("blob", "boxy", "bird", "dragonling", "jelly", "bean", "star", "fuzzball")
FEATURES = ("horns", "ears", "antenna", "crown", "halo", "tuft", "glasses", "spots", "wings", "rewind-tail",
            "box", "dice-hat", "cube-hat", "none")


@dataclass(frozen=True)
class Creature:
    tag: str
    name: str
    body: str
    main: str
    light: str
    dark: str
    feature: str
    badge: str
    catchphrase: str


def _c(tag, name, body, palette, feature, badge, catchphrase) -> Creature:
    main, light, dark = palette
    return Creature(tag, name, body, main, light, dark, feature, badge, catchphrase)


_ALL = [
    _c("arithmetic", "Sumsy", "bean", ("#3cb878", "#c8f0da", "#23865a"), "glasses", "+−", "Carry the one!"),
    _c("fractions-ratios", "Slicey", "blob", ("#ff9f43", "#ffe0bf", "#d9771a"), "ears", "½", "Fair shares!"),
    _c("percentages", "Centipup", "fuzzball", ("#ff6fae", "#ffd3e7", "#d64a8a"), "spots", "%", "100% fluffy!"),
    _c("rates-work", "Zoomlet", "bird", ("#3fa9f5", "#cde9ff", "#1f7fc4"), "wings", "km/h", "Zoom zoom!"),
    _c("word-problems", "Storybug", "jelly", ("#20c4b5", "#c5f3ef", "#13968a"), "antenna", "abc", "Once upon a sum…"),
    _c("working-backwards", "Rewindle", "blob", ("#8bc34a", "#e1f3c9", "#5e8f2c"), "rewind-tail", "↺",
       "Start at the end!"),
    _c("pattern-finding", "Pattercat", "fuzzball", ("#6f6cf0", "#d9d8ff", "#4744c4"), "ears", "123",
       "Spot the pattern!"),
    _c("sequences-series", "Seqwiggle", "bean", ("#f5b700", "#fff0bf", "#b88900"), "antenna", "Σ",
       "Next one's mine!"),
    _c("divisibility-remainders", "Remmy", "boxy", ("#ef5350", "#ffd6d5", "#b8302d"), "box", "r1", "Any leftovers?"),
    _c("primes-factors", "Primo", "star", ("#ffc107", "#fff1c4", "#c99400"), "crown", "7", "I'm indivisible!"),
    _c("last-digit", "Digitail", "dragonling", ("#00bcd4", "#c4f1f7", "#008a9c"), "none", "…7",
       "Only the end matters"),
    _c("digit-sums", "Summalump", "jelly", ("#9c6bff", "#e6dcff", "#6f43d6"), "tuft", "9", "Add my digits!"),
    _c("parity", "Evenix", "blob", ("#7c5cff", "#c9bcff", "#5636d6"), "horns", "2k", "Even steven!"),
    _c("pigeonhole", "Coopie", "bird", ("#5c7cfa", "#d6defe", "#3a56c9"), "box", "n+1", "One box too few!"),
    _c("casework", "Casey", "boxy", ("#a1887f", "#eadbd5", "#6f5b53"), "glasses", "A|B", "Case by case!"),
    _c("combinations", "Combo", "fuzzball", ("#e040fb", "#f6c9fd", "#a91fc0"), "antenna", "nCr", "So many ways!"),
    _c("complementary-counting", "Flipsy", "jelly", ("#ff7f6e", "#ffd9d3", "#d4523f"), "halo", "1−x",
       "Count the rest!"),
    _c("probability", "Dicey", "boxy", ("#3f51b5", "#d0d6f6", "#2a3889"), "dice-hat", "⅙", "Feeling lucky!"),
    _c("angle-chasing", "Anglo", "star", ("#ff7043", "#ffd5c6", "#cc4a22"), "ears", "90°", "Chase that angle!"),
    _c("areas", "Patchy", "blob", ("#26a69a", "#c3ece8", "#1a7a71"), "spots", "m²", "Cover me up!"),
    _c("pythagoras", "Pythorn", "dragonling", ("#7cb342", "#dcefc8", "#558a26"), "horns", "c²",
       "Square the sides!"),
    _c("similar-triangles", "Twinkle", "star", ("#ba68c8", "#efd6f4", "#8a3f99"), "tuft", "△▲", "Same shape!"),
    _c("circles", "Orbi", "blob", ("#2196f3", "#cbe5fd", "#1769b8"), "halo", "π", "Round and round!"),
    _c("3d-shapes", "Cubert", "boxy", ("#607d8b", "#d5e0e5", "#3f5764"), "cube-hat", "3D", "I'm a cube!"),
    _c("logic", "Sherlox", "bird", ("#00897b", "#c2ebe6", "#005f56"), "glasses", "∴", "Elementary!"),
    _c("clocks-calendars", "Tickle", "bean", ("#ffa726", "#ffe5c2", "#cf7a00"), "antenna", "12", "Tick tock!"),
    _c("estimation", "Guessie", "fuzzball", ("#c0a062", "#efe3c8", "#8d733c"), "tuft", "≈", "About right!"),
    _c("algebra", "Xeno", "bean", ("#ab47bc", "#ecd1f1", "#7b2c88"), "antenna", "x", "Solve for me!"),
    _c("optimisation", "Maxi", "dragonling", ("#e53935", "#fbd0cf", "#ab201d"), "crown", "max", "Biggest wins!"),
    _c("invariants", "Stayzy", "jelly", ("#78909c", "#dae3e7", "#51656f"), "halo", "=", "I never change!"),
]

CREATURES: dict[str, Creature] = {c.tag: c for c in _ALL}
STAGE_LABEL = {"egg": "egg", "baby": "baby", "grown": "grown-up"}
