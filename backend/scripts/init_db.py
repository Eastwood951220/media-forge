#!/usr/bin/env python3
"""Initialize database: create tables and default admin user.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --username admin --password admin123
"""

import argparse
import logging
import sys

from backend.app.core.security import get_password_hash
from backend.app.models.user import User
from backend.app.repositories.user import UserRepository
from shared.database.models.base import Base
from shared.database.session import connect_postgres, get_session_factory

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    logger.info("Connecting to PostgreSQL...")
    connect_postgres()

    factory = get_session_factory()
    session = factory()

    try:
        # Create all tables
        logger.info("Creating tables...")
        Base.metadata.create_all(bind=session.get_bind())
        logger.info("Tables created.")

        # Create admin user if not exists
        user_repo = UserRepository(session)

        if user_repo.username_exists(args.username):
            logger.info("Admin user '%s' already exists. Skipping.", args.username)
            return

        user = User(
            username=args.username,
            hashed_password=get_password_hash(args.password),
            role="admin",
        )
        session.add(user)
        session.commit()
        logger.info("Admin user created: %s", args.username)
    except Exception:
        session.rollback()
        logger.exception("Failed to initialize database.")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
