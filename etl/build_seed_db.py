#!/usr/bin/env python3
"""Build the SQLite seed database from enriched CSV data."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the SQLite seed database from enriched CSV data."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to data_processed/entries_enriched.csv.",
    )
    parser.add_argument(
        "--schema",
        default="db/schema.sql",
        help="Path to the SQLite schema file.",
    )
    parser.add_argument(
        "--db",
        default="db/app.db",
        help="Path to the output SQLite database file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level, for example DEBUG, INFO, WARNING.",
    )
    return parser.parse_args()


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    input_path = Path(args.input)
    schema_path = Path(args.schema)
    db_path = Path(args.db)

    LOGGER.info("SQLite builder skeleton")
    LOGGER.info("Input CSV: %s", input_path)
    LOGGER.info("Schema SQL: %s", schema_path)
    LOGGER.info("Output DB: %s", db_path)

    missing = [str(path) for path in (input_path, schema_path) if not path.exists()]
    if missing:
        for path in missing:
            LOGGER.error("Required input does not exist: %s", path)
        return 1

    db_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.warning("Database build logic is not implemented yet. This is a milestone 1 skeleton.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
