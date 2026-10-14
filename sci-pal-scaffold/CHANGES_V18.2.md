# Changelog V18.2 — 2026-09-20

## build_db/download_test_papers.py

### Changes
- Reverted from OpenAlex back to NCBI E-utilities + Unpaywall (OpenAlex now requires registration/API key)
- Target journals changed to fully OA sub-journals: Cell Rep, Sci Adv, Nat Commun (8 papers each = 24 total)
- Downloads organized into journal-specific subfolders under documents/
- Fixed PMC XML parsing: `<article>` tags may have attributes, regex updated to `<article[^>]*>`
- Added fallback: if article-block parsing returns 0, extract DOIs directly via regex
- NCBI requests try direct connection first, proxy as fallback
- PDF downloads use browser-like Chrome User-Agent to avoid 403
- Unpaywall email updated to chenwei-ucas@outlook.com
- Added open access[filter] and date range (2023-2026) to PMC search query
