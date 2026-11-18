from fastapi import APIRouter, Depends, Request

from app.auth import require_user
from app.models import User
from app.web import render

router = APIRouter()


@router.get("/practice")
def practice_home(request: Request, user: User = Depends(require_user)):
    return render(request, "practice_home.html")
