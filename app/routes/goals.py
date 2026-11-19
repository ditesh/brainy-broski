"""A child sets their own weekly goal."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import current_user
from app.daily import local_today
from app.db import get_db
from app.goals import GOAL_MAX, GOAL_MIN, set_goal
from app.models import Role, User

router = APIRouter()
GOAL_ERROR = f"Pick a number from {GOAL_MIN} to {GOAL_MAX}."


def _safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/practice"


@router.post("/goal")
def save_goal(request: Request, target: str = Form(""), next: str = Form("/practice"),
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != Role.child:
        raise HTTPException(status_code=403, detail="Goals are for kids")
    dest = _safe_next(next)
    value = target.strip()
    if not value.isdigit() or not GOAL_MIN <= int(value) <= GOAL_MAX:
        if dest == "/account":
            from app.routes.account import _page
            return _page(request, user, 400, goal_error=GOAL_ERROR)
        from app.routes.practice import render_home
        return render_home(request, db, user, status_code=400, goal_error=GOAL_ERROR)
    set_goal(db, user, int(value), local_today(request.app.state.settings.timezone))
    return RedirectResponse(dest, status_code=303)
