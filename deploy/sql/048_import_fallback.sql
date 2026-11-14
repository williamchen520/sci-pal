ALTER TABLE import_items
    ADD COLUMN IF NOT EXISTS fallback_path text;
