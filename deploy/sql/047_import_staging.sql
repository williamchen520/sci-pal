ALTER TABLE import_items
    ADD COLUMN IF NOT EXISTS staged_path text,
    ADD COLUMN IF NOT EXISTS parsed_json jsonb;

CREATE INDEX IF NOT EXISTS import_items_parsed_idx
    ON import_items (import_id) WHERE parsed_json IS NOT NULL;
