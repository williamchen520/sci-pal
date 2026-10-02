"""
Base Parser Interface
All parsers must implement this interface
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any

class BaseParser(ABC):
    """Abstract base class for all PDF parsers"""
    
    @abstractmethod
    def parse(self, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        """
        Parse a PDF file and return structured results
        
        Args:
            pdf_path: Path to the PDF file
            paper_id: Unique paper identifier
            
        Returns:
            Dict with parsed content in standardized format
        """
        pass
    
    @abstractmethod
    def get_parser_name(self) -> str:
        """Return the name of this parser"""
        pass
