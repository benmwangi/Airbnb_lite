"""
Seeds two demo login accounts so the app is testable immediately without
signing up first:
  - host@airbnblite.demo / demo12345 - linked to host_id=218745884, an
    archive-backed host with listings that have real review insights.
  - guest@airbnblite.demo / demo12345 - a plain guest account.

Both accounts are marked is_demo=True (see db.py's User model) - these
credentials are published in this file, so main.py restricts what a demo
login can mutate: /pricing/approve refuses demo sessions outright (they'd
otherwise be able to override live prices on a real archive-backed host's
listings), and /listings/{id}/price-year caps a demo session's days_ahead
so it can't trigger a large burst of external event/news API calls.

Safe to re-run - skips accounts that already exist rather than erroring,
but still sets is_demo=True on an existing row so this can retroactively
fix a database seeded before that column existed.

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
        existing_host.is_demo = True
        print("Updated host@airbnblite.demo to an archive-backed host")
    else:
        h, salt = auth.hash_password("demo12345")
        session.add(User(email="host@airbnblite.demo", password_hash=h, password_salt=salt,
                          name="Jayson", role="host", host_id=DEMO_HOST_ID, is_demo=True))
        print("Created host@airbnblite.demo (password: demo12345)")

    existing_guest = session.query(User).filter_by(email="guest@airbnblite.demo").first()
    if existing_guest:
        existing_guest.is_demo = True
        print("guest@airbnblite.demo already exists - marked is_demo")
    else:
        h, salt = auth.hash_password("demo12345")
        session.add(User(email="guest@airbnblite.demo", password_hash=h, password_salt=salt,
                          name="Jordan", role="guest", host_id=None, is_demo=True))
        print("Created guest@airbnblite.demo (password: demo12345)")

    session.commit()
    session.close()


if __name__ == "__main__":
    seed()
