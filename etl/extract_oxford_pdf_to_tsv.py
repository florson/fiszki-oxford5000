#!/usr/bin/env python3
"""Extract Oxford word list entries from a PDF into a simple TSV file."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


LOGGER = logging.getLogger(__name__)
TSV_COLUMNS = ("headword", "pos", "cefr")
CEFR_PATTERN = r"(?:A1|A2|B1|B2|C1|C2)"
POS_LABELS = (
    "indefinite article",
    "definite article",
    "infinitive marker",
    "auxiliary v.",
    "auxiliary v",
    "modal v.",
    "modal v",
    "number",
    "exclam.",
    "exclam",
    "pron.",
    "pron",
    "prep.",
    "prep",
    "conj.",
    "conj",
    "det.",
    "det",
    "adv.",
    "adv",
    "adj.",
    "adj",
    "n.",
    "n",
    "v.",
    "v",
)
POS_ALIASES = {
    "n": "n.",
    "n.": "n.",
    "v": "v.",
    "v.": "v.",
    "adj": "adj.",
    "adj.": "adj.",
    "adv": "adv.",
    "adv.": "adv.",
    "prep": "prep.",
    "prep.": "prep.",
    "conj": "conj.",
    "conj.": "conj.",
    "det": "det.",
    "det.": "det.",
    "pron": "pron.",
    "pron.": "pron.",
    "exclam": "exclam.",
    "exclam.": "exclam.",
    "auxiliary v": "auxiliary v.",
    "auxiliary v.": "auxiliary v.",
    "modal v": "modal v.",
    "modal v.": "modal v.",
    "indefinite article": "indefinite article",
    "definite article": "definite article",
    "infinitive marker": "infinitive marker",
    "number": "number",
}
POS_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(POS_LABELS, key=len, reverse=True)
)
POS_START_RE = re.compile(rf"\b(?P<pos>{POS_LABEL_PATTERN})(?=$|[\s,/])", re.IGNORECASE)
POS_SEGMENT_RE = re.compile(
    rf"^(?P<pos>{POS_LABEL_PATTERN})\s*(?P<cefr>{CEFR_PATTERN})?$",
    re.IGNORECASE,
)
CEFR_RE = re.compile(rf"^{CEFR_PATTERN}$", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\d+\s*/\s*\d+$")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MISSING_SPACE_BEFORE_CEFR_RE = re.compile(
    rf"(?i)\b(?P<pos>auxiliary v\.|modal v\.|n\.|v\.|adj\.|adv\.|prep\.|conj\.|det\.|pron\.|exclam\.)(?P<cefr>{CEFR_PATTERN})\b"
)
SLASH_POS_RE = re.compile(
    rf"(?P<left>{POS_LABEL_PATTERN})(?=$|[\s,/])\s*/\s*(?P<right>{POS_LABEL_PATTERN})(?=$|[\s,/])",
    re.IGNORECASE,
)


class ParseError(ValueError):
    """Raised when a PDF line cannot be parsed into headword/POS/CEFR rows."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Oxford PDF entries into a headword/POS/CEFR TSV file."
    )
    parser.add_argument("--input", required=True, help="Path to the Oxford PDF file.")
    parser.add_argument(
        "--output",
        help="Path to the output TSV file. Defaults to the input path with .tsv suffix.",
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="Write a header row: headword, pos, cefr.",
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


def normalize_spaces(value: str) -> str:
    return " ".join(value.strip().split())


def canonicalize_pos(value: str) -> str:
    key = normalize_spaces(value).lower()
    canonical = POS_ALIASES.get(key)
    if canonical is None:
        raise ParseError(f"Unsupported part of speech: {value!r}")
    return canonical


def swift_source_for_pdf(pdf_path: Path) -> str:
    return textwrap.dedent(
        f"""
        import Foundation
        import PDFKit

        let url = URL(fileURLWithPath: "{pdf_path}")
        guard let document = PDFDocument(url: url) else {{
            fputs("Could not open PDF\\n", stderr)
            exit(1)
        }}

        for pageIndex in 0..<document.pageCount {{
            if let text = document.page(at: pageIndex)?.string {{
                print(text)
            }}
        }}
        """
    )


def extract_pdf_text(pdf_path: Path) -> str:
    cache_dir = Path(tempfile.gettempdir()) / "swift-module-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["SWIFT_MODULECACHE_PATH"] = str(cache_dir)
    env["CLANG_MODULE_CACHE_PATH"] = str(cache_dir)

    try:
        result = subprocess.run(
            ["swift", "-"],
            input=swift_source_for_pdf(pdf_path),
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Swift is required to extract text from PDF on macOS.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or "unknown Swift/PDFKit error"
        raise RuntimeError(f"Swift/PDFKit extraction failed: {stderr}") from exc

    return result.stdout


def clean_lines(pdf_text: str) -> list[str]:
    text = CONTROL_CHAR_RE.sub(" ", pdf_text)
    for token in ("© Oxford University Press", "The Oxford 5000™", "The Oxford 5000"):
        text = text.replace(token, "\n")

    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        line = normalize_spaces(raw_line)
        if not line:
            continue
        if PAGE_NUMBER_RE.fullmatch(line):
            continue
        line = MISSING_SPACE_BEFORE_CEFR_RE.sub(r"\g<pos> \g<cefr>", line)
        normalized_lines.append(expand_slash_pos(line))

    merged_lines: list[str] = []
    for line in normalized_lines:
        if not merged_lines:
            merged_lines.append(line)
            continue

        previous = merged_lines[-1]
        if previous.endswith(",") or previous.endswith("/"):
            merged_lines[-1] = f"{previous} {line}"
            continue

        if POS_START_RE.match(line):
            merged_lines[-1] = f"{previous} {line}"
            continue

        merged_lines.append(line)

    return merged_lines


def expand_slash_pos(value: str) -> str:
    expanded = value
    while True:
        next_value = SLASH_POS_RE.sub(r"\g<left>, \g<right>", expanded)
        if next_value == expanded:
            return expanded
        expanded = next_value


def parse_entry_line(line: str) -> list[tuple[str, str, str]]:
    if not CEFR_RE.search(line) and not re.search(rf"\b{CEFR_PATTERN}\b", line):
        return []

    for first_pos_match in POS_START_RE.finditer(line):
        headword = normalize_spaces(line[: first_pos_match.start()])
        if not headword:
            continue

        remainder = normalize_spaces(line[first_pos_match.start() :])
        parts = [normalize_spaces(part) for part in remainder.split(",") if part.strip()]
        if not parts:
            continue

        pending_pos: list[str] = []
        parsed_pairs: list[tuple[str, str]] = []

        try:
            for part in parts:
                if CEFR_RE.fullmatch(part):
                    if not pending_pos:
                        raise ParseError(f"CEFR without POS in line: {line!r}")
                    level = part.upper()
                    parsed_pairs.extend((pos, level) for pos in pending_pos)
                    pending_pos.clear()
                    continue

                match = POS_SEGMENT_RE.fullmatch(part)
                if match is None:
                    raise ParseError(
                        f"Unsupported POS/CEFR segment {part!r} in line: {line!r}"
                    )

                pos = canonicalize_pos(match.group("pos"))
                level = match.group("cefr")

                if level is None:
                    pending_pos.append(pos)
                    continue

                normalized_level = level.upper()
                if pending_pos:
                    parsed_pairs.extend((pending, normalized_level) for pending in pending_pos)
                    pending_pos.clear()
                parsed_pairs.append((pos, normalized_level))
        except ParseError:
            continue

        if pending_pos:
            continue

        return [(headword, pos, cefr) for pos, cefr in parsed_pairs]

    return []


def extract_records(pdf_path: Path) -> list[tuple[str, str, str]]:
    pdf_text = extract_pdf_text(pdf_path)
    records: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for line in clean_lines(pdf_text):
        entries = parse_entry_line(line)
        for entry in entries:
            if entry not in seen:
                seen.add(entry)
                records.append(entry)

    return records


def write_tsv(
    records: list[tuple[str, str, str]],
    output_path: Path,
    *,
    include_header: bool,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        if include_header:
            writer.writerow(TSV_COLUMNS)
        writer.writerows(records)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".tsv")

    LOGGER.info("Extracting Oxford entries from PDF")
    LOGGER.info("Input: %s", input_path)
    LOGGER.info("Output: %s", output_path)

    if not input_path.exists():
        LOGGER.error("Input file does not exist: %s", input_path)
        return 1

    try:
        records = extract_records(input_path)
    except (OSError, RuntimeError, ParseError) as exc:
        LOGGER.error("Failed to extract %s: %s", input_path, exc)
        return 1

    if not records:
        LOGGER.error("No records extracted from input file: %s", input_path)
        return 1

    write_tsv(records, output_path, include_header=args.header)
    LOGGER.info("Extracted %d rows", len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
