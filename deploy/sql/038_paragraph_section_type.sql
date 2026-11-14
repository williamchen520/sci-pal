ALTER TABLE paragraphs
    ADD COLUMN IF NOT EXISTS section_type text;

CREATE INDEX IF NOT EXISTS paragraphs_paper_section_type_idx
    ON paragraphs (paper_id, section_type);
