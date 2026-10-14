"""
Match figure captions to images using spatial coordinates.
V20.3 - For each caption paragraph, find figures on the same page
        whose bbox is above the caption text.

Logic:
  1. Find paragraphs that look like figure captions (start with "Fig. N.")
  2. Get caption's page + bbox
  3. Find figures on same page whose bbox is above caption
  4. Link them in figures.caption field
"""
import sqlite3
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "research.db"

CAPTION_RE = re.compile(
    r'^(Fig(?:ure)?\.?\s*(\d+[a-z]?))[\.\:\s—\-]+\s*(.+)',
    re.IGNORECASE
)


def parse_bbox(bbox_str: str):
    """Parse 'l,t,r,b' string into tuple of floats."""
    try:
        parts = [float(x) for x in bbox_str.split(',')]
        return tuple(parts)
    except:
        return None


def match_captions_to_figures():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Get all papers
    cur.execute("SELECT paper_id FROM papers")
    papers = [row[0] for row in cur.fetchall()]

    total_matched = 0
    total_captions = 0
    papers_processed = 0

    for paper_id in papers:
        # Get all figures for this paper
        cur.execute("""
            SELECT fig_id, fig_number, caption, file_path, page, bbox
            FROM figures WHERE paper_id = ?
        """, (paper_id,))
        fig_rows = cur.fetchall()
        figures = []
        for fig_id, fig_num, caption, file_path, page, bbox in fig_rows:
            bbox_t = parse_bbox(bbox) if bbox else None
            figures.append({
                'fig_id': fig_id,
                'fig_number': fig_num,
                'caption': caption,
                'file_path': file_path,
                'page': page,
                'bbox': bbox_t,
            })

        # Get all paragraphs that look like captions
        cur.execute("""
            SELECT para_id, text, page, bbox
            FROM paragraphs WHERE paper_id = ?
        """, (paper_id,))
        para_rows = cur.fetchall()

        captions = []
        for para_id, text, page, bbox in para_rows:
            if not text or len(text) < 20:
                continue
            m = CAPTION_RE.match(text.strip())
            if m:
                bbox_t = parse_bbox(bbox) if bbox else None
                captions.append({
                    'para_id': para_id,
                    'fig_label': m.group(1),
                    'fig_num': m.group(2),
                    'text': text.strip(),
                    'page': page,
                    'bbox': bbox_t,
                })

        if not captions or not figures:
            continue

        total_captions += len(captions)

        # For each caption, find matching figures
        for cap in captions:
            if not cap['page'] or not cap['bbox']:
                continue

            # Caption bbox: (l, t, r, b) in BOTTOMLEFT coords
            # t = top of caption (higher y), b = bottom of caption (lower y)
            cap_l, cap_t, cap_r, cap_b = cap['bbox']

            # Find figures on same page, above the caption
            candidates = []
            for fig in figures:
                if not fig['page'] or not fig['bbox']:
                    continue
                if fig['page'] != cap['page']:
                    continue

                fl, ft, fr, fb = fig['bbox']

                # Figure should be above caption:
                # figure's bottom (fb) > caption's top (cap_t)
                # because in BOTTOMLEFT, higher y = higher on page
                # and figure is above caption visually
                if fb > cap_t - 20:  # 20px tolerance
                    # Also check horizontal overlap
                    h_overlap = min(fr, cap_r) - max(fl, cap_l)
                    if h_overlap > 0:
                        # Distance from figure bottom to caption top
                        distance = fb - cap_t
                        candidates.append((distance, fig))

            if candidates:
                # Pick closest figure(s)
                candidates.sort(key=lambda x: x[0])
                best_fig = candidates[0][1]

                # Update figure caption if it's empty
                if not best_fig['caption'] or best_fig['caption'] == 'No caption...':
                    cur.execute("""
                        UPDATE figures SET caption = ? WHERE fig_id = ?
                    """, (cap['text'][:500], best_fig['fig_id']))
                    total_matched += 1

        papers_processed += 1
        if papers_processed % 10 == 0:
            print(f"  [{papers_processed}/{len(papers)}] papers, {total_matched} matched so far")

    conn.commit()

    # Stats
    cur.execute("SELECT COUNT(*) FROM figures")
    total_figs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM figures WHERE caption IS NOT NULL AND caption != '' AND caption != 'No caption...'")
    with_caption = cur.fetchone()[0]

    print(f"\n✅ Done!")
    print(f"  Papers processed: {papers_processed}")
    print(f"  Captions found: {total_captions}")
    print(f"  Figures matched: {total_matched}")
    print(f"  Figures with caption: {with_caption}/{total_figs} ({100*with_caption/total_figs:.1f}%)")

    conn.close()


if __name__ == "__main__":
    match_captions_to_figures()
