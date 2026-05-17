#!/usr/bin/env python3
"""Enrich Oxford seed words with Kaikki / Wiktionary data."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich Oxford entries with Kaikki / Wiktionary data."
    )
    parser.add_argument(
        "--oxford",
        required=True,
        help="Path to data_processed/oxford5000.csv.",
    )
    parser.add_argument(
        "--kaikki",
        required=True,
        help="Path to a Kaikki JSONL dump.",
    )
    parser.add_argument(
        "--output",
        default="data_processed/entries_enriched.csv",
        help="Path to the enriched CSV output.",
    )
    parser.add_argument(
        "--report",
        default="data_processed/match_report.json",
        help="Path to the match quality report.",
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

    oxford_path = Path(args.oxford)
    kaikki_path = Path(args.kaikki)
    output_path = Path(args.output)
    report_path = Path(args.report)

    LOGGER.info("Kaikki enrichment skeleton")
    LOGGER.info("Oxford CSV: %s", oxford_path)
    LOGGER.info("Kaikki dump: %s", kaikki_path)
    LOGGER.info("Output CSV: %s", output_path)
    LOGGER.info("Report JSON: %s", report_path)

    missing = [str(path) for path in (oxford_path, kaikki_path) if not path.exists()]
    if missing:
        for path in missing:
            LOGGER.error("Required input does not exist: %s", path)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.warning("Enrichment logic is not implemented yet. This is a milestone 1 skeleton.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
