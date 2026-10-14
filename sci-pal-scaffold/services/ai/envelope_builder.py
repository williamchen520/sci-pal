"""
Envelope Builder
Takes unified search results and converts them into numbered items for the LLM
This is the same pattern we perfected in the etymology project
"""
from typing import Dict, List, Any

class EnvelopeBuilder:
    """Build numbered envelope items from search results"""
    
    def build(self, search_results: Dict[str, List], question: str) -> Dict[str, Any]:
        """
        Convert unified search results into numbered envelope items
        
        Returns:
            {
                "items": [...],
                "required_item_ids": [...],
                "prompt_context": "formatted text for LLM"
            }
        """
        items = []
        required_ids = []
        counter = {
            "paper": 0,
            "text": 0,
            "figure": 0,
            "citation": 0
        }
        
        # ============================================================
        # 1. Paper metadata items
        # ============================================================
        for i, paper in enumerate(search_results.get("papers", [])):
            counter["paper"] += 1
            item_id = f"P{counter['paper']:02d}"
            
            item = {
                "id": item_id,
                "type": "paper",
                "required": True,
                "content": f"{paper.get('title', 'Unknown')} ({paper.get('year', 'n.d.')}) - {paper.get('authors', 'Unknown')}",
                "paper_id": paper.get("paper_id"),
                "data": paper
            }
            items.append(item)
            required_ids.append(item_id)
        
        # ============================================================
        # 2. Text paragraph items
        # ============================================================
        for i, para in enumerate(search_results.get("text", [])):
            counter["text"] += 1
            item_id = f"T{counter['text']:02d}"
            
            item = {
                "id": item_id,
                "type": "text",
                "required": True,
                "content": para.get("snippet", para.get("text_content", "")),
                "paper_id": para.get("paper_id"),
                "section": para.get("section_name"),
                "page": para.get("page_number"),
                "data": para
            }
            items.append(item)
            required_ids.append(item_id)
        
        # ============================================================
        # 3. Figure items
        # ============================================================
        for i, fig in enumerate(search_results.get("figures", [])):
            counter["figure"] += 1
            item_id = f"F{counter['figure']:02d}"
            
            item = {
                "id": item_id,
                "type": "figure",
                "required": False,  # Optional, nice to cite
                "content": fig.get("caption", ""),
                "paper_id": fig.get("paper_id"),
                "page": fig.get("page_number"),
                "data": fig
            }
            items.append(item)
        
        # ============================================================
        # 4. Citation items
        # ============================================================
        for i, cit in enumerate(search_results.get("citations", [])):
            counter["citation"] += 1
            item_id = f"C{counter['citation']:02d}"
            
            item = {
                "id": item_id,
                "type": "citation",
                "required": False,  # Optional, nice to cite
                "content": f"{cit.get('author', '')} ({cit.get('year', 'n.d.')}). {cit.get('title', '')}. {cit.get('journal', '')}",
                "paper_id": cit.get("paper_id"),
                "data": cit
            }
            items.append(item)
        
        # Build prompt context text
        prompt_context = self._build_prompt_context(items, required_ids, question)
        
        return {
            "items": items,
            "required_item_ids": required_ids,
            "total_items": len(items),
            "required_count": len(required_ids),
            "prompt_context": prompt_context
        }
    
    def _build_prompt_context(self, items: List[Dict], required_ids: List[str], question: str) -> str:
        """Build the formatted prompt context for the LLM"""
        
        lines = [
            "You are a research assistant. Answer the user's question based ONLY on the numbered items below.",
            "",
            "## RULES (must follow strictly):",
            "1. All facts MUST come from the numbered items below - do not use your own knowledge",
            f"2. You MUST cover ALL required items: {', '.join(required_ids)}",
            "3. Every claim MUST cite the item ID (e.g., [T01], [P01])",
            "4. If information is missing, say so explicitly - do not make things up",
            "5. If the question cannot be answered from the items, say 'I don't have enough information from the provided sources'",
            "",
            "## NUMBERED ITEMS:",
        ]
        
        for item in items:
            required_mark = " [REQUIRED]" if item["id"] in required_ids else " [optional]"
            lines.append(f"[{item['id']}] {item['type'].upper()}{required_mark}")
            lines.append(f"  {item['content'][:300]}")
            if item.get("paper_id"):
                lines.append(f"  (Source paper: {item['paper_id']})")
            lines.append("")
        
        lines.append("## USER QUESTION:")
        lines.append(question)
        lines.append("")
        lines.append("## YOUR ANSWER:")
        lines.append("(Remember to cite item IDs like [T01] for every claim)")
        
        return "\n".join(lines)
