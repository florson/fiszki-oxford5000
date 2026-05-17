# Fiszki app ETL

Lokalny pipeline ETL przygotowujący bazę SQLite dla aplikacji webowej do nauki słówek po angielsku.

## Cel projektu

Celem projektu jest zbudowanie prostego, lokalnego pipeline ETL, który:

- bierze listę słów z Oxford 5000 jako seed,
- wzbogaca ją o definicje i przykłady z Kaikki / Wiktionary,
- zapisuje wynik do SQLite,
- pozwala przyszłej aplikacji korzystać wyłącznie z gotowej bazy danych.

Na tym etapie nie używamy Oxforda jako źródła definicji i nie opieramy rozwiązania na zewnętrznym live API.

## Źródła danych

### 1. Oxford 5000

Źródło seed listy słów:

- `headword`
- `part of speech`
- `CEFR`

Oxford 5000 służy tutaj tylko jako lista haseł wejściowych.

### 2. Kaikki / Wiktionary

Źródło danych leksykalnych:

- definicje po angielsku,
- przykładowe zdania,
- IPA,
- opcjonalnie audio.

Dane wejściowe zakładamy w formacie JSONL i przetwarzamy strumieniowo.

### 3. SQLite

Docelowy storage używany później przez backend aplikacji.

## Struktura projektu

```text
data_raw/
  oxford/
  kaikki/
data_processed/
etl/
  parse_oxford_5000.py
  enrich_from_kaikki.py
  build_seed_db.py
db/
  schema.sql
README.md
```

## Kolejność uruchamiania pipeline

1. Przygotować lokalny plik źródłowy Oxford 5000 w `data_raw/oxford/`.
2. Uruchomić parser Oxford 5000:
   - wejście: plik lokalny z listą Oxford 5000
   - wyjście: `data_processed/oxford5000.csv`
3. Przygotować lokalny dump Kaikki w `data_raw/kaikki/`.
4. Uruchomić enrichment z Kaikki:
   - wejście: `data_processed/oxford5000.csv` oraz dump Kaikki
   - wyjście: `data_processed/entries_enriched.csv`
   - dodatkowo: `data_processed/match_report.json`
5. Zbudować bazę SQLite:
   - wejście: `data_processed/entries_enriched.csv`
   - wyjście: `db/app.db`

## Wejścia i wyjścia

### Wejścia

- `data_raw/oxford/` - lokalny plik z listą Oxford 5000
- `data_raw/kaikki/` - lokalny dump Kaikki / Wiktionary w formacie JSONL

### Przetworzone dane

- `data_processed/oxford5000.csv` - ustandaryzowana lista seed słów
- `data_processed/entries_enriched.csv` - seed wzbogacony o definicje i przykłady
- `data_processed/match_report.json` - raport jakości dopasowań

### Baza danych

- `db/schema.sql` - definicja schematu SQLite
- `db/app.db` - gotowa lokalna baza dla aplikacji

## Skrypty ETL

### `etl/parse_oxford_5000.py`

Parsuje lokalną listę Oxford 5000 i zapisuje wynik do CSV.

Przykładowe uruchomienie:

```bash
python etl/parse_oxford_5000.py --input data_raw/oxford/source.txt --output data_processed/oxford5000.csv
```

### `etl/enrich_from_kaikki.py`

Wzbogaca seed Oxford 5000 danymi z Kaikki / Wiktionary.

Przykładowe uruchomienie:

```bash
python etl/enrich_from_kaikki.py --oxford data_processed/oxford5000.csv --kaikki data_raw/kaikki/kaikki.jsonl --output data_processed/entries_enriched.csv --report data_processed/match_report.json
```

### `etl/build_seed_db.py`

Buduje finalną bazę SQLite na podstawie przetworzonego CSV.

Przykładowe uruchomienie:

```bash
python etl/build_seed_db.py --input data_processed/entries_enriched.csv --schema db/schema.sql --db db/app.db
```

## Status

Milestone 1 przygotowuje tylko strukturę projektu i szkielety plików. W kolejnych etapach zostanie dodana właściwa logika ETL.
