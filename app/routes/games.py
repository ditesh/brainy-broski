"""Brain-break games: the games page, starting a round he has earned, and recording how it went."""
import random

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.games import GAMES, make_target, nim_pile, record, rounds_left
from app.models import GamePlay, Role, User
from app.web import render

router = APIRouter()


def _game(name: str) -> dict:
    if name not in GAMES:
        raise HTTPException(status_code=404)
    return GAMES[name]


def _opponent(db: Session, user: User):
    from app.routes.practice import _buddy
    return _buddy(db, user)


def _puzzle(game: str) -> dict:
    rng = random.Random()
    if game == "nim":
        return {"pile": nim_pile(rng)}
    nums, target, answer = make_target(rng)
    return {"numbers": nums, "target": target, "answer": answer}


def _play_page(request: Request, db: Session, user: User, game: str, puzzle: dict, round_id: int | None):
    return render(request, f"games/{game}.html", game=game, info=GAMES[game], puzzle=puzzle, round_id=round_id,
                  buddy=_opponent(db, user), rounds=rounds_left(db, user, request.app.state.settings.timezone)
                  if user.role == Role.child else None)


@router.get("/games")
def games_home(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    child = user.role == Role.child
    return render(request, "games/index.html", games=GAMES,
                  rounds=rounds_left(db, user, request.app.state.settings.timezone) if child else None,
                  wins=record(db, user) if child else None)


@router.post("/games/{game}/play")
def start_round(game: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _game(game)
    if user.role != Role.child:
        return RedirectResponse(f"/games/{game}/preview", status_code=303)
    if rounds_left(db, user, request.app.state.settings.timezone).left <= 0:
        return RedirectResponse("/games", status_code=303)
    play = GamePlay(user_id=user.id, game=game, puzzle=_puzzle(game))
    db.add(play)
    db.commit()
    return RedirectResponse(f"/games/{game}/{play.id}", status_code=303)


@router.get("/games/{game}/preview")
def preview(game: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _game(game)
    if user.role == Role.child:
        raise HTTPException(status_code=403)
    return _play_page(request, db, user, game, _puzzle(game), None)


def _own_play(db: Session, user: User, play_id: int) -> GamePlay:
    play = db.get(GamePlay, play_id)
    if play is None or play.user_id != user.id:
        raise HTTPException(status_code=404)
    return play


@router.get("/games/{game}/{play_id}")
def play_round(game: str, play_id: int, request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    _game(game)
    play = _own_play(db, user, play_id)
    if play.game != game:
        raise HTTPException(status_code=404)
    if play.won is not None:  # finished: back to the games page rather than a free replay
        return RedirectResponse("/games", status_code=303)
    return _play_page(request, db, user, game, play.puzzle or _puzzle(game), play.id)


@router.post("/games/plays/{play_id}/result")
def round_result(play_id: int, won: str = Form(...), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    play = _own_play(db, user, play_id)
    if play.won is not None:
        raise HTTPException(status_code=409)
    play.won = won == "1"
    db.commit()
    return Response(status_code=204)
