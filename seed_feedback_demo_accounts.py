"""
Seeds two additional demo host accounts, chosen specifically to illustrate
the review-insights feature's range - both hosts genuinely receive real
review-based recommendations, contrasting in volume/severity rather than one
showing recommendations and the other showing none (which could otherwise
look like the feature simply hadn't run for that account):

  - positivehost@airbnblite.demo - host_id=344804377, a real Maven-dataset
    host who owns 2 real listings (Cape Town #647, Istanbul #1340). Mostly
    glowing fixture reviews, but one listing (#647) surfaces a single real,
    minor recommendation (value_for_price) - a realistic "great host, one
    small thing to improve" case. The other listing (#1340) genuinely has
    zero themes - confirmed processed and clean, not just unprocessed.

  - negativehost@airbnblite.demo - host_id=33174397, a real single-listing
    host (Paris #2491). Fixture reviews surface two real, more significant
    themes: cleanliness and missing_amenities.

Both host_ids are real, existing hosts in the dataset - not fabricated - so
their "My Listings" pages show genuine portfolio data, not empty shells.

Run review_insights_loader.py against fixture_two_hosts.csv BEFORE this
script if you want the recommendations to be visible immediately after
logging in; otherwise both accounts will show "no recommendations yet" until
you do. Safe to re-run - skips accounts that already exist.

Usage:
    python seed_feedback_demo_accounts.py
"""
from db import init_db, get_session, User
import auth

ACCOUNTS = [
    {
        "email": "positivehost@airbnblite.demo",
        "name": "Naledi",
        "host_id": 344804377,  # real host - Cape Town #647, Istanbul #1340
    },
    {
        "email": "negativehost@airbnblite.demo",
        "name": "Étienne",
        "host_id": 33174397,  # real host - Paris #2491
    },
]


def seed():
    init_db()
    session = get_session()

    for acct in ACCOUNTS:
        if session.query(User).filter_by(email=acct["email"]).first():
            print(f"{acct['email']} already exists - skipped")
            continue
        h, salt = auth.hash_password("demo12345")
        session.add(User(
            email=acct["email"], password_hash=h, password_salt=salt,
            name=acct["name"], role="host", host_id=acct["host_id"],
        ))
        print(f"Created {acct['email']} (password: demo12345, host_id={acct['host_id']})")

    session.commit()
    session.close()


if __name__ == "__main__":
    seed()
