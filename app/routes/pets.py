"""Technique pets: the parent preview of every creature (and, later, the child's collection)."""
from fastapi import APIRouter, Depends, Request

from app.auth import require_parent
from app.models import User
from app.pets.creatures import CREATURES
from app.techniques import TECHNIQUES
from app.web import render

router = APIRouter()
TECHNIQUE_NAMES = {t: name for t, name, _ in TECHNIQUES}


@router.get("/parent/pets/preview")
def preview(request: Request, user: User = Depends(require_parent)):
    creatures = [CREATURES[t] for t, _, _ in TECHNIQUES]
    return render(request, "pets/preview.html", creatures=creatures, names=TECHNIQUE_NAMES)
