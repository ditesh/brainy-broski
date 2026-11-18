from fastapi import APIRouter, Depends, Request

from app.auth import require_parent
from app.models import User
from app.web import render

router = APIRouter()


@router.get("/parent")
def parent_home(request: Request, user: User = Depends(require_parent)):
    return render(request, "parent_home.html")
