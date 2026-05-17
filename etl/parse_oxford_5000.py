#!/usr/bin/env python3
"""Parse a local Oxford 5000 source file into a normalized CSV."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Oxford 5000 source data into a normalized CSV."
    )
    parser.add_argument("--input", required=True, help="Path to the Oxford source file.")
    parser.add_argument(
        "--output",
        default="data_processed/oxford5000.csv",
        help="Path to the output CSV file.",
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
    output_path = Path(args.output)

    LOGGER.info("Oxford parser skeleton")
    LOGGER.info("Input: %s", input_path)
    LOGGER.info("Output: %s", output_path)

    if not input_path.exists():
        LOGGER.error("Input file does not exist: %s", input_path)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.warning("Parsing logic is not implemented yet. This is a milestone 1 skeleton.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
