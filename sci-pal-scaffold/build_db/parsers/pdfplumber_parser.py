"""
pdfplumber Table Parser Wrapper
Best for complex table extraction
"""
import os
from typing import Dict, List, Any
from .base_parser import BaseParser

class PdfPlumberParser(BaseParser):
    """Wrapper around pdfplumber for table extraction"""
    
    def __init__(self):
        self.name = "pdfplumber"
    
    def get_parser_name(self) -> str:
        return self.name
    
    def parse(self, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        """
        Extract tables with pdfplumber
        Returns: {
            "tables": [...]
        }
        """
        print(f"📊 Extracting tables from {os.path.basename(pdf_path)} with pdfplumber...")
        
        try:
            import pdfplumber
            
            tables = []
            table_index = 0
            
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract tables from this page
                    page_tables = page.extract_tables()
                    
                    for table_data in page_tables:
                        if len(table_data) < 2:  # Skip empty/tiny tables
                            continue
                        
                        table_index += 1
                        table_id = f"{paper_id}_tab{table_index:03d}"
                        
                        tables.append({
                            "table_id": table_id,
                            "paper_id": paper_id,
                            "page_number": page_num,
                            "caption": f"Table {table_index}",
                            "table_data": table_data,
                            "parser_source": "pdfplumber"
                        })
            
            print(f"  Found {len(tables)} tables")
            
            return {"tables": tables}
            
        except ImportError:
            print("⚠️  pdfplumber not installed. Run: pip install pdfplumber")
            return {"tables": []}
        except Exception as e:
            print(f"⚠️  pdfplumber error: {e}")
            return {"tables": []}
