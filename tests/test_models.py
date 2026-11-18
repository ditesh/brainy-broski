from app.auth import create_user, verify_password
from app.models import Role, Technique
from app.techniques import TECHNIQUES, seed_techniques


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_create_user_and_hash(db):
    u = create_user(db, "dad", "Dad", Role.parent, "pw")
    assert u.password_hash != "pw" and verify_password("pw", u.password_hash)
    assert not verify_password("nope", u.password_hash)


def test_seed_techniques_idempotent(db):
    seed_techniques(db)
    seed_techniques(db)
    assert db.query(Technique).count() == len(TECHNIQUES) >= 25
