#!/usr/bin/env python3
"""Initialize database tables and default data.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --username admin --password admin123
"""

import argparse
import logging
import sys

from backend.app.modules.init.database_bootstrap import (
    create_application_tables,
    seed_default_admin_user,
)
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
        engine = session.get_bind()
        logger.info("Creating tables...")
        create_application_tables(engine)
        logger.info("Tables created.")

        seed_default_admin_user(
            engine,
            username=args.username,
            password=args.password,
        )
    except Exception:
        session.rollback()
        logger.exception("Failed to initialize database.")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
