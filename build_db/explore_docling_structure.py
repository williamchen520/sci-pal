"""
Explore Docling output structure - dump all item types, fields, and hierarchy
"""
import sys
from pathlib import Path
from collections import Counter

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
from docling.document_converter import PdfFormatOption


def explore_docling_structure(pdf_path: str):
    """Dump the full structure of Docling output"""
    print("=" * 70)
    print(f"🔍 Exploring: {Path(pdf_path).name}")
    print("=" * 70)
    
    # Setup converter
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    pipeline_options.images_scale = 2.0
    pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device="cuda")
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    
    result = converter.convert(pdf_path)
    doc = result.document
    
    # ============================================================
    # 1. Top-level attributes
    # ============================================================
    print("\n📦 1. Top-level document attributes:")
    print("-" * 50)
    for attr in sorted(dir(doc)):
        if not attr.startswith('_'):
            val = getattr(doc, attr)
            if not callable(val):
                print(f"  .{attr}: {type(val).__name__}")
    
    # ============================================================
    # 2. Count item types
    # ============================================================
    print("\n📊 2. Item type counts:")
    print("-" * 50)
    
    item_counts = Counter()
    for item in doc.iterate_items():
        item_type = type(item).__name__
        item_counts[item_type] += 1
    
    for item_type, count in item_counts.most_common():
        print(f"  {count:4d} × {item_type}")
    
    # ============================================================
    # 3. Section headers - what do they look like?
    # ============================================================
    print("\n📑 3. Section headers (first 20):")
    print("-" * 50)
    
    from docling_core.types.doc import SectionHeaderItem
    count = 0
    for item, level in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            count += 1
            if count <= 20:
                text = item.text[:60] if hasattr(item, 'text') else 'N/A'
                prov = item.prov[0] if item.prov else None
                page = prov.page_no if prov else '?'
                print(f"  L{level} | p{page:3d} | {text}")
    
    print(f"  ... total: {count} section headers")
    
    # ============================================================
    # 4. Sample paragraph structure
    # ============================================================
    print("\n📝 4. Sample paragraph structure:")
    print("-" * 50)
    
    from docling_core.types.doc import TextItem
    para_count = 0
    for item, level in doc.iterate_items():
        if isinstance(item, TextItem) and item.label == "paragraph":
            para_count += 1
            if para_count <= 3:
                print(f"\n  Paragraph #{para_count}:")
                print(f"    text: {item.text[:80]}...")
                print(f"    label: {item.label}")
                print(f"    level: {level}")
                if item.prov:
                    prov = item.prov[0]
                    print(f"    page_no: {prov.page_no}")
                    print(f"    bbox: {prov.bbox}")
                print(f"    All attrs: {[a for a in dir(item) if not a.startswith('_')]}")
            if para_count > 3:
                break
    
    # ============================================================
    # 5. Title item
    # ============================================================
    print("\n🏷️ 5. Title item:")
    print("-" * 50)
    
    title_count = 0
    for item, level in doc.iterate_items():
        if isinstance(item, TextItem) and item.label == "title":
            title_count += 1
            print(f"  Title: {item.text[:80]}")
            print(f"    level: {level}")
            if item.prov:
                print(f"    page_no: {item.prov[0].page_no}")
    print(f"  Total titles: {title_count}")
    
    # ============================================================
    # 6. Body tree structure (first 30 nodes)
    # ============================================================
    print("\n🌳 6. Body tree structure (first 30 nodes):")
    print("-" * 50)
    
    def print_tree(node, depth=0, max_depth=10, count=[0]):
        if count[0] >= 30:
            return
        count[0] += 1
        
        indent = "  " * depth
        node_type = type(node).__name__
        
        text_preview = ""
        if hasattr(node, 'text') and node.text:
            text_preview = f": {node.text[:50]}"
        
        label = ""
        if hasattr(node, 'label') and node.label:
            label = f" [{node.label}]"
        
        print(f"{indent}{node_type}{label}{text_preview}")
        
        if depth < max_depth:
            for child in getattr(node, 'children', []):
                print_tree(child, depth + 1, max_depth, count)
    
    print_tree(doc.body)
    
    # ============================================================
    # 7. Metadata
    # ============================================================
    print("\n📋 7. Document metadata:")
    print("-" * 50)
    if hasattr(doc, 'metadata') and doc.metadata:
        for attr in sorted(dir(doc.metadata)):
            if not attr.startswith('_'):
                val = getattr(doc.metadata, attr)
                if not callable(val):
                    print(f"  .{attr}: {val}")
    
    print("\n" + "=" * 70)
    print("✅ Exploration complete!")
    print("=" * 70)


def explore_paper_sections(pdf_path: str, show_details: bool = False):
    """Quickly dump section headers for one paper"""
    from docling_core.types.doc import SectionHeaderItem
    
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = False  # Faster, no need for images
    pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device="cuda")
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    
    result = converter.convert(pdf_path)
    doc = result.document
    
    sections = []
    for item, level in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            prov = item.prov[0] if item.prov else None
            page = prov.page_no if prov else '?'
            text = item.text[:60] if hasattr(item, 'text') else 'N/A'
            sections.append((page, text))
    
    return sections


def explore_all_papers():
    """Dump section headers for all PDFs"""
    pdf_dir = project_root / "documents"
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    
    print("=" * 80)
    print(f"🔍 Exploring section structure for all {len(pdfs)} papers")
    print("=" * 80)
    
    summary = []
    
    for i, pdf in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] {pdf.name[:60]}")
        print("-" * 70)
        
        try:
            sections = explore_paper_sections(str(pdf))
            print(f"  Found {len(sections)} section headers")
            for page, text in sections:
                print(f"    p{page:3d} | {text}")
            summary.append((pdf.name, len(sections)))
        except Exception as e:
            print(f"  ❌ Error: {e}")
            summary.append((pdf.name, -1))
    
    print("\n" + "=" * 80)
    print("📊 Summary:")
    print("-" * 50)
    for name, count in summary:
        status = "✅" if count > 5 else "⚠️" if count > 0 else "❌"
        print(f"  {status} {count:3d} sections: {name[:55]}")
    
    total = sum(c for _, c in summary if c > 0)
    good = sum(1 for _, c in summary if c > 5)
    print(f"\n  Total sections found: {total}")
    print(f"  Papers with >5 sections: {good}/{len(pdfs)}")


if __name__ == "__main__":
    explore_all_papers()
