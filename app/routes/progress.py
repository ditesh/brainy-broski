from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_parent, require_user
from app.db import get_db
from app.models import Label, Response, Role, User
from app.progress import (effective_label, miss_breakdown_by_week, paper_history, recent_misses,
                          technique_table)
from app.routes.feedback import LABEL_TEXT
from app.web import render

router = APIRouter()
LABEL_ORDER = [Label.careless_self_corrected, Label.careless, Label.technique, Label.unsure]


def _week_chart(weeks) -> dict:
    max_total = max([sum(d.values()) for _, d in weeks] + [1])
    bars = []
    for i, (start, d) in enumerate(weeks):
        y = 120.0
        segs = []
        for lab in LABEL_ORDER:
            n = d.get(lab, 0)
            if n:
                h = 110.0 * n / max_total
                y -= h
                segs.append({"label": lab.value, "y": round(y, 1), "h": round(h, 1), "n": n})
        bars.append({"x": 8 + i * 40, "start": start, "segs": segs, "total": sum(d.values())})
    return {"bars": bars, "width": 8 + len(weeks) * 40}


@router.get("/progress")
def progress_page(request: Request, user: int | None = None, viewer: User = Depends(require_user),
                  db: Session = Depends(get_db)):
    children = db.query(User).filter(User.role == Role.child).order_by(User.id).all()
    if viewer.role == Role.parent:
        target = next((c for c in children if c.id == user), children[0] if children else None)
    else:
        target = viewer
    if target is None:
        return render(request, "progress.html", target=None, children=children)
    weeks = miss_breakdown_by_week(db, target, weeks=8)
    return render(request, "progress.html", target=target, children=children, chart=_week_chart(weeks),
                  techniques=technique_table(db, target), history=paper_history(db, target),
                  misses=recent_misses(db, target), effective_label=effective_label,
                  label_text=LABEL_TEXT, labels=LABEL_ORDER, is_parent=viewer.role == Role.parent)


@router.post("/parent/responses/{response_id}/override")
def override(response_id: int, request: Request, label: str = Form(""), user: User = Depends(require_parent),
             db: Session = Depends(get_db)):
    r = db.get(Response, response_id)
    if r is None:
        raise HTTPException(404)
    r.parent_override = Label(label) if label else None
    db.commit()
    back = request.headers.get("referer") or f"/progress?user={r.attempt.user_id}"
    return RedirectResponse(back, status_code=303)
