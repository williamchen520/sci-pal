"""
Quick test: count GROBID in-text citations per paper
"""
import os
from pathlib import Path
from build_db.parsers.grobid_parser import GrobidParser

project_root = Path(__file__).parent.parent
pdf_dir = project_root / "documents"

parser = GrobidParser()
if not parser.is_alive():
    exit(1)

pdfs = sorted(pdf_dir.glob("*.pdf"))
print(f"📄 Found {len(pdfs)} PDFs\n")

total_refs = 0
total_intext = 0
results = []

for i, pdf in enumerate(pdfs):
    print(f"[{i+1}/{len(pdfs)}] {pdf.name[:50]}...", end=" ", flush=True)
    try:
        result = parser.parse(str(pdf))
        refs = len(result["citations"])
        intext = len(result["intext_citations"])
        total_refs += refs
        total_intext += intext
        results.append((pdf.name, refs, intext))
        print(f"refs={refs}, intext={intext}")
    except Exception as e:
        print(f"❌ Error: {e}")

print(f"\n{'='*60}")
print(f"📊 Summary:")
print(f"  Total papers: {len(results)}")
print(f"  Total references: {total_refs}")
print(f"  Total in-text links: {total_intext}")
print(f"  Avg refs per paper: {total_refs/len(results):.0f}")
print(f"  Avg in-text per paper: {total_intext/len(results):.0f}")
print(f"  Ratio: {total_intext/total_refs:.2f}x")
