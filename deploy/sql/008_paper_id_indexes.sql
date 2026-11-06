-- paper_id indexes for per-paper import/delete paths
CREATE INDEX IF NOT EXISTS idx_paragraphs_paper_id ON paragraphs(paper_id);
CREATE INDEX IF NOT EXISTS idx_sentences_paper_id ON sentences(paper_id);
CREATE INDEX IF NOT EXISTS idx_citations_paper_id ON citations(paper_id);
CREATE INDEX IF NOT EXISTS idx_figures_paper_id ON figures(paper_id);
CREATE INDEX IF NOT EXISTS idx_sections_paper_id ON sections(paper_id);
CREATE INDEX IF NOT EXISTS idx_sentence_links_paper_id ON sentence_links(paper_id);
CREATE INDEX IF NOT EXISTS idx_tables_paper_id ON "tables"(paper_id);
