"""
Test Docling PDF parser
Quick test to see what Docling outputs
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ============================================================
# Model config - use Chinese mirror, disable Xet
# ============================================================
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
from docling.chunking import HierarchicalChunker


def test_docling_parse(pdf_path: str):
    """Test Docling parsing on a sample PDF
    - OCR: OFF
    - Table structure: ON
    - Layout detection: ON
    """
    print("=" * 70)
    print(f"Testing Docling on: {pdf_path}")
    print("Mode: No OCR, but keep layout + table AI")
    print("=" * 70)
    
    # Step 1: Convert PDF
    print("\n🔄 Step 1: Converting PDF...")
    print("GPU: ON (cuda) | CPU threads: 8")
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False  # Skip OCR (digital PDFs don't need it)
    pipeline_options.do_table_structure = True  # Keep table structure AI

    # Enable heading hierarchy (uses PDF bookmarks first)
    pipeline_options.heading_hierarchy_options.enabled = True
    pipeline_options.heading_hierarchy_options.use_bookmarks = True

    # GPU + multithreading
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=8,
        device="cuda"  # Use GPU (RTX 4060)
    )
    
    converter = DocumentConverter(
        format_options={
            "pdf": PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(pdf_path)
    doc = result.document
    
    print(f"✅ Conversion done!")
    
    # Step 2: Export to Markdown to see structure
    print("\n📝 Step 2: Exporting to Markdown (first 100 lines)...")
    md_text = doc.export_to_markdown()
    lines = md_text.split('\n')
    for i, line in enumerate(lines[:100]):
        if line.strip():
            print(f"  {i+1:3d}: {line[:100]}")
    
    print(f"\n  ... total lines: {len(lines)}")
    
    # Step 3: Use HierarchicalChunker to see chunks
    print("\n📦 Step 3: Hierarchical Chunking...")
    chunker = HierarchicalChunker()
    chunks = list(chunker.chunk(doc))
    
    print(f"✅ Total chunks: {len(chunks)}")
    
    # Show first 10 chunks
    print("\n📋 First 10 chunks:")
    for i, chunk in enumerate(chunks[:10]):
        text_preview = chunk.text[:100].replace('\n', ' ')
        print(f"  Chunk {i+1:2d}: {text_preview}...")
    
    # Step 4: Show metadata from chunks
    print("\n🏷️  Chunk metadata (first 5):")
    for i, chunk in enumerate(chunks[:5]):
        meta = chunk.meta
        print(f"  Chunk {i+1}:")
        print(f"    Headings: {meta.headings}")
        # captions and page_no vary by version, skip if not available
        if hasattr(meta, 'captions'):
            print(f"    Captions: {meta.captions}")
    
    print("\n" + "=" * 70)
    print("✅ Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    # Test with a sample PDF
    documents_dir = project_root / "documents"
    pdf_files = list(documents_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No PDF files found in documents/")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF files")
    print(f"Using first one: {pdf_files[0].name}")
    
    test_docling_parse(str(pdf_files[0]))
