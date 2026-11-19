"""The 30 technique creatures: catalogue rules, shared animation rig, and the parent preview."""
import re
from collections import Counter

from app.pets.creatures import BODY_TYPES, CREATURES
from app.techniques import TECHNIQUES


def test_one_creature_per_technique():
    assert set(CREATURES) == {t for t, _, _ in TECHNIQUES}
    assert all(c.tag == tag for tag, c in CREATURES.items())


def test_names_unique_and_every_body_used_at_least_twice():
    names = [c.name for c in CREATURES.values()]
    assert len(set(names)) == len(names)
    bodies = Counter(c.body for c in CREATURES.values())
    assert set(bodies) == set(BODY_TYPES) and min(bodies.values()) >= 2


def test_badge_short():
    for c in CREATURES.values():
        assert 1 <= len(c.badge) <= 4, c.name
        assert 1 <= len(c.catchphrase) <= 24, c.name


def test_palettes_are_colours():
    hexcol = re.compile(r"^#[0-9a-f]{6}$")
    for c in CREATURES.values():
        assert all(hexcol.match(x) for x in (c.main, c.light, c.dark)), c.name


def test_evenix_is_parity():
    c = CREATURES["parity"]
    assert c.name == "Evenix" and c.badge == "2k"


def test_every_creature_renders_each_stage_with_rig(parent_client):
    html = parent_client.get("/parent/pets/preview").text
    assert html.count('class="pet-slot') == 90
    for stage in ("baby", "grown"):
        slots = re.findall(rf'data-stage="{stage}".*?</svg>', html, re.S)
        assert len(slots) == 30
        for s in slots:
            for part in ('class="pupils"', 'class="lid"', 'class="mouth-smile"', 'class="mouth-o"',
                         'class="breathe"', 'class="jump"'):
                assert part in s
    eggs = re.findall(r'data-stage="egg".*?</svg>', html, re.S)
    assert len(eggs) == 30 and all('class="shell-top"' in e and 'class="peek"' in e for e in eggs)
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids))


def test_slots_are_accessible(parent_client):
    html = parent_client.get("/parent/pets/preview").text
    assert 'aria-label="Evenix, grown-up"' in html and 'role="button"' in html and 'tabindex="0"' in html


def test_preview_parent_only(child_client):
    assert child_client.get("/parent/pets/preview").status_code == 403


def test_pet_assets_loaded(child_client):
    html = child_client.get("/practice").text
    assert "/static/pets.css" in html and "/static/pets.js" in html
