#!/usr/bin/env python3
"""Build the SQLite seed database from enriched CSV data."""

from __future__ import annotations

import argparse
import csv
import logging
import sqlite3
import sys
from pathlib import Path


LOGGER = logging.getLogger(__name__)
DEFAULT_INPUT = "data_processed/entries_enriched.csv"
DEFAULT_SCHEMA = "db/schema.sql"
DEFAULT_DB = "db/app.db"
CSV_COLUMNS = [
    "headword",
    "normalized_headword",
    "pos",
    "cefr",
    "definition_en",
    "example_en",
    "ipa",
    "audio_url",
    "source_list",
    "source_definition",
    "match_quality",
    "notes",
]
INSERT_SQL = """
    INSERT INTO dictionary_entries (
        headword,
        normalized_headword,
        pos,
        cefr,
        definition_en,
        example_en,
        ipa,
        audio_url,
        source_list,
        source_definition,
        match_quality,
        notes
    ) VALUES (
        :headword,
        :normalized_headword,
        :pos,
        :cefr,
        :definition_en,
        :example_en,
        :ipa,
        :audio_url,
        :source_list,
        :source_definition,
        :match_quality,
        :notes
    )
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the SQLite seed database from enriched CSV data."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"Path to the enriched CSV input. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA,
        help=f"Path to the SQLite schema file. Default: {DEFAULT_SCHEMA}",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to the output SQLite database file. Default: {DEFAULT_DB}",
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


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def load_rows(input_path: Path) -> list[dict[str, str]]:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in CSV_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                "Input CSV is missing required columns: " + ", ".join(sorted(missing))
            )

        rows: list[dict[str, str]] = []
        for row_number, raw_row in enumerate(reader, start=2):
            row = {column: normalize_text(raw_row.get(column, "")) for column in CSV_COLUMNS}
            if not row["headword"] or not row["normalized_headword"]:
                raise ValueError(f"Input CSV line {row_number} is missing headword data.")
            rows.append(row)

    if not rows:
        raise ValueError(f"Input CSV has no data rows: {input_path}")

    return rows


def read_schema(schema_path: Path) -> str:
    schema_sql = schema_path.read_text(encoding="utf-8")
    if not schema_sql.strip():
        raise ValueError(f"Schema file is empty: {schema_path}")
    return schema_sql


def build_database(db_path: Path, schema_sql: str, rows: list[dict[str, str]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema_sql)
        connection.executemany(INSERT_SQL, rows)
        connection.commit()


def count_rows(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM dictionary_entries").fetchone()
    return int(row[0]) if row else 0


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    input_path = Path(args.input)
    schema_path = Path(args.schema)
    db_path = Path(args.db)

    LOGGER.info("Input CSV: %s", input_path)
    LOGGER.info("Schema SQL: %s", schema_path)
    LOGGER.info("Output DB: %s", db_path)

    missing = [str(path) for path in (input_path, schema_path) if not path.exists()]
    if missing:
        for path in missing:
            LOGGER.error("Required input does not exist: %s", path)
        return 1

    try:
        rows = load_rows(input_path)
        schema_sql = read_schema(schema_path)
        build_database(db_path, schema_sql, rows)
        inserted_count = count_rows(db_path)
    except (OSError, sqlite3.DatabaseError, ValueError, csv.Error) as exc:
        LOGGER.error("Failed to build SQLite database: %s", exc)
        return 1

    LOGGER.info("Inserted %d rows into dictionary_entries", inserted_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
