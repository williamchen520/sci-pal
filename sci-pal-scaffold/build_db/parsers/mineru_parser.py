"""
MinerU Primary Parser Wrapper
Best overall parser for academic PDFs
"""
import os
import json
import hashlib
from typing import Dict, List, Any
from .base_parser import BaseParser

class MinerUParser(BaseParser):
    """Wrapper around MinerU for primary PDF parsing"""
    
    def __init__(self, output_dir: str = None):
        self.name = "mineru"
        self._parser_loaded = False
        self._parser = None
        self.output_dir = output_dir or "data/parsed_output"
    
    def _load_parser(self):
        """Lazy load MinerU to avoid startup delay"""
        if self._parser_loaded:
            return
        
        try:
            # Try importing MinerU
            from magic_pdf.cli.common import common_parse
            self._parser = common_parse
            self._parser_loaded = True
            print("✅ MinerU parser loaded successfully")
        except ImportError:
            print("⚠️  MinerU not installed yet. Run: pip install mineru[all]")
            self._parser = None
    
    def get_parser_name(self) -> str:
        return self.name
    
    def parse(self, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        """
        Parse PDF with MinerU
        Returns our standardized format: {
            "paragraphs": [...],
            "figures": [...],
            "metadata": {...}
        }
        """
        self._load_parser()
        
        if not self._parser:
            print("⚠️  Falling back to stub parser")
            return self._stub_parse(pdf_path, paper_id)
        
        print(f"📄 Parsing {pdf_path} with MinerU...")
        
        try:
            # Create output directory for this paper
            paper_output_dir = os.path.join(self.output_dir, paper_id)
            os.makedirs(paper_output_dir, exist_ok=True)
            
            # Run MinerU parsing
            # Note: This is the actual MinerU API call
            # The exact API may vary by version
            from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
            from magic_pdf.data.data_reader_writer import FileBasedDataReader, FileBasedDataWriter
            from magic_pdf.data.dataset import PymuDocDataset
            
            # Read PDF
            pdf_bytes = open(pdf_path, "rb").read()
            reader_writer = FileBasedDataWriter(paper_output_dir)
            
            # Create dataset
            ds = PymuDocDataset(pdf_bytes)
            
            # Analyze with model
            inference_res = doc_analyze(ds, ocr=True, langs=["en"])
            
            # Apply to dataset
            ds.apply(inference_res)
            
            # Get markdown content
            md_content = ds.get_markdown_text()
            
            # Parse the markdown into our structured format
            return self._convert_mineru_output(ds, md_content, paper_id, pdf_path)
            
        except Exception as e:
            print(f"⚠️  MinerU parse error: {e}")
            print("Falling back to stub parser")
            return self._stub_parse(pdf_path, paper_id)
    
    def _convert_mineru_output(self, ds, markdown_text: str, paper_id: str, pdf_path: str) -> Dict[str, Any]:
        """
        Convert MinerU output to our standardized format
        """
        paragraphs = []
        figures = []
        para_index = 0
        
        # Extract metadata from first page
        metadata = {
            "title": self._extract_title_from_markdown(markdown_text),
            "authors": [],  # TODO: Extract authors
            "journal": None,
            "year": None,
            "doi": None,
            "abstract": self._extract_abstract(markdown_text),
            "page_count": self._estimate_page_count(markdown_text),
            "parser_source": "mineru"
        }
        
        # Parse markdown into paragraphs by section
        sections = self._parse_markdown_sections(markdown_text)
        
        current_section = "body"
        current_section_name = "Body"
        
        for i, section in enumerate(sections):
            para_text = section["text"].strip()
            if not para_text:
                continue
            
            para_id = f"{paper_id}_p{para_index + 1:03d}"
            
            paragraphs.append({
                "para_id": para_id,
                "paper_id": paper_id,
                "page_number": section.get("page", 1),
                "section_type": self._detect_section_type(section["heading"]),
                "section_name": section["heading"] or "Body",
                "para_index": para_index,
                "text_content": para_text,
                "char_start": 0,
                "char_end": len(para_text),
                "parser_source": "mineru"
            })
            
            para_index += 1
        
        # Extract figures (MinerU saves images to output dir)
        fig_index = 0
        image_dir = os.path.join(self.output_dir, paper_id, "images")
        if os.path.exists(image_dir):
            for img_file in sorted(os.listdir(image_dir)):
                if img_file.endswith(('.png', '.jpg', '.jpeg')):
                    fig_index += 1
                    figures.append({
                        "figure_id": f"{paper_id}_fig{fig_index:03d}",
                        "paper_id": paper_id,
                        "page_number": 1,  # TODO: Extract actual page
                        "figure_type": "figure",
                        "caption": f"Figure {fig_index}",
                        "image_path": os.path.join(image_dir, img_file),
                        "bbox": None,
                        "para_id": paragraphs[0]["para_id"] if paragraphs else None,
                        "parser_source": "mineru"
                    })
        
        return {
            "paragraphs": paragraphs,
            "figures": figures,
            "metadata": metadata
        }
    
    def _extract_title_from_markdown(self, md: str) -> str:
        """Extract paper title from markdown"""
        for line in md.split('\n'):
            line = line.strip()
            if line.startswith('# ') and len(line) > 5:
                return line[2:].strip()
        return "Unknown Title"
    
    def _extract_abstract(self, md: str) -> str:
        """Extract abstract from markdown"""
        in_abstract = False
        abstract_lines = []
        for line in md.split('\n'):
            line_lower = line.lower().strip()
            if 'abstract' in line_lower and len(line) < 50:
                in_abstract = True
                continue
            if in_abstract:
                if line.startswith('#') or line.strip() == '':
                    if abstract_lines:
                        break
                    continue
                abstract_lines.append(line.strip())
        return ' '.join(abstract_lines) if abstract_lines else None
    
    def _parse_markdown_sections(self, md: str) -> List[Dict]:
        """Parse markdown into sections with headings"""
        sections = []
        current_heading = None
        current_text = []
        
        for line in md.split('\n'):
            if line.startswith('#'):
                if current_text:
                    sections.append({
                        "heading": current_heading,
                        "text": '\n'.join(current_text)
                    })
                    current_text = []
                current_heading = line.lstrip('#').strip()
            else:
                current_text.append(line)
        
        if current_text:
            sections.append({
                "heading": current_heading,
                "text": '\n'.join(current_text)
            })
        
        return sections
    
    def _detect_section_type(self, heading: str = None) -> str:
        """Detect section type from heading"""
        if not heading:
            return "body"
        
        heading_lower = heading.lower()
        
        if "abstract" in heading_lower:
            return "abstract"
        elif "introduction" in heading_lower or "background" in heading_lower:
            return "introduction"
        elif "method" in heading_lower:
            return "methodology"
        elif "result" in heading_lower:
            return "results"
        elif "discussion" in heading_lower:
            return "discussion"
        elif "conclusion" in heading_lower:
            return "conclusion"
        elif "reference" in heading_lower:
            return "references"
        else:
            return "body"
    
    def _estimate_page_count(self, md: str) -> int:
        """Estimate page count from markdown length"""
        # Rough estimate: ~3000 chars per page
        return max(1, len(md) // 3000)
    
    def _stub_parse(self, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        """Stub parser used when MinerU is not installed"""
        filename = os.path.basename(pdf_path).replace('.pdf', '')
        
        return {
            "paragraphs": [
                {
                    "para_id": f"{paper_id}_p001",
                    "paper_id": paper_id,
                    "page_number": 1,
                    "section_type": "abstract",
                    "section_name": "Abstract",
                    "para_index": 0,
                    "text_content": f"[STUB] Parsing {filename} with MinerU stub. Install MinerU to get real results.",
                    "parser_source": "stub"
                }
            ],
            "figures": [],
            "metadata": {
                "title": filename.replace('_', ' ').title(),
                "authors": [],
                "year": None,
                "parser_source": "stub"
            }
        }
