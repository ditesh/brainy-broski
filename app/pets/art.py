"""Draws a creature as SVG on one shared rig, so every pet can breathe, blink, look, giggle, hatch and grow.

Rig classes (animated by app/static/pets.css and pets.js):
  jump > float > breathe ... pupils, lid, mouth-smile, mouth-o, tail, wings, badge, halo
  egg: egg-all, wobble-idle, peek, shell-top, shell-bottom, crack
"""
import itertools
import math

from markupsafe import Markup, escape

from app.pets.creatures import Creature

_ids = itertools.count(1)
INK = "#241a4d"
GOLD, GOLD_EDGE = "#ffd34d", "#e0ab12"
GEOM = {"baby": (100.0, 128.0, 46.0, 44.0), "grown": (100.0, 116.0, 60.0, 58.0)}
ADJUST = {"bean": (0.82, 1.06), "boxy": (0.95, 0.92), "jelly": (1.0, 0.95)}


def _n(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _pts(points) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in points)


# ---------- bodies ----------

def _top(body: str, cy: float, rx: float, ry: float) -> float:
    if body == "star":
        return cy - rx * 1.18
    if body == "jelly":
        return cy - ry * 0.9
    return cy - ry


def _body_shape(body, cx, cy, rx, ry, fill) -> str:
    if body == "boxy":
        return f'<rect x="{_n(cx - rx)}" y="{_n(cy - ry)}" width="{_n(2 * rx)}" height="{_n(2 * ry)}" rx="{_n(rx * .38)}" fill="{fill}"/>'
    if body == "jelly":
        base, w = cy + ry * .6, 2 * rx / 4
        d = [f"M{_n(cx - rx)} {_n(cy + ry * .25)}", f"A{_n(rx)} {_n(ry * 1.15)} 0 0 1 {_n(cx + rx)} {_n(cy + ry * .25)}",
             f"L{_n(cx + rx)} {_n(base)}"]
        x = cx + rx
        for _ in range(4):
            d.append(f"Q{_n(x - w / 2)} {_n(base + ry * .3)} {_n(x - w)} {_n(base)}")
            x -= w
        return f'<path d="{" ".join(d)} Z" fill="{fill}"/>'
    if body == "star":
        big = rx * 1.18
        pts = [(cx + (big if k % 2 == 0 else big * .56) * math.cos(math.radians(-90 + k * 36)),
                cy + (big if k % 2 == 0 else big * .56) * math.sin(math.radians(-90 + k * 36))) for k in range(10)]
        return f'<polygon points="{_pts(pts)}" fill="{fill}" stroke="{fill}" stroke-width="16" stroke-linejoin="round"/>'
    if body == "fuzzball":
        pts = [(cx + rx * (1 if k % 2 else 1.09) * math.cos(2 * math.pi * k / 40),
                cy + ry * (1 if k % 2 else 1.09) * math.sin(2 * math.pi * k / 40)) for k in range(40)]
        return f'<polygon points="{_pts(pts)}" fill="{fill}" stroke="{fill}" stroke-width="4" stroke-linejoin="round"/>'
    return f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(rx)}" ry="{_n(ry)}" fill="{fill}"/>'


def _belly(body, cx, cy, rx, ry, fill) -> str:
    if body == "star":
        return f'<circle cx="{_n(cx)}" cy="{_n(cy + ry * .24)}" r="{_n(rx * .42)}" fill="{fill}"/>'
    if body == "jelly":
        return f'<ellipse cx="{_n(cx)}" cy="{_n(cy + ry * .2)}" rx="{_n(rx * .5)}" ry="{_n(ry * .4)}" fill="{fill}"/>'
    if body == "boxy":
        return (f'<rect x="{_n(cx - rx * .55)}" y="{_n(cy - ry * .02)}" width="{_n(rx * 1.1)}" height="{_n(ry * .78)}" '
                f'rx="{_n(rx * .28)}" fill="{fill}"/>')
    return f'<ellipse cx="{_n(cx)}" cy="{_n(cy + ry * .3)}" rx="{_n(rx * .56)}" ry="{_n(ry * .5)}" fill="{fill}"/>'


def _feet(body, cx, cy, rx, ry, c: Creature) -> str:
    if body == "star":
        return ""
    if body == "jelly":
        out = []
        for dx in (-.5, 0, .5):
            x, y = cx + dx * rx, cy + ry * .6
            out.append(f'<path d="M{_n(x)} {_n(y)} q-7 9 0 18 q6 7 0 14" stroke="{c.dark}" stroke-width="6" '
                       f'fill="none" stroke-linecap="round"/>')
        return "".join(out)
    y = cy + ry - 2
    return "".join(f'<ellipse cx="{_n(cx + s * rx * .42)}" cy="{_n(y)}" rx="{_n(rx * .22)}" ry="{_n(rx * .12)}" '
                   f'fill="{c.dark}"/>' for s in (-1, 1))


def _spikes(cx, cy, rx, ry, c: Creature) -> str:
    out = []
    for dx in (-.42, 0, .42):
        x = cx + dx * rx
        y = cy - ry * math.sqrt(max(0.0, 1 - dx * dx)) + 8
        out.append(f'<polygon points="{_pts([(x - 9, y), (x, y - 22), (x + 9, y)])}" fill="{c.dark}" '
                   f'stroke="{c.dark}" stroke-width="3" stroke-linejoin="round"/>')
    return "".join(out)


def _dragon_tail(cx, cy, rx, ry, c: Creature) -> str:
    x0, y0 = cx + rx * .75, cy + ry * .5
    return (f'<g class="tail"><path d="M{_n(x0)} {_n(y0)} C{_n(x0 + 30)} {_n(y0 + 8)} {_n(x0 + 44)} {_n(y0 - 12)} '
            f'{_n(x0 + 42)} {_n(y0 - 30)}" stroke="{c.main}" stroke-width="12" fill="none" stroke-linecap="round"/>'
            f'<polygon points="{_pts([(x0 + 30, y0 - 30), (x0 + 42, y0 - 52), (x0 + 54, y0 - 28)])}" fill="{c.dark}" '
            f'stroke="{c.dark}" stroke-width="3" stroke-linejoin="round"/></g>')


def _wings(cx, cy, rx, ry, c: Creature) -> str:
    out = []
    for s in (-1, 1):
        x0 = cx + s * rx * .7
        d = (f"M{_n(x0)} {_n(cy - ry * .05)} Q{_n(cx + s * rx * 1.4)} {_n(cy - ry * .65)} {_n(cx + s * rx * 1.2)} "
             f"{_n(cy + ry * .25)} Q{_n(cx + s * rx * .98)} {_n(cy + ry * .12)} {_n(x0)} {_n(cy + ry * .22)} Z")
        out.append(f'<path d="{d}" fill="{c.light}" stroke="{c.main}" stroke-width="3" stroke-linejoin="round"/>')
    return f'<g class="wings">{"".join(out)}</g>'


# ---------- features ----------

def _back_feature(feature, cx, cy, rx, ry, top, c: Creature) -> str:
    if feature == "horns":
        return "".join(f'<polygon points="{_pts([(cx + s * rx * .5, top + ry * .28), (cx + s * rx * .66, top - ry * .34), (cx + s * rx * .2, top + ry * .1)])}" '
                       f'fill="{GOLD}" stroke="{GOLD_EDGE}" stroke-width="3" stroke-linejoin="round"/>' for s in (-1, 1))
    if feature == "ears":
        out = []
        for s in (-1, 1):
            out.append(f'<polygon points="{_pts([(cx + s * rx * .6, top + ry * .4), (cx + s * rx * .62, top - ry * .34), (cx + s * rx * .14, top + ry * .14)])}" '
                       f'fill="{c.main}" stroke="{c.main}" stroke-width="6" stroke-linejoin="round"/>')
            out.append(f'<polygon points="{_pts([(cx + s * rx * .52, top + ry * .26), (cx + s * rx * .54, top - ry * .16), (cx + s * rx * .27, top + ry * .14)])}" '
                       f'fill="{c.light}"/>')
        return "".join(out)
    if feature == "antenna":
        out = []
        for s in (-1, 1):
            x1, y1 = cx + s * rx * .4, top - ry * .42
            out.append(f'<path d="M{_n(cx + s * rx * .18)} {_n(top + 12)} Q{_n(cx + s * rx * .22)} {_n(top - ry * .2)} '
                       f'{_n(x1)} {_n(y1)}" stroke="{c.dark}" stroke-width="4" fill="none" stroke-linecap="round"/>')
            out.append(f'<circle cx="{_n(x1)}" cy="{_n(y1)}" r="7" fill="{c.light}" stroke="{c.dark}" stroke-width="3"/>')
        return "".join(out)
    if feature == "wings":
        return _wings(cx, cy, rx, ry, c)
    if feature == "rewind-tail":
        x0, y0 = cx + rx * .78, cy + ry * .45
        end = (x0 + 26, y0 - 44)
        return (f'<g class="tail"><path d="M{_n(x0)} {_n(y0)} C{_n(x0 + 34)} {_n(y0 + 4)} {_n(x0 + 44)} {_n(y0 - 26)} '
                f'{_n(end[0])} {_n(end[1])}" stroke="{c.dark}" stroke-width="10" fill="none" stroke-linecap="round"/>'
                f'<polygon points="{_pts([(end[0] - 14, end[1] - 4), (end[0] + 4, end[1] - 16), (end[0] + 8, end[1] + 6)])}" '
                f'fill="{c.dark}" stroke="{c.dark}" stroke-width="3" stroke-linejoin="round"/></g>')
    return ""


def _front_feature(feature, cx, cy, rx, ry, top, eyes, c: Creature) -> str:
    if feature == "crown":
        p = [(cx - rx * .36, top + 8), (cx - rx * .36, top - 20), (cx - rx * .18, top - 6), (cx, top - 28),
             (cx + rx * .18, top - 6), (cx + rx * .36, top - 20), (cx + rx * .36, top + 8)]
        return (f'<polygon points="{_pts(p)}" fill="{GOLD}" stroke="{GOLD_EDGE}" stroke-width="3" stroke-linejoin="round"/>'
                f'<circle cx="{_n(cx)}" cy="{_n(top - 2)}" r="4" fill="#ff6fb1"/>')
    if feature == "halo":
        return (f'<ellipse class="halo" cx="{_n(cx)}" cy="{_n(top - 16)}" rx="{_n(rx * .46)}" ry="9" fill="none" '
                f'stroke="{GOLD}" stroke-width="6"/>')
    if feature == "tuft":
        return (f'<path d="M{_n(cx - 8)} {_n(top + 6)} q-6 -22 -18 -20 M{_n(cx)} {_n(top + 4)} q0 -26 9 -30 '
                f'M{_n(cx + 8)} {_n(top + 6)} q10 -18 20 -14" stroke="{c.dark}" stroke-width="5" fill="none" '
                f'stroke-linecap="round"/>')
    if feature == "glasses":
        (lx, ly), (rx_, _), ew = eyes[0], eyes[1], eyes[2]
        r = ew + 5
        return (f'<g fill="rgba(255,255,255,.18)" stroke="{INK}" stroke-width="3.5">'
                f'<circle cx="{_n(lx)}" cy="{_n(ly)}" r="{_n(r)}"/><circle cx="{_n(rx_)}" cy="{_n(ly)}" r="{_n(r)}"/></g>'
                f'<path d="M{_n(lx + r)} {_n(ly)} Q{_n(cx)} {_n(ly - 6)} {_n(rx_ - r)} {_n(ly)}" stroke="{INK}" '
                f'stroke-width="3.5" fill="none"/>')
    if feature == "spots":
        return "".join(f'<circle cx="{_n(cx + dx * rx)}" cy="{_n(cy + dy * ry)}" r="{_n(r * rx)}" fill="{c.dark}" '
                       f'opacity=".35"/>' for dx, dy, r in ((-.62, .02, .11), (.64, -.18, .09), (.5, .5, .07)))
    if feature == "dice-hat":
        x, y, s = cx + 6, top - 18, 28
        pips = "".join(f'<circle cx="{_n(x + px * s)}" cy="{_n(y + py * s)}" r="3" fill="{INK}"/>'
                       for px, py in ((.25, .25), (.5, .5), (.75, .75)))
        return (f'<g transform="rotate(14 {_n(x + s / 2)} {_n(y + s / 2)})"><rect x="{_n(x)}" y="{_n(y)}" width="{s}" '
                f'height="{s}" rx="6" fill="#fff" stroke="{INK}" stroke-width="3"/>{pips}</g>')
    if feature == "cube-hat":
        x, y, s = cx, top - 6, 18
        topf = [(x, y - s), (x + s, y - s / 2), (x, y), (x - s, y - s / 2)]
        left = [(x - s, y - s / 2), (x, y), (x, y + s), (x - s, y + s / 2)]
        right = [(x + s, y - s / 2), (x, y), (x, y + s), (x + s, y + s / 2)]
        return "".join(f'<polygon points="{_pts(p)}" fill="{col}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>'
                       for p, col in ((left, c.main), (right, c.dark), (topf, c.light)))
    if feature == "box":
        y0, h = cy + ry * .42, min(ry * .78, 182 - (cy + ry * .42))
        return (f'<rect x="{_n(cx - rx * .78)}" y="{_n(y0)}" width="{_n(rx * 1.56)}" height="{_n(h)}" rx="4" '
                f'fill="#d9a066" stroke="#a8733f" stroke-width="3"/>'
                f'<polygon points="{_pts([(cx - rx * .78, y0), (cx - rx * .95, y0 - 12), (cx - rx * .1, y0 - 12), (cx - rx * .02, y0)])}" '
                f'fill="#e8b884" stroke="#a8733f" stroke-width="3" stroke-linejoin="round"/>'
                f'<polygon points="{_pts([(cx + rx * .78, y0), (cx + rx * .95, y0 - 12), (cx + rx * .1, y0 - 12), (cx + rx * .02, y0)])}" '
                f'fill="#e8b884" stroke="#a8733f" stroke-width="3" stroke-linejoin="round"/>')
    return ""


# ---------- face ----------

def _face(body, cx, cy, rx, ry, c: Creature, u: str):
    fy = cy - (0.16 if body == "star" else 0.28 if body == "jelly" else 0.12) * ry
    dx, ew, eh = rx * .34, rx * .19, rx * .21
    pr = rx * .11
    eyes = [(cx - dx, fy), (cx + dx, fy)]
    whites = "".join(f'<ellipse cx="{_n(x)}" cy="{_n(y)}" rx="{_n(ew)}" ry="{_n(eh)}" fill="#fff"/>' for x, y in eyes)
    pupils = "".join(f'<circle cx="{_n(x + 1.5)}" cy="{_n(y + 2)}" r="{_n(pr)}" fill="{INK}"/>'
                     f'<circle cx="{_n(x + 1.5 + pr * .4)}" cy="{_n(y + 2 - pr * .45)}" r="{_n(pr * .36)}" fill="#fff"/>'
                     for x, y in eyes)
    lids = "".join(f'<rect class="lid" x="{_n(x - ew)}" y="{_n(y - eh)}" width="{_n(2 * ew)}" height="{_n(2 * eh)}" '
                   f'rx="{_n(ew)}" fill="{c.main}"/>' for x, y in eyes)
    cheeks = "".join(f'<ellipse cx="{_n(x + s * rx * .14)}" cy="{_n(y + rx * .3)}" rx="{_n(rx * .13)}" ry="{_n(rx * .07)}" '
                     f'fill="#ff8fc7" opacity=".55"/>' for (x, y), s in zip(eyes, (-1, 1)))
    my = fy + rx * (.42 if body == "bird" else .32)
    mouth = (f'<path class="mouth-smile" d="M{_n(cx - rx * .11)} {_n(my)} q{_n(rx * .11)} {_n(rx * .1)} {_n(rx * .22)} 0" '
             f'stroke="{INK}" stroke-width="3.5" fill="none" stroke-linecap="round"/>'
             f'<ellipse class="mouth-o" cx="{_n(cx)}" cy="{_n(my + 2)}" rx="{_n(rx * .08)}" ry="{_n(rx * .1)}" fill="{INK}"/>')
    beak = ""
    if body == "bird":
        by = fy + rx * .2
        beak = (f'<polygon points="{_pts([(cx - rx * .12, by), (cx + rx * .12, by), (cx, by + rx * .15)])}" fill="#ffb300" '
                f'stroke="#e08a00" stroke-width="2.5" stroke-linejoin="round"/>')
    svg = whites + f'<g class="pupils">{pupils}</g>' + lids + cheeks + mouth + beak
    return svg, (eyes[0], eyes[1], ew)


# ---------- stages ----------

def _defs(u: str, c: Creature) -> str:
    return (f'<defs><radialGradient id="{u}-body" cx="38%" cy="32%" r="75%"><stop offset="0" stop-color="{c.light}"/>'
            f'<stop offset=".55" stop-color="{c.main}"/><stop offset="1" stop-color="{c.dark}"/></radialGradient>'
            f'<radialGradient id="{u}-belly" cx="50%" cy="35%" r="65%"><stop offset="0" stop-color="#fff"/>'
            f'<stop offset="1" stop-color="{c.light}"/></radialGradient>'
            f'<linearGradient id="{u}-shell" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fffdf5"/>'
            f'<stop offset="1" stop-color="{c.light}"/></linearGradient>'
            f'<radialGradient id="{u}-glow"><stop offset="0" stop-color="#fff"/><stop offset=".5" stop-color="{c.light}"/>'
            f'<stop offset="1" stop-color="{c.light}" stop-opacity="0"/></radialGradient></defs>')


SPARKS = ('<g class="sparks">'
          '<path class="spark" d="M38 66 l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4 Z" fill="#ffd34d"/>'
          '<path class="spark" d="M162 56 l3 8 l8 3 l-8 3 l-3 8 l-3 -8 l-8 -3 l8 -3 Z" fill="#ff6fb1"/>'
          '<path class="spark" d="M154 118 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3 Z" fill="#7c5cff"/></g>')


def _creature(c: Creature, stage: str, u: str) -> str:
    cx, cy, rx, ry = GEOM[stage]
    ax, ay = ADJUST.get(c.body, (1.0, 1.0))
    rx, ry = rx * ax, ry * ay
    top = _top(c.body, cy, rx, ry)
    grown = stage == "grown"
    back = []
    if c.body == "dragonling":
        back.append(_dragon_tail(cx, cy, rx, ry, c))
        back.append(_spikes(cx, cy, rx, ry, c))
    if grown:
        if c.body == "bird" and c.feature != "wings":
            back.append(_wings(cx, cy, rx, ry, c))
        back.append(_back_feature(c.feature, cx, cy, rx, ry, top, c))
    feet = _feet(c.body, cx, cy, rx, ry, c)
    face, eyes = _face(c.body, cx, cy, rx, ry, c, u)
    front = ""
    if grown:
        front = _front_feature(c.feature, cx, cy, rx, ry, top, eyes, c)
        size = {1: 28, 2: 24, 3: 19}.get(len(c.badge), 15)
        by = (cy + ry * .42 + ry * .42) if c.feature == "box" else cy + ry * (.42 if c.body == "star" else .44 if c.body == "jelly" else .5)
        front += (f'<text class="badge" x="{_n(cx)}" y="{_n(by + size * .35)}" text-anchor="middle" font-size="{size}" '
                  f'font-weight="900" font-family="Nunito, system-ui, sans-serif" fill="{c.dark}">{escape(c.badge)}</text>')
    else:
        zig = [(cx - rx * .55, top + ry * .3)]
        for k in range(1, 7):
            zig.append((cx - rx * .55 + k * rx * 1.1 / 6, top + ry * (.18 if k % 2 else .3)))
        front = (f'<path d="M{_n(cx - rx * .55)} {_n(top + ry * .3)} Q{_n(cx)} {_n(top - ry * .5)} {_n(cx + rx * .55)} '
                 f'{_n(top + ry * .3)} L{" L".join(f"{_n(x)} {_n(y)}" for x, y in reversed(zig))} Z" '
                 f'fill="url(#{u}-shell)" stroke="#e2c46a" stroke-width="2.5" stroke-linejoin="round"/>')
    spots_under_face = c.feature == "spots" and grown
    inner = (feet + _body_shape(c.body, cx, cy, rx, ry, f"url(#{u}-body)")
             + _belly(c.body, cx, cy, rx, ry, f"url(#{u}-belly)")
             + (front if spots_under_face else "") + face + ("" if spots_under_face else front))
    glow = f'<circle class="glow" cx="100" cy="112" r="95" fill="url(#{u}-glow)"/>' if grown else ""
    shadow = f'<ellipse class="shadow" cx="100" cy="186" rx="{_n(rx * .9)}" ry="7"/>'
    body = f'<g class="breathe">{inner}</g>'
    if grown:
        body = f'<g class="float">{"".join(back)}{body}</g>'
    else:
        body = "".join(back) + body
    return glow + shadow + f'<g class="jump">{body}</g>' + SPARKS


def _egg(c: Creature, u: str) -> str:
    peek_face = (f'<circle cx="100" cy="112" r="34" fill="url(#{u}-body)"/>'
                 f'<ellipse cx="88" cy="106" rx="7" ry="8" fill="#fff"/><ellipse cx="112" cy="106" rx="7" ry="8" fill="#fff"/>'
                 f'<g class="pupils"><circle cx="89" cy="108" r="4" fill="{INK}"/><circle cx="113" cy="108" r="4" fill="{INK}"/></g>'
                 f'<path d="M94 120 q6 5 12 0" stroke="{INK}" stroke-width="3" fill="none" stroke-linecap="round"/>')
    zig = "L130 110 L118 120 L106 108 L94 120 L82 110 L70 120 Z"
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c.main}" opacity=".45"/>'
                   for x, y, r in ((76, 76, 5), (124, 70, 4), (118, 150, 5), (84, 156, 4)))
    size = {1: 30, 2: 28, 3: 22}.get(len(c.badge), 18)
    return (f'<ellipse class="shadow" cx="100" cy="182" rx="40" ry="7"/>'
            f'<g class="egg-all wobble-idle">'
            f'<g class="peek">{peek_face}</g>'
            f'<g class="shell-bottom"><path d="M58 118 Q58 176 100 176 Q142 176 142 118 {zig}" fill="url(#{u}-shell)" '
            f'stroke="{c.main}" stroke-width="2.5" stroke-linejoin="round"/></g>'
            f'<g class="shell-top"><path d="M58 118 Q58 40 100 40 Q142 40 142 118 {zig}" fill="url(#{u}-shell)" '
            f'stroke="{c.main}" stroke-width="2.5" stroke-linejoin="round"/>{dots}'
            f'<text x="100" y="{100 - size * .1:.0f}" text-anchor="middle" font-size="{size}" font-weight="900" '
            f'font-family="Nunito, system-ui, sans-serif" fill="{c.main}" opacity=".6">{escape(c.badge)}</text></g>'
            f'<path class="crack" d="M74 96 l10 10 l-6 10 l12 6" stroke="{c.dark}" stroke-width="3" fill="none"/>'
            f'<path class="crack" d="M126 90 l-8 12 l8 8 l-6 12" stroke="{c.dark}" stroke-width="3" fill="none"/></g>'
            + SPARKS)


def pet_svg(c: Creature, stage: str) -> Markup:
    u = f"pet{next(_ids)}"
    inner = _egg(c, u) if stage == "egg" else _creature(c, stage, u)
    return Markup(f'<svg class="pet-svg" viewBox="0 0 200 200" aria-hidden="true" focusable="false">'
                  f'{_defs(u, c)}{inner}</svg>')
