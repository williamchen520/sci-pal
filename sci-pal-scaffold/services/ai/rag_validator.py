"""
RAG Validator
Checks if AI output actually cited all required items
Same pattern as etymology project
"""
import re
from typing import Dict, List, Tuple

class RAGValidator:
    """Validate AI output coverage of required items"""
    
    def __init__(self, coverage_threshold: float = 0.9):
        self.coverage_threshold = coverage_threshold
    
    def validate(self, ai_output: str, required_item_ids: List[str]) -> Dict:
        """
        Validate AI output covers all required items
        
        Returns:
            {
                "passed": bool,
                "coverage": float,
                "covered": List[str],
                "missing": List[str],
                "message": str
            }
        """
        if not ai_output or not ai_output.strip():
            return {
                "passed": False,
                "coverage": 0.0,
                "covered": [],
                "missing": required_item_ids,
                "message": "AI output is empty"
            }
        
        # Find all cited item IDs in the output
        cited_ids = self._extract_citations(ai_output)
        
        # Check which required items are covered
        covered = [item_id for item_id in required_item_ids if item_id in cited_ids]
        missing = [item_id for item_id in required_item_ids if item_id not in cited_ids]
        
        coverage = len(covered) / len(required_item_ids) if required_item_ids else 1.0
        
        passed = coverage >= self.coverage_threshold
        
        message = f"Coverage: {coverage*100:.1f}% ({len(covered)}/{len(required_item_ids)})"
        if not passed:
            message += f" - Missing: {', '.join(missing)}"
        
        return {
            "passed": passed,
            "coverage": coverage,
            "covered": covered,
            "missing": missing,
            "message": message
        }
    
    def _extract_citations(self, text: str) -> set:
        """Extract all cited item IDs from AI output"""
        # Match patterns like [T01], [P02], [F03], [C04]
        pattern = r'\[([TPFC]\d{2})\]'
        matches = re.findall(pattern, text)
        return set(matches)
    
    def build_retry_prompt(self, original_prompt: str, missing_items: List[str]) -> str:
        """Build a retry prompt that tells the AI what it missed"""
        retry_addition = f"""

## IMPORTANT - YOUR PREVIOUS ANSWER WAS INCOMPLETE:
You forgot to cite the following required items: {', '.join(missing_items)}

Please revise your answer to INCLUDE analysis of ALL these missing items.
Each of these MUST have explicit discussion and citation in your answer.
"""
        return original_prompt + retry_addition
