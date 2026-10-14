# Sci-Pal V18.0 — Changelog

## What changed

### 1. Grobid title sanity check (build_db/build_database.py)

Grobid occasionally returns something that is **not** the paper title:

| Real case | Grobid returned | Why it's wrong |
|---|---|---|
| s41590-023-01588-w | `Estonian Biobank Research Team` | Consortium author name, not title |
| s11897-020-00469-9 | `TRANSLATIONAL RESEARCH IN HEART FAILURE (` | Journal running header, truncated |

A new function `is_grobid_title_suspicious(title)` now runs **before** Grobid overrides
the Docling-extracted title. If any rule triggers, the Grobid title is discarded and the
Docling/PyMuPDF title is kept.

**Rules:**
1. **Unbalanced parenthesis** — title ends with `(` but has more `(` than `)`.
2. **Consortium suffix** — title (≤8 words) ends with `research team / study group /
   consortium / collaboration / network / initiative / project / group`.
3. **All-caps running header** — >85% of letters are uppercase and ≤8 words.

**Fallback chain:** Grobid title (if clean) → Docling metadata → PyMuPDF → first L1 heading.

### 2. Verification script (build_db/verify_database.py)

New section **9b. Suspicious-Looking Titles** re-runs the same three rules against the
built database and flags any paper whose title still looks wrong.

---

## Files in this release

| File | Purpose |
|---|---|
| `build_db/build_database.py` | V18.0 — title sanity check added |
| `build_db/verify_database.py` | V18.0 — suspicious-title scan added |
| `CHANGES_V18.0.md` | This file |

## How to use

1. Copy `build_db/build_database.py` and `build_db/verify_database.py` into your project.
2. Rebuild the database (Grobid must be running on CPU):
   ```bash
   python -m build_db.build_database
   ```
3. Verify:
   ```bash
   python -m build_db.verify_database
   ```
   Check section **9b** — it should report no suspicious titles for the two previously-bad papers.

## Expected result

- s41590-023-01588-w → title should now come from Docling (real title: "Genetics of
  circulating inflammatory proteins identifies drivers...")
- s11897-020-00469-9 → title should now come from Docling (real title about Big Data
  in Heart Failure)
- All other 44 titles unchanged (Grobid titles that pass the sanity check are still used)
