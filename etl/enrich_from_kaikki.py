#!/usr/bin/env python3
"""Enrich Oxford seed words with Kaikki / Wiktionary data."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterable, Iterator, TextIO


LOGGER = logging.getLogger(__name__)
SOURCE_DEFINITION = "Kaikki / Wiktionary"
OUTPUT_COLUMNS = [
    "headword",
    "normalized_headword",
    "pos",
    "cefr",
    "definition_en",
    "example_en",
    "ipa",
    "audio_url",
    "source_definition",
    "source_list",
    "match_quality",
    "notes",
]
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
AUDIO_FIELDS = ("audio", "mp3_url", "ogg_url", "oga_url", "wav_url", "url")
ARCHAIC_TAGS = {"archaic", "obsolete"}


class EnrichmentError(ValueError):
    """Raised when enrichment input cannot be processed."""


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
        help="Path to a Kaikki JSONL dump or a directory with JSONL files.",
    )
    parser.add_argument(
        "--output",
        default="data_processed/entries_enriched.csv",
        help="Path to the enriched CSV output.",
    )
    parser.add_argument(
        "--report",
        default="data_processed/match_report.json",
        help="Path to the match quality report JSON.",
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


def normalize_headword(value: str) -> str:
    return normalize_text(value).lower()


def normalize_pos(value: str | None) -> str:
    normalized = normalize_text(value or "").lower().rstrip(":")
    if not normalized:
        return ""
    if normalized in POS_MAP:
        return POS_MAP[normalized]
    cleaned = normalized.replace(".", "")
    if cleaned in POS_MAP:
        return POS_MAP[cleaned]
    return normalized


def load_oxford_entries(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"headword", "normalized_headword", "pos", "cefr"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise EnrichmentError(
                f"Oxford CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        entries: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            headword = normalize_text(row.get("headword", ""))
            normalized_headword = normalize_headword(
                row.get("normalized_headword") or headword
            )
            pos = normalize_pos(row.get("pos"))
            cefr = normalize_text(row.get("cefr", ""))
            source_list = normalize_text(row.get("source_list", "")) or "Oxford 5000"

            if not headword or not normalized_headword:
                raise EnrichmentError(
                    f"Oxford CSV line {row_number} is missing headword data."
                )

            entries.append(
                {
                    "headword": headword,
                    "normalized_headword": normalized_headword,
                    "pos": pos,
                    "cefr": cefr,
                    "source_list": source_list,
                }
            )

    if not entries:
        raise EnrichmentError(f"Oxford CSV has no data rows: {path}")

    return entries


def group_entries_by_headword(
    entries: list[dict[str, str]],
) -> dict[str, list[tuple[int, dict[str, str]]]]:
    grouped: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for index, entry in enumerate(entries):
        grouped.setdefault(entry["normalized_headword"], []).append((index, entry))
    return grouped


def iter_kaikki_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    if path.is_dir():
        candidates = sorted(path.glob("*.jsonl")) + sorted(path.glob("*.jsonl.gz"))
        if candidates:
            return candidates

    raise EnrichmentError(
        "Kaikki input must be a .jsonl file, a .jsonl.gz file, or a directory containing them."
    )


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_kaikki_records(paths: list[Path]) -> Iterator[tuple[Path, int, dict]]:
    for path in paths:
        LOGGER.info("Reading Kaikki file: %s", path)
        with open_text(path) as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    LOGGER.warning(
                        "Skipping invalid JSON at %s:%d: %s", path, line_number, exc
                    )
                    continue

                if not isinstance(data, dict):
                    LOGGER.warning("Skipping non-object JSON at %s:%d", path, line_number)
                    continue

                yield path, line_number, data


def is_english_entry(entry: dict) -> bool:
    lang_code = normalize_text(entry.get("lang_code", "")).lower()
    lang = normalize_text(entry.get("lang", "")).lower()
    return lang_code == "en" or lang == "english"


def first_non_empty(values: Iterable[object]) -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return ""


def normalize_tags(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()

    tags: set[str] = set()
    for value in values:
        if isinstance(value, str):
            normalized = normalize_text(value).lower()
        elif isinstance(value, dict):
            normalized = normalize_text(
                value.get("tag") or value.get("name") or value.get("value")
            ).lower()
        else:
            normalized = ""
        if normalized:
            tags.add(normalized)
    return tags


def extract_example(sense: dict) -> str:
    examples = sense.get("examples") or []
    if not isinstance(examples, list):
        return ""

    for example in examples:
        if isinstance(example, str):
            text = normalize_text(example)
            if text:
                return text
            continue

        if not isinstance(example, dict):
            continue

        text = first_non_empty(
            (
                example.get("english"),
                example.get("text"),
                example.get("example"),
            )
        )
        if text:
            return text

    return ""


def extract_best_sense(entry: dict) -> dict[str, object] | None:
    senses = entry.get("senses") or []
    if not isinstance(senses, list):
        return None

    entry_tags = normalize_tags(entry.get("tags"))
    best_result: dict[str, object] | None = None
    best_score = -1

    for sense in senses:
        if not isinstance(sense, dict):
            continue

        glosses = sense.get("glosses")
        raw_glosses = sense.get("raw_glosses")
        definition = ""
        score = 0

        if isinstance(glosses, list):
            definition = first_non_empty(glosses)
            if definition:
                score += 10

        if not definition and isinstance(raw_glosses, list):
            definition = first_non_empty(raw_glosses)
            if definition:
                score += 5

        if not definition:
            continue

        example = extract_example(sense)
        if example:
            score += 3

        tags = entry_tags | normalize_tags(sense.get("tags"))
        if tags & ARCHAIC_TAGS:
            score -= 4
        else:
            score += 1

        if score > best_score:
            best_result = {
                "definition_en": definition,
                "example_en": example,
                "tags": sorted(tags),
            }
            best_score = score

    return best_result


def extract_pronunciation(entry: dict) -> tuple[str, str]:
    ipa = ""
    audio_url = ""

    sounds = entry.get("sounds") or []
    if not isinstance(sounds, list):
        return ipa, audio_url

    for sound in sounds:
        if not isinstance(sound, dict):
            continue

        if not ipa:
            ipa = first_non_empty((sound.get("ipa"),))

        if not audio_url:
            audio_url = first_non_empty(sound.get(field) for field in AUDIO_FIELDS)

        if ipa and audio_url:
            break

    return ipa, audio_url


def build_candidate(entry: dict) -> dict[str, object] | None:
    best_sense = extract_best_sense(entry)
    if not best_sense:
        return None

    ipa, audio_url = extract_pronunciation(entry)
    tags = set(best_sense.get("tags", []))
    candidate_pos = normalize_pos(entry.get("pos"))
    return {
        "definition_en": best_sense["definition_en"],
        "example_en": best_sense["example_en"],
        "ipa": ipa,
        "audio_url": audio_url,
        "source_definition": SOURCE_DEFINITION,
        "_entry_pos": candidate_pos,
        "_pos_match": False,
        "_archaic_or_obsolete": bool(tags & ARCHAIC_TAGS),
        "_tags": sorted(tags),
    }


def candidate_score(seed_pos: str, candidate: dict[str, object]) -> int:
    score = 1000

    if candidate.get("definition_en"):
        score += 100

    candidate_pos = normalize_text(candidate.get("_entry_pos", ""))
    if candidate_pos and seed_pos == candidate_pos:
        score += 100
    elif candidate_pos:
        score += 10

    if candidate.get("example_en"):
        score += 10

    if candidate.get("ipa"):
        score += 2

    if candidate.get("audio_url"):
        score += 1

    if candidate.get("_archaic_or_obsolete"):
        score -= 25

    return score


def choose_best_matches(
    entries: list[dict[str, str]],
    grouped_entries: dict[str, list[tuple[int, dict[str, str]]]],
    kaikki_paths: list[Path],
) -> tuple[dict[int, dict[str, object]], dict[str, int]]:
    best_matches: dict[int, dict[str, object]] = {}
    stats = {
        "records_scanned": 0,
        "english_records": 0,
        "word_candidates": 0,
        "usable_candidates": 0,
    }

    for _, _, raw_entry in iter_kaikki_records(kaikki_paths):
        stats["records_scanned"] += 1

        if not is_english_entry(raw_entry):
            continue
        stats["english_records"] += 1

        word = normalize_headword(raw_entry.get("word", ""))
        if not word or word not in grouped_entries:
            continue
        stats["word_candidates"] += 1

        candidate = build_candidate(raw_entry)
        if not candidate:
            continue
        stats["usable_candidates"] += 1

        for entry_index, seed_entry in grouped_entries[word]:
            score = candidate_score(seed_entry["pos"], candidate)
            enriched_candidate = {
                **candidate,
                "_score": score,
                "_pos_match": bool(
                    normalize_text(candidate.get("_entry_pos", ""))
                    and seed_entry["pos"] == candidate.get("_entry_pos")
                ),
            }

            existing = best_matches.get(entry_index)
            if existing is None or score > int(existing["_score"]):
                best_matches[entry_index] = enriched_candidate

    return best_matches, stats


def classify_match(
    seed_entry: dict[str, str],
    match: dict[str, object] | None,
) -> tuple[str, list[str]]:
    if not match or not normalize_text(match.get("definition_en", "")):
        return "unmatched", ["no_definition_match"]

    notes: list[str] = []
    pos_match = bool(match.get("_pos_match"))
    archaic = bool(match.get("_archaic_or_obsolete"))
    candidate_pos = normalize_text(match.get("_entry_pos", ""))

    if not pos_match:
        if candidate_pos:
            notes.append(f"pos_mismatch_fallback:{seed_entry['pos']}->{candidate_pos}")
        else:
            notes.append("candidate_pos_missing")

    if archaic:
        notes.append("archaic_or_obsolete")

    if not normalize_text(match.get("example_en", "")):
        notes.append("missing_example")

    if not normalize_text(match.get("ipa", "")):
        notes.append("missing_ipa")

    if pos_match and not archaic and normalize_text(match.get("example_en", "")):
        quality = "high"
    elif pos_match and not archaic:
        quality = "medium"
    else:
        quality = "low"

    return quality, notes


def build_output_rows(
    entries: list[dict[str, str]],
    best_matches: dict[int, dict[str, object]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, entry in enumerate(entries):
        match = best_matches.get(index)
        match_quality, notes = classify_match(entry, match)

        rows.append(
            {
                "headword": entry["headword"],
                "normalized_headword": entry["normalized_headword"],
                "pos": entry["pos"],
                "cefr": entry["cefr"],
                "definition_en": normalize_text(match.get("definition_en", "") if match else ""),
                "example_en": normalize_text(match.get("example_en", "") if match else ""),
                "ipa": normalize_text(match.get("ipa", "") if match else ""),
                "audio_url": normalize_text(match.get("audio_url", "") if match else ""),
                "source_definition": normalize_text(
                    match.get("source_definition", "") if match else ""
                ),
                "source_list": entry["source_list"],
                "match_quality": match_quality,
                "notes": "; ".join(notes),
            }
        )
    return rows


def write_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_report(
    rows: list[dict[str, str]],
    stats: dict[str, int],
) -> dict[str, object]:
    matched = sum(1 for row in rows if row["definition_en"])
    with_example = sum(1 for row in rows if row["example_en"])
    with_ipa = sum(1 for row in rows if row["ipa"])
    manual_review_rows = [
        {
            "headword": row["headword"],
            "pos": row["pos"],
            "cefr": row["cefr"],
            "match_quality": row["match_quality"],
            "notes": row["notes"],
        }
        for row in rows
        if row["match_quality"] in {"low", "unmatched"}
    ]

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "total_oxford_entries": len(rows),
            "matched_entries": matched,
            "unmatched_entries": len(rows) - matched,
            "entries_with_definition": matched,
            "entries_with_example": with_example,
            "entries_with_ipa": with_ipa,
            "requires_manual_review": len(manual_review_rows),
        },
        "scan_stats": stats,
        "manual_review_entries": manual_review_rows,
    }


def write_report(report_path: Path, report: dict[str, object]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    oxford_path = Path(args.oxford)
    kaikki_path = Path(args.kaikki)
    output_path = Path(args.output)
    report_path = Path(args.report)

    LOGGER.info("Oxford CSV: %s", oxford_path)
    LOGGER.info("Kaikki input: %s", kaikki_path)
    LOGGER.info("Output CSV: %s", output_path)
    LOGGER.info("Report JSON: %s", report_path)

    missing = [str(path) for path in (oxford_path, kaikki_path) if not path.exists()]
    if missing:
        for path in missing:
            LOGGER.error("Required input does not exist: %s", path)
        return 1

    try:
        entries = load_oxford_entries(oxford_path)
        grouped_entries = group_entries_by_headword(entries)
        kaikki_paths = iter_kaikki_paths(kaikki_path)
        best_matches, stats = choose_best_matches(entries, grouped_entries, kaikki_paths)
        rows = build_output_rows(entries, best_matches)
        report = build_report(rows, stats)
        write_csv(output_path, rows)
        write_report(report_path, report)
    except (EnrichmentError, OSError, csv.Error) as exc:
        LOGGER.error("Failed to enrich entries: %s", exc)
        return 1

    matched_rows = report["summary"]["matched_entries"]
    manual_review = report["summary"]["requires_manual_review"]
    LOGGER.info("Scanned %d Kaikki records", stats["records_scanned"])
    LOGGER.info("English records: %d", stats["english_records"])
    LOGGER.info("Word candidates: %d", stats["word_candidates"])
    LOGGER.info("Usable candidates: %d", stats["usable_candidates"])
    LOGGER.info("Matched %d of %d Oxford entries", matched_rows, len(rows))
    LOGGER.info("Manual review required for %d entries", manual_review)
    return 0


if __name__ == "__main__":
    sys.exit(main())
