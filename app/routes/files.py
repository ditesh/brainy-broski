from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.auth import require_user
from app.models import Role, User

router = APIRouter()


@router.get("/files/{path:path}")
def get_file(path: str, request: Request, user: User = Depends(require_user)):
    root = request.app.state.settings.data_dir.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(404)
    rel = target.relative_to(root).parts
    if user.role != Role.parent:
        allowed = rel[0] == "crops" or (rel[0] == "photos" and len(rel) > 1 and rel[1] == str(user.id))
        if not allowed:
            raise HTTPException(403)
    return FileResponse(target, headers={"Cache-Control": "private, max-age=3600"})
