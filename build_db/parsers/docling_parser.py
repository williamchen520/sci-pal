"""
Docling Parser
Primary PDF parser for Sci-Pal
- OCR: OFF (digital PDFs don't need it)
- Table structure: ON
- Layout detection: ON
- Heading hierarchy: ON (uses PDF bookmarks first)
"""
import os
import hashlib
from typing import Dict, List, Any
from pathlib import Path

# ============================================================
# Model config - use Chinese mirror, disable Xet
# ============================================================
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.chunking import HierarchicalChunker
from docling_core.types.doc import (
    TextItem,
    TableItem,
    SectionHeaderItem,
)

# V25.14 兼容：不同版本 docling_core 中 FigureItem 可能改名或不存在
try:
    from docling_core.types.doc import FigureItem
except ImportError:
    try:
        from docling_core.types.doc import PictureItem as FigureItem  # 旧版本名
    except ImportError:
        # 都没有时用占位类，isinstance 永远返回 False，图表按普通文本处理
        FigureItem = type('FigureItem', (), {})


class DoclingParser:
    """Docling-based primary PDF parser
    - OCR: OFF (digital PDFs don't need it)
    - Table structure: ON (keep table AI)
    - Layout detection: ON (keep section detection)
    """
    
    def __init__(self):
        # Configure pipeline: OCR off, but keep layout + table structure
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Skip OCR (digital PDFs don't need it)
        pipeline_options.do_table_structure = True  # Keep table structure AI
        pipeline_options.table_structure_options.mode = TableFormerMode.FAST  # CPU-friendly table mode
        
        # Enable heading hierarchy inference (OFF by default!)
        # Uses PDF bookmarks first, then numbering, then font size
        from docling.datamodel.pipeline_options import HeadingHierarchyOptions
        pipeline_options.heading_hierarchy_options = HeadingHierarchyOptions(
            enabled=True,              # Must be on
            use_bookmarks=True,        # Use bookmarks first
            use_numbering=True,        # Use numbering-based detection too
            use_style=True,            # Use style-based detection too (maximise headings)
            max_level=6,               # Max heading level (don't cut off top levels)
            bookmark_match_threshold=0.6  # Lower threshold to match more bookmarks
        )
        pipeline_options.generate_parsed_pages = True  # Needed for style-based heading detection
        pipeline_options.generate_picture_images = True  # Generate actual image data for figures
        pipeline_options.images_scale = 2.0  # 2x resolution for better quality
        print(f"🔍 Parser debug: generate_picture_images = {pipeline_options.generate_picture_images}")
        print(f"🔍 Parser debug: images_scale = {pipeline_options.images_scale}")

        self.converter = DocumentConverter(
            format_options={
                "pdf": PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        self.chunker = HierarchicalChunker()
        print("✅ Docling Parser initialized (native mode, no AI)")
    
    def parse(self, pdf_path: str, paper_id: str = None) -> Dict[str, Any]:
        """
        Parse a PDF using Docling
        
        Args:
            pdf_path: Path to PDF file
            paper_id: Paper ID (generated if not provided)
            
        Returns:
            Dict with paragraphs, figures, metadata, etc.
        """
        if not paper_id:
            paper_id = self._generate_paper_id(pdf_path)
        
        print(f"\n📄 Docling parsing: {os.path.basename(pdf_path)}")
        print(f"   Paper ID: {paper_id}")
        
        # Step 1: Convert PDF to DoclingDocument
        result = self.converter.convert(pdf_path)
        doc = result.document
        
        # Step 2: Extract metadata
        metadata = self._extract_metadata(doc, pdf_path, paper_id)
        
        # Step 3: Extract paragraphs using chunker
        paragraphs = self._extract_paragraphs(doc, paper_id)
        
        # Step 4: Extract figures and tables
        figures = self._extract_figures(doc, paper_id)
        
        # Step 5: Extract references (simple approach: last section)
        citations = self._extract_references(doc, paper_id)
        
        print(f"   ✅ Paragraphs: {len(paragraphs)}")
        print(f"   ✅ Figures: {len(figures)}")
        print(f"   ✅ Citations: {len(citations)}")
        
        return {
            "paper_id": paper_id,
            "metadata": metadata,
            "paragraphs": paragraphs,
            "figures": figures,
            "citations": citations,
        }
    
    def _generate_paper_id(self, pdf_path: str) -> str:
        """Generate paper ID from file hash"""
        with open(pdf_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:12]
        filename = os.path.basename(pdf_path).replace(".pdf", "")
        # Clean filename for ID
        clean_name = "".join(c if c.isalnum() else "_" for c in filename)[:50]
        return f"paper_{clean_name}_{file_hash}"
    
    def _extract_metadata(self, doc, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        """Extract paper metadata"""
        metadata = {
            "paper_id": paper_id,
            "file_path": pdf_path,
            "file_name": os.path.basename(pdf_path),
        }
        
        # Try to get title from first heading or document title
        if hasattr(doc, 'title') and doc.title:
            metadata["title"] = doc.title
        
        # Get filename as fallback
        if "title" not in metadata or not metadata["title"]:
            metadata["title"] = os.path.basename(pdf_path).replace(".pdf", "").replace("_", " ")
        
        # Extract abstract from abstract section
        abstract_text = self._extract_abstract(doc)
        metadata["abstract"] = abstract_text
        
        # Authors, journal, year - Docling may not extract these perfectly
        # We'll use Crossref API later for better metadata
        metadata["authors"] = []
        metadata["journal"] = ""
        metadata["year"] = ""
        metadata["doi"] = ""
        
        return metadata
    
    def _extract_abstract(self, doc) -> str:
        """Extract abstract text from the document"""
        try:
            current_heading = None
            in_abstract = False
            abstract_parts = []
            
            for item, level in doc.iterate_items():
                if isinstance(item, SectionHeaderItem):
                    heading_text = item.text.lower()
                    if any(kw in heading_text for kw in ["abstract", "summary"]):
                        in_abstract = True
                        continue
                    elif in_abstract:
                        # Hit next section, stop
                        break
                
                if in_abstract and isinstance(item, TextItem):
                    abstract_parts.append(item.text)
            
            if abstract_parts:
                return " ".join(abstract_parts)[:2000]  # Limit to 2000 chars
        except Exception as e:
            print(f"   ⚠️  Abstract extraction error: {e}")
        
        return ""
    
    @staticmethod
    def _prov_bbox(items) -> tuple:
        """Union the provenance bboxes of a chunk's items -> (page, 'l,t,r,b')."""
        boxes = []
        page = None
        for item in items or []:
            for prov in getattr(item, "prov", None) or []:
                bbox = getattr(prov, "bbox", None)
                if bbox is None:
                    continue
                try:
                    boxes.append(
                        (
                            float(getattr(bbox, "l", 0)),
                            float(getattr(bbox, "t", 0)),
                            float(getattr(bbox, "r", 0)),
                            float(getattr(bbox, "b", 0)),
                        )
                    )
                except (TypeError, ValueError):
                    continue
                if page is None:
                    page = getattr(prov, "page_no", None)
        if not boxes:
            return page, None
        left = min(b[0] for b in boxes)
        top = min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        bottom = max(b[3] for b in boxes)
        return page, f"{left:.2f},{top:.2f},{right:.2f},{bottom:.2f}"

    def _extract_paragraphs(self, doc, paper_id: str) -> List[Dict[str, Any]]:
        """Extract paragraphs using HierarchicalChunker"""
        paragraphs = []

        try:
            chunks = list(self.chunker.chunk(doc))

            for i, chunk in enumerate(chunks):
                # Determine section type from headings
                section_type = self._classify_section(chunk.meta.headings)
                section_title = chunk.meta.headings[-1] if chunk.meta.headings else ""

                para_id = f"{paper_id}_para_{i+1:04d}"
                bbox_page, bbox_text = self._prov_bbox(
                    getattr(chunk.meta, "doc_items", None)
                )
                page_no = getattr(chunk.meta, "page_no", None) or bbox_page

                paragraphs.append({
                    "para_id": para_id,
                    "paper_id": paper_id,
                    "section_type": section_type,
                    "section_title": section_title,
                    "section_path": list(chunk.meta.headings or []),
                    "para_index": i + 1,
                    "page_number": page_no,
                    "bbox": bbox_text,
                    "text_content": chunk.text,
                    "token_count": len(chunk.text.split()),
                })
        except Exception as e:
            print(f"   ⚠️  Chunking error: {e}")
            # Fallback: just get all text items
            for i, (item, level) in enumerate(doc.iterate_items()):
                if isinstance(item, TextItem):
                    bbox_page, bbox_text = self._prov_bbox([item])
                    paragraphs.append({
                        "para_id": f"{paper_id}_para_{i+1:04d}",
                        "paper_id": paper_id,
                        "section_type": "body",
                        "section_title": "",
                        "section_path": [],
                        "para_index": i + 1,
                        "page_number": bbox_page,
                        "bbox": bbox_text,
                        "text_content": item.text,
                        "token_count": len(item.text.split()),
                    })

        return paragraphs
    
    def _classify_section(self, headings: List[str]) -> str:
        """Classify section type from headings"""
        if not headings:
            return "body"
        
        last_heading = headings[-1].lower()
        
        # Simple classification based on keywords
        if any(kw in last_heading for kw in ["abstract", "summary"]):
            return "abstract"
        elif any(kw in last_heading for kw in ["introduction", "background", "intro"]):
            return "introduction"
        elif any(kw in last_heading for kw in ["method", "materials", "experiment"]):
            return "methods"
        elif any(kw in last_heading for kw in ["result", "finding"]):
            return "results"
        elif any(kw in last_heading for kw in ["discussion", "conclusion"]):
            return "discussion"
        elif any(kw in last_heading for kw in ["reference", "bibliography"]):
            return "references"
        elif any(kw in last_heading for kw in ["figure", "fig", "table"]):
            return "figure_caption"
        else:
            return "body"
    
    def _extract_figures(self, doc, paper_id: str) -> List[Dict[str, Any]]:
        """Extract figures and tables"""
        figures = []
        fig_index = 0
        tab_index = 0
        
        for item, level in doc.iterate_items():
            if isinstance(item, FigureItem):
                fig_index += 1
                fig_id = f"{paper_id}_fig_{fig_index}"
                
                # Get caption
                caption = ""
                if hasattr(item, 'caption') and item.caption:
                    caption = item.caption
                
                figures.append({
                    "figure_id": fig_id,
                    "paper_id": paper_id,
                    "figure_type": "figure",
                    "figure_number": str(fig_index),
                    "caption": caption,
                    "page_number": None,  # TODO: get from item
                    "image_path": "",  # TODO: save images
                })
            
            elif isinstance(item, TableItem):
                tab_index += 1
                tab_id = f"{paper_id}_tab_{tab_index}"
                
                caption = ""
                if hasattr(item, 'caption') and item.caption:
                    caption = item.caption
                
                figures.append({
                    "figure_id": tab_id,
                    "paper_id": paper_id,
                    "figure_type": "table",
                    "figure_number": str(tab_index),
                    "caption": caption,
                    "page_number": None,
                    "image_path": "",
                })
        
        return figures
    
    def _extract_references(self, doc, paper_id: str) -> List[Dict[str, Any]]:
        """Extract references (simple approach: find references section)"""
        # TODO: Use GROBID for better citation parsing later
        # For now, return empty list
        return []
