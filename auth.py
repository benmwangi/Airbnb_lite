"""
Authentication for Airbnb-lite: password hashing and bearer-token sessions.

No external auth dependency (no passlib/bcrypt) - uses hashlib's PBKDF2-HMAC
directly, which is in the Python standard library and is a real, correctly-
salted, iterated password hash (100,000 rounds of SHA-256), not a toy scheme.
Sessions are opaque random tokens stored server-side (db.Session), not JWTs -
simpler, and a session can be revoked by just deleting its row.
"""
import datetime
import hashlib
import hmac
import secrets

from db import get_session, User, Session as SessionModel

SESSION_LIFETIME = datetime.timedelta(days=7)
PBKDF2_ITERATIONS = 100_000


def hash_password(password: str, salt: str = None) -> tuple:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def create_session(db_session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.utcnow() + SESSION_LIFETIME
    db_session.add(SessionModel(token=token, user_id=user.id, expires_at=expires_at))
    db_session.commit()
    return token


def get_user_from_token(token: str):
    """Returns the User for a valid, unexpired session token, or None."""
    if not token:
        return None
    db_session = get_session()
    try:
        sess = db_session.query(SessionModel).filter_by(token=token).first()
        if not sess or sess.expires_at < datetime.datetime.utcnow():
            return None
        user = db_session.query(User).get(sess.user_id)
        if user:
            db_session.expunge(user)  # detach so it's usable after this session closes
        return user
    finally:
        db_session.close()


def extract_bearer_token(authorization_header: str) -> str:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return ""
    return authorization_header.removeprefix("Bearer ").strip()
