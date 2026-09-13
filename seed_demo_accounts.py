"""
Seeds two demo login accounts so the app is testable immediately without
signing up first:
  - host@airbnblite.demo / demo12345 - linked to host_id=218745884, an
    archive-backed host with listings that have real review insights.
  - guest@airbnblite.demo / demo12345 - a plain guest account.

Safe to re-run - skips accounts that already exist rather than erroring.

Usage:
    python seed_demo_accounts.py
"""
from db import init_db, get_session, User
import auth

DEMO_HOST_ID = 218745884  # archive-backed host with real review insights


def seed():
    init_db()
    session = get_session()

    existing_host = session.query(User).filter_by(email="host@airbnblite.demo").first()
    if existing_host:
        existing_host.name = "Jayson"
        existing_host.host_id = DEMO_HOST_ID
        print("Updated host@airbnblite.demo to an archive-backed host")
    else:
        h, salt = auth.hash_password("demo12345")
        session.add(User(email="host@airbnblite.demo", password_hash=h, password_salt=salt,
                          name="Jayson", role="host", host_id=DEMO_HOST_ID))
        print("Created host@airbnblite.demo (password: demo12345)")

    if not session.query(User).filter_by(email="guest@airbnblite.demo").first():
        h, salt = auth.hash_password("demo12345")
        session.add(User(email="guest@airbnblite.demo", password_hash=h, password_salt=salt,
                          name="Jordan", role="guest", host_id=None))
        print("Created guest@airbnblite.demo (password: demo12345)")
    else:
        print("guest@airbnblite.demo already exists - skipped")

    session.commit()
    session.close()


if __name__ == "__main__":
    seed()
