"""
Copies every row from a SQLite airbnb_lite.db into Postgres, table by table,
using the same SQLAlchemy models - so the schema is guaranteed identical on
both sides. Run this once when moving from the local demo to Postgres.

Usage:
    export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/airbnb_lite
    python migrate_sqlite_to_postgres.py --sqlite-path airbnb_lite.db
"""
import argparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import Base, Market, Listing, CalendarDay, ExternalSignalCache, engine as pg_engine

TABLES_IN_ORDER = [Market, Listing, CalendarDay, ExternalSignalCache]  # parents before children


def migrate(sqlite_path: str):
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    print(f"Creating schema on Postgres ({pg_engine.url})...")
    Base.metadata.create_all(pg_engine)

    src = SqliteSession()
    dst = PgSession()

    for model in TABLES_IN_ORDER:
        rows = src.query(model).all()
        print(f"{model.__tablename__:20s}: copying {len(rows)} rows")
        for row in rows:
            src.expunge(row)  # detach from the SQLite session
            dst.merge(row)    # insert-or-update on the Postgres session, preserving primary keys
        dst.commit()

    src.close()
    dst.close()
    print("Migration complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-path", default="airbnb_lite.db")
    args = parser.parse_args()
    migrate(args.sqlite_path)
