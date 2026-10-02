"""
Test docling-hierarchical-pdf package
- Compare section hierarchy before and after
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
from docling.document_converter import PdfFormatOption
from docling_core.types.doc import SectionHeaderItem


def get_sections(doc):
    """Extract all section headers with their level"""
    sections = []
    for item, level in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            prov = item.prov[0] if item.prov else None
            page = prov.page_no if prov else '?'
            text = item.text[:70]
            sections.append((level, page, text))
    return sections


def test_on_paper(pdf_path: str):
    """Test hierarchy on one paper"""
    print("=" * 70)
    print(f"📄 Testing: {Path(pdf_path).name}")
    print("=" * 70)
    
    # Setup converter
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = False
    pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device="cuda")
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    
    result = converter.convert(pdf_path)
    
    # Before
    print("\n📊 BEFORE docling-hierarchical-pdf:")
    print("-" * 50)
    before = get_sections(result.document)
    for level, page, text in before:
        indent = "  " * (level - 1) if level else ""
        print(f"{indent}L{level} | p{page:3d} | {text}")
    print(f"  Total: {len(before)} sections")
    
    # Apply postprocessor
    print("\n🔧 Applying docling-hierarchical-pdf...")
    try:
        from hierarchical.postprocessor import ResultPostprocessor
        ResultPostprocessor(result, source=pdf_path).process()
        print("  ✅ Success!")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # After
    print("\n📊 AFTER docling-hierarchical-pdf:")
    print("-" * 50)
    after = get_sections(result.document)
    for level, page, text in after:
        indent = "  " * (level - 1) if level else ""
        print(f"{indent}L{level} | p{page:3d} | {text}")
    print(f"  Total: {len(after)} sections")
    
    # Comparison
    print("\n📈 Comparison:")
    print("-" * 50)
    before_levels = set(lvl for lvl, _, _ in before)
    after_levels = set(lvl for lvl, _, _ in after)
    print(f"  Levels before: {sorted(before_levels)}")
    print(f"  Levels after:  {sorted(after_levels)}")


if __name__ == "__main__":
    pdf_dir = project_root / "documents"
    
    # Test specific paper: nihms633763.pdf
    test_paper = pdf_dir / "nihms633763.pdf"
    
    if test_paper.exists():
        test_on_paper(str(test_paper))
    else:
        print(f"❌ File not found: {test_paper}")
        print("Available PDFs:")
        for p in sorted(pdf_dir.glob("*.pdf")):
            print(f"  - {p.name}")
