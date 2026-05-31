#!/usr/bin/env python3
"""Parse local Oxford source files into a normalized seed CSV."""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Iterable


LOGGER = logging.getLogger(__name__)
OUTPUT_COLUMNS = [
    "headword",
    "normalized_headword",
    "pos",
    "cefr",
    "source_list",
]
DEFAULT_SOURCE_LIST = "Oxford"
CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
POS_MAP = {
    "n": "noun",
    "n.": "noun",
    "noun": "noun",
    "v": "verb",
    "v.": "verb",
    "verb": "verb",
    "adj": "adjective",
    "adj.": "adjective",
    "adjective": "adjective",
    "adv": "adverb",
    "adv.": "adverb",
    "adverb": "adverb",
    "pron": "pronoun",
    "pron.": "pronoun",
    "pronoun": "pronoun",
    "prep": "preposition",
    "prep.": "preposition",
    "preposition": "preposition",
    "det": "determiner",
    "det.": "determiner",
    "determiner": "determiner",
    "conj": "conjunction",
    "conj.": "conjunction",
    "conjunction": "conjunction",
    "exclam": "exclamation",
    "exclam.": "exclamation",
    "exclamation": "exclamation",
    "modal verb": "verb",
    "auxiliary verb": "verb",
    "phrasal verb": "verb",
}
TEXT_PATTERN = re.compile(
    r"^(?P<headword>.+?)\s+(?P<pos>[A-Za-z. ]+?)\s+(?P<cefr>A1|A2|B1|B2|C1|C2)$"
)


class ParseError(ValueError):
    """Raised when an input row cannot be parsed."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Oxford source data into a normalized CSV."
    )
    parser.add_argument(
        "--input",
        required=True,
        nargs="+",
        help="One or more Oxford source files.",
    )
    parser.add_argument(
        "--output",
        default="data_processed/oxford5000.csv",
        help="Path to the output CSV file.",
    )
    parser.add_argument(
        "--source-list",
        default=DEFAULT_SOURCE_LIST,
        help="Fallback source_list value when it cannot be inferred from the file name.",
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


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_headword(value: str) -> str:
    return normalize_text(value).lower()


def normalize_pos(value: str) -> str:
    normalized = normalize_text(value).lower().rstrip(":")
    normalized = normalized.replace("/", " / ")
    normalized = " ".join(normalized.split())
    if normalized in POS_MAP:
        return POS_MAP[normalized]
    cleaned = normalized.replace(".", "")
    if cleaned in POS_MAP:
        return POS_MAP[cleaned]
    return normalized


def normalize_cefr(value: str) -> str:
    normalized = normalize_text(value).upper()
    if normalized not in CEFR_LEVELS:
        raise ParseError(f"Unsupported CEFR level: {value!r}")
    return normalized


def make_record(
    headword: str,
    pos: str,
    cefr: str,
    source_list: str,
) -> dict[str, str]:
    clean_headword = normalize_text(headword)
    if not clean_headword:
        raise ParseError("Missing headword")

    clean_pos = normalize_pos(pos)
    clean_cefr = normalize_cefr(cefr)

    return {
        "headword": clean_headword,
        "normalized_headword": normalize_headword(clean_headword),
        "pos": clean_pos,
        "cefr": clean_cefr,
        "source_list": source_list,
    }


def sniff_delimiter(sample: str) -> str | None:
    if "\t" in sample:
        return "\t"
    if "," in sample:
        return ","
    return None


def infer_source_list(input_path: Path, fallback: str) -> str:
    name = input_path.name.lower()
    if "3000" in name:
        return "Oxford 3000"
    if "5000" in name:
        return "Oxford 5000"
    return fallback


def load_records(input_path: Path, source_list: str) -> list[dict[str, str]]:
    sample = input_path.read_text(encoding="utf-8-sig", errors="replace")
    delimiter = sniff_delimiter(sample[:4096])
    if delimiter:
        return list(parse_delimited_text(sample, delimiter, source_list))
    return list(parse_plain_text(sample.splitlines(), source_list))


def merge_records(all_records: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[tuple[str, str], dict[str, str]] = {}

    for record in all_records:
        key = (record["normalized_headword"], record["pos"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(record)
            continue

        merged_sources = split_source_list(existing["source_list"]) | split_source_list(
            record["source_list"]
        )
        existing["source_list"] = "; ".join(sorted(merged_sources))

        if existing["cefr"] != record["cefr"]:
            LOGGER.warning(
                "Conflicting CEFR for %s (%s): keeping %s, skipping %s",
                existing["headword"],
                existing["pos"],
                existing["cefr"],
                record["cefr"],
            )

    return list(merged.values())


def split_source_list(value: str) -> set[str]:
    return {part.strip() for part in value.split(";") if part.strip()}


def parse_delimited_text(
    text: str,
    delimiter: str,
    source_list: str,
) -> Iterable[dict[str, str]]:
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    if not rows:
        return []

    header = [normalize_text(cell).lower() for cell in rows[0]]
    if is_header_row(header):
        yield from parse_tabular_rows(rows[1:], header, source_list)
        return

    if delimiter == "\t" and all(len(row) >= 3 for row in rows):
        for row_number, row in enumerate(rows, start=1):
            try:
                yield make_record(row[0], row[1], row[2], source_list)
            except ParseError as exc:
                raise ParseError(f"Line {row_number}: {exc}") from exc
        return

    raise ParseError(
        "Could not recognize delimited input. Expected header row or tab-separated headword/pos/cefr columns."
    )


def is_header_row(header: list[str]) -> bool:
    return any(
        column in header
        for column in (
            "headword",
            "word",
            "lemma",
            "pos",
            "part of speech",
            "part_of_speech",
            "cefr",
            "level",
        )
    )


def parse_tabular_rows(
    rows: list[list[str]],
    header: list[str],
    source_list: str,
) -> Iterable[dict[str, str]]:
    column_map = map_columns(header)

    for row_number, row in enumerate(rows, start=2):
        if not row or not any(cell.strip() for cell in row):
            continue

        try:
            headword = get_required_cell(row, column_map["headword"], "headword")
            pos = get_required_cell(row, column_map["pos"], "pos")
            cefr = get_required_cell(row, column_map["cefr"], "cefr")
            yield make_record(headword, pos, cefr, source_list)
        except ParseError as exc:
            raise ParseError(f"Line {row_number}: {exc}") from exc


def map_columns(header: list[str]) -> dict[str, int]:
    aliases = {
        "headword": {"headword", "word", "lemma"},
        "pos": {"pos", "part of speech", "part_of_speech"},
        "cefr": {"cefr", "level"},
    }
    mapping: dict[str, int] = {}

    for field_name, options in aliases.items():
        for index, column_name in enumerate(header):
            if column_name in options:
                mapping[field_name] = index
                break
        else:
            raise ParseError(f"Missing required column in header: {field_name}")

    return mapping


def get_required_cell(row: list[str], index: int, field_name: str) -> str:
    if index >= len(row):
        raise ParseError(f"Missing value for {field_name}")
    value = row[index].strip()
    if not value:
        raise ParseError(f"Empty value for {field_name}")
    return value


def parse_plain_text(
    lines: Iterable[str],
    source_list: str,
) -> Iterable[dict[str, str]]:
    for line_number, raw_line in enumerate(lines, start=1):
        line = normalize_text(raw_line)
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("\t")]
        if len(parts) >= 3:
            try:
                yield make_record(parts[0], parts[1], parts[2], source_list)
                continue
            except ParseError as exc:
                raise ParseError(f"Line {line_number}: {exc}") from exc

        match = TEXT_PATTERN.match(line)
        if not match:
            raise ParseError(
                f"Line {line_number}: unsupported format {raw_line!r}. "
                "Expected 'headword<TAB>pos<TAB>cefr' or 'headword pos cefr'."
            )

        yield make_record(
            match.group("headword"),
            match.group("pos"),
            match.group("cefr"),
            source_list,
        )


def write_csv(records: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    input_paths = [Path(value) for value in args.input]
    output_path = Path(args.output)

    LOGGER.info("Parsing Oxford source data")
    LOGGER.info("Inputs: %s", ", ".join(str(path) for path in input_paths))
    LOGGER.info("Output: %s", output_path)

    missing_paths = [path for path in input_paths if not path.exists()]
    if missing_paths:
        for path in missing_paths:
            LOGGER.error("Input file does not exist: %s", path)
        return 1

    try:
        all_records: list[dict[str, str]] = []
        for input_path in input_paths:
            source_list = infer_source_list(input_path, args.source_list)
            records = load_records(input_path, source_list)
            LOGGER.info("Parsed %d records from %s", len(records), input_path)
            all_records.extend(records)
        records = merge_records(all_records)
    except (OSError, ParseError, csv.Error) as exc:
        LOGGER.error("Failed to parse Oxford input: %s", exc)
        return 1

    if not records:
        LOGGER.error("No records parsed from input files")
        return 1

    write_csv(records, output_path)
    LOGGER.info("Wrote %d merged records", len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
