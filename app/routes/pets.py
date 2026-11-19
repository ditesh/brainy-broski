"""Technique pets: the child's collection, choosing a buddy, and the parent preview of every creature."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import current_user, require_parent
from app.db import get_db
from app.models import Role, User
from app.pets.creatures import CREATURES
from app.pets.growth import GROWN, HATCH, buddy, growth, shown_tags
from app.techniques import TECHNIQUES
from app.web import render

router = APIRouter()
TECHNIQUE_NAMES = {t: name for t, name, _ in TECHNIQUES}
TECHNIQUE_ABOUT = {t: about for t, _, about in TECHNIQUES}


def progress_text(points: int) -> str:
    if points < HATCH:
        return f"{points} / {HATCH} to hatch"
    if points < GROWN:
        return f"{points} / {GROWN} to grow up"
    return "Grown-up!"


def _page(request: Request, db: Session, user: User, status_code: int = 200, **extra):
    states = growth(db, user)
    shown = shown_tags(db, user, states)
    pets = [{"c": CREATURES[t], "state": states[t], "progress": progress_text(states[t].points),
             "pct": min(100, round(100 * states[t].points / GROWN)), "technique": TECHNIQUE_NAMES[t],
             "about": TECHNIQUE_ABOUT[t]} for t in shown]
    return render(request, "pets/index.html", status_code=status_code, pets=pets, mystery=len(TECHNIQUES) - len(shown),
                  buddy=buddy(db, user, states), **extra)


@router.get("/pets")
def my_pets(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != Role.child:
        return RedirectResponse("/parent/pets/preview", status_code=303)
    return _page(request, db, user)


@router.post("/pets/buddy")
def choose_buddy(request: Request, tag: str = Form(""), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    if user.role != Role.child:
        raise HTTPException(status_code=403)
    states = growth(db, user)
    if tag not in states or states[tag].stage == "egg":
        return _page(request, db, user, status_code=400, error="Only a hatched pet can be your buddy.")
    user.buddy_tag = tag
    db.commit()
    return _page(request, db, user, saved=CREATURES[tag].name)


@router.get("/parent/pets/preview")
def preview(request: Request, user: User = Depends(require_parent)):
    creatures = [CREATURES[t] for t, _, _ in TECHNIQUES]
    return render(request, "pets/preview.html", creatures=creatures, names=TECHNIQUE_NAMES)
