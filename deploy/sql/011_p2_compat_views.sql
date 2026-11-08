-- P2 compatibility views for work/document identity.

BEGIN;

CREATE OR REPLACE VIEW library_main.v_documents AS
SELECT d.document_id,
       d.work_id,
       d.library_id,
       d.source_type,
       d.source_path,
       d.sha256,
       d.parser,
       d.parser_version,
       d.imported_at,
       w.primary_doi,
       w.pmcid,
       w.title AS work_title,
       w.year  AS work_year
FROM library_main.documents d
JOIN catalog.works w ON w.work_id = d.work_id;

CREATE OR REPLACE VIEW library_main.v_works AS
SELECT w.work_id,
       w.primary_doi,
       w.pmcid,
       w.title,
       w.year,
       count(d.document_id) AS document_count
FROM catalog.works w
LEFT JOIN library_main.documents d ON d.work_id = w.work_id
GROUP BY w.work_id, w.primary_doi, w.pmcid, w.title, w.year;

COMMIT;
