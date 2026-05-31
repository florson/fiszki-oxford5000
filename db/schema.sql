DROP TABLE IF EXISTS dictionary_entries;

CREATE TABLE dictionary_entries (
    id INTEGER PRIMARY KEY,
    headword TEXT NOT NULL,
    normalized_headword TEXT NOT NULL,
    pos TEXT,
    cefr TEXT,
    definition_en TEXT,
    example_en TEXT,
    ipa TEXT,
    audio_url TEXT,
    source_list TEXT,
    source_definition TEXT,
    match_quality TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE INDEX idx_dictionary_entries_normalized_headword
    ON dictionary_entries(normalized_headword);

CREATE INDEX idx_dictionary_entries_cefr
    ON dictionary_entries(cefr);

CREATE INDEX idx_dictionary_entries_pos
    ON dictionary_entries(pos);
