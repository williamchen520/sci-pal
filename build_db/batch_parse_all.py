"""
Batch parse all PDFs in documents/ folder
V10.0 - First working version
"""
import os
import sys
import time
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Model config - use Chinese mirror, disable Xet
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
from docling.chunking import HierarchicalChunker


def batch_parse(input_dir: str = "documents", output_dir: str = "parsed_output", use_gpu: bool = True, num_threads: int = 8):
    """Batch parse all PDFs in input_dir

    Args:
        input_dir: Folder with PDFs
        output_dir: Folder to save results
        use_gpu: Use GPU acceleration if available (RTX 4060)
        num_threads: Number of CPU threads
    """

    input_path = project_root / input_dir
    output_path = project_root / output_dir
    output_path.mkdir(exist_ok=True)

    # Find all PDFs
    pdf_files = sorted(list(input_path.glob("*.pdf")))
    print("=" * 70)
    print(f"Found {len(pdf_files)} PDF files to process")
    print(f"Output directory: {output_path}")
    print(f"GPU: {'ON' if use_gpu else 'OFF'} | CPU threads: {num_threads}")
    print("=" * 70)

    # Setup converter
    print("\n🔄 Initializing Docling...")
    pipeline_options = PdfPipelineOptions()

    # Core settings
    pipeline_options.do_ocr = False  # OCR off (digital PDFs)
    pipeline_options.do_table_structure = True  # Table structure AI on
    pipeline_options.heading_hierarchy_options.enabled = True  # Heading hierarchy on
    pipeline_options.heading_hierarchy_options.use_bookmarks = True  # Use PDF bookmarks first

    # GPU + multithreading
    device = "cuda" if use_gpu else "cpu"
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=num_threads,
        device=device
    )

    converter = DocumentConverter(
        format_options={
            "pdf": PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    chunker = HierarchicalChunker()
    print("✅ Docling ready!\n")

    # Process each PDF
    results = []
    total_start = time.time()

    for i, pdf_file in enumerate(pdf_files):
        print(f"[{i+1}/{len(pdf_files)}] Processing: {pdf_file.name}")
        start = time.time()

        try:
            # Parse
            result = converter.convert(str(pdf_file))
            doc = result.document

            # Export to Markdown
            md_text = doc.export_to_markdown()

            # Chunk
            chunks = list(chunker.chunk(doc))

            # Collect stats
            chunk_data = []
            for j, chunk in enumerate(chunks):
                chunk_data.append({
                    "index": j,
                    "text": chunk.text[:500],  # Truncate for JSON
                    "headings": chunk.meta.headings if chunk.meta else []
                })

            # Save output
            paper_name = pdf_file.stem
            md_file = output_path / f"{paper_name}.md"
            json_file = output_path / f"{paper_name}.json"

            with open(md_file, "w", encoding="utf-8") as f:
                f.write(md_text)

            with open(json_file, "w", encoding="utf-8") as f:
                json.dump({
                    "filename": pdf_file.name,
                    "total_chunks": len(chunks),
                    "total_lines": len(md_text.split("\n")),
                    "chunks": chunk_data[:20]  # First 20 chunks only
                }, f, ensure_ascii=False, indent=2)

            elapsed = time.time() - start
            print(f"  ✅ Done! {len(chunks)} chunks, {elapsed:.1f}s")

            results.append({
                "filename": pdf_file.name,
                "chunks": len(chunks),
                "time_sec": round(elapsed, 1),
                "status": "success"
            })

        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ Error: {str(e)[:100]}")
            results.append({
                "filename": pdf_file.name,
                "chunks": 0,
                "time_sec": round(elapsed, 1),
                "status": f"error: {str(e)[:200]}"
            })

    # Summary
    total_time = time.time() - total_start
    success_count = sum(1 for r in results if r["status"] == "success")
    total_chunks = sum(r["chunks"] for r in results)

    print("\n" + "=" * 70)
    print("📊 Batch Parse Complete!")
    print("=" * 70)
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"Success: {success_count}")
    print(f"Failed: {len(pdf_files) - success_count}")
    print(f"Total chunks: {total_chunks}")
    print(f"Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    if success_count > 0:
        print(f"Average per paper: {total_time/success_count:.1f}s")
    print("=" * 70)

    # Save summary
    summary_file = output_path / "_batch_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_pdfs": len(pdf_files),
            "success": success_count,
            "failed": len(pdf_files) - success_count,
            "total_chunks": total_chunks,
            "total_time_sec": round(total_time, 1),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\nSummary saved to: {summary_file}")
    print(f"Markdown files in: {output_path}")


if __name__ == "__main__":
    batch_parse()
