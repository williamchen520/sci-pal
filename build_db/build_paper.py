#!/usr/bin/env python3
"""
Offline Paper Build Script
Run this on your local GPU machine to build the database
Usage: python -m build_db.build_paper path/to/paper.pdf
"""
import sys
import os
from .parsers.parser_orchestrator import ParserOrchestrator
from .db_writer import DatabaseWriter

def build_paper(pdf_path: str):
    """Build a single paper into the database"""
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
    
    print(f"Building paper: {pdf_path}")
    
    # Run parsing
    orchestrator = ParserOrchestrator()
    parsed_result = orchestrator.parse_paper(pdf_path)
    
    # Write to database
    db_writer = DatabaseWriter()
    success = db_writer.insert_paper(parsed_result)
    
    if success:
        print(f"\n✅ Successfully built paper: {parsed_result['paper_id']}")
        print(f"   Title: {parsed_result['metadata'].get('title', 'Unknown')}")
    else:
        print("\n❌ Failed to build paper")
        sys.exit(1)

def build_batch(pdf_dir: str):
    """Build all PDFs in a directory"""
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        return
    
    print(f"Found {len(pdf_files)} PDF files to process")
    print("=" * 60)
    
    orchestrator = ParserOrchestrator()
    db_writer = DatabaseWriter()
    
    success_count = 0
    for i, filename in enumerate(pdf_files, 1):
        pdf_path = os.path.join(pdf_dir, filename)
        print(f"\n[{i}/{len(pdf_files)}] Processing: {filename}")
        
        try:
            parsed_result = orchestrator.parse_paper(pdf_path)
            success = db_writer.insert_paper(parsed_result)
            if success:
                success_count += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print(f"✅ Batch build complete: {success_count}/{len(pdf_files)} papers built successfully")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single paper: python -m build_db.build_paper path/to/paper.pdf")
        print("  Batch build:  python -m build_db.build_paper path/to/pdf_folder/")
        sys.exit(1)
    
    path = sys.argv[1]
    
    if os.path.isdir(path):
        build_batch(path)
    else:
        build_paper(path)
