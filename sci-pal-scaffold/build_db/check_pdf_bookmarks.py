"""
Check which PDFs have built-in bookmarks (outline)
"""
import PyPDF2
from pathlib import Path

project_root = Path(__file__).parent.parent
pdf_dir = project_root / "documents"

def count_bookmarks(items, depth=0):
    """Count total bookmarks recursively"""
    count = 0
    for item in items:
        if isinstance(item, list):
            count += count_bookmarks(item, depth + 1)
        else:
            count += 1
    return count

def print_bookmarks(items, depth=0, max_depth=2):
    """Print bookmark structure"""
    for item in items:
        if isinstance(item, list):
            print_bookmarks(item, depth + 1, max_depth)
        else:
            title = item.title[:60] if hasattr(item, 'title') else str(item)
            indent = "  " * depth
            print(f"{indent}- {title}")

print("=" * 70)
print("📑 Checking PDF Bookmarks")
print("=" * 70)

has_bookmarks = []
no_bookmarks = []

for pdf in sorted(pdf_dir.glob("*.pdf")):
    try:
        reader = PyPDF2.PdfReader(str(pdf))
        outline = reader.outline
        total = count_bookmarks(outline)
        
        if total > 0:
            has_bookmarks.append((pdf.name, total))
        else:
            no_bookmarks.append(pdf.name)
    except Exception as e:
        print(f"❌ {pdf.name[:50]}: {e}")

print(f"\n✅ PDFs WITH bookmarks: {len(has_bookmarks)}")
print("-" * 70)
for name, count in has_bookmarks:
    print(f"  {count:3d} bookmarks: {name[:60]}")

print(f"\n❌ PDFs WITHOUT bookmarks: {len(no_bookmarks)}")
print("-" * 70)
for name in no_bookmarks:
    print(f"  - {name[:60]}")

print(f"\n📊 Summary:")
print(f"  Total PDFs: {len(has_bookmarks) + len(no_bookmarks)}")
print(f"  With bookmarks: {len(has_bookmarks)}")
print(f"  Without bookmarks: {len(no_bookmarks)}")
