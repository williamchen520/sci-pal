"""
AI Service
Main AI Q&A service with strong RAG:
1. Search across all tables
2. Build numbered envelope
3. Call LLM
4. Validate coverage
5. Retry if needed
"""
import os
from typing import Dict, Any
from .envelope_builder import EnvelopeBuilder
from .rag_validator import RAGValidator
from services.query.search_service import SearchService

class AIService:
    """Main AI Q&A service with strong RAG validation"""
    
    def __init__(self, max_retries: int = 2):
        self.search_service = SearchService()
        self.envelope_builder = EnvelopeBuilder()
        self.validator = RAGValidator(coverage_threshold=0.9)
        self.max_retries = max_retries
        
        # LLM config (will be configured from env)
        self.api_key = os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MODEL", "qwen-turbo")
        self.base_url = os.getenv("AI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    def ask(self, question: str, paper_id: str = None) -> Dict[str, Any]:
        """
        Ask a question and get an answer with strong RAG
        """
        print(f"🤖 AI Q&A: {question}")
        
        # Step 1: Search across all tables
        print("🔍 Step 1: Searching across all databases...")
        search_results = self.search_service.unified_search(question, top_k=10)
        
        item_counts = {
            "papers": len(search_results["papers"]),
            "text": len(search_results["text"]),
            "figures": len(search_results["figures"]),
            "citations": len(search_results["citations"]),
        }
        print(f"  Found: {item_counts}")
        
        # Step 2: Build envelope
        print("📦 Step 2: Building numbered envelope...")
        envelope = self.envelope_builder.build(search_results, question)
        print(f"  Total items: {envelope['total_items']}, required: {envelope['required_count']}")
        
        if envelope['required_count'] == 0:
            return {
                "answer": "I couldn't find any relevant information in the database for your question.",
                "sources": [],
                "coverage": 0.0,
                "attempts": 0
            }
        
        # Step 3: Call LLM with retries
        print("🧠 Step 3: Calling LLM...")
        prompt = envelope["prompt_context"]
        
        for attempt in range(1, self.max_retries + 2):
            print(f"  Attempt {attempt}/{self.max_retries + 1}")
            
            # Call LLM (stub for now - will connect to real API)
            ai_answer = self._call_llm(prompt)
            
            # Step 4: Validate coverage
            validation = self.validator.validate(ai_answer, envelope["required_item_ids"])
            print(f"  Coverage: {validation['coverage']*100:.1f}%")
            
            if validation["passed"]:
                print(f"  ✅ Validation passed on attempt {attempt}")
                return {
                    "answer": ai_answer,
                    "sources": envelope["items"],
                    "coverage": validation["coverage"],
                    "attempts": attempt,
                    "validation": validation
                }
            
            # If not passed and we have retries left, build retry prompt
            if attempt <= self.max_retries:
                print(f"  ⚠️  Missing: {validation['missing']}")
                prompt = self.validator.build_retry_prompt(prompt, validation["missing"])
        
        # If we exhausted retries, return what we have
        print(f"  ⚠️  Exhausted retries, returning best attempt")
        return {
            "answer": ai_answer,
            "sources": envelope["items"],
            "coverage": validation["coverage"],
            "attempts": self.max_retries + 1,
            "validation": validation,
            "warning": "Coverage below threshold"
        }
    
    def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM API using OpenAI-compatible interface
        Works with: DashScope (Qwen), OpenAI, DeepSeek, etc.
        """
        if not self.api_key:
            return self._stub_response(prompt)
        
        try:
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional research assistant. Answer questions based ONLY on the provided sources. Always cite source IDs like [T01], [P01] for every claim."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            return response.choices[0].message.content.strip()
            
        except ImportError:
            print("⚠️  openai package not installed, using stub response")
            return self._stub_response(prompt)
        except Exception as e:
            print(f"⚠️  LLM API error: {e}, using stub response")
            return self._stub_response(prompt)
    
    def _stub_response(self, prompt: str) -> str:
        """Fallback stub response when LLM is not configured"""
        text_count = len([x for x in prompt.split('\n') if x.startswith('[T')])
        paper_count = len([x for x in prompt.split('\n') if x.startswith('[P')])
        figure_count = len([x for x in prompt.split('\n') if x.startswith('[F')])
        citation_count = len([x for x in prompt.split('\n') if x.startswith('[C')])
        
        return f"""Based on the provided sources, here is my analysis:

The system retrieved the following information:
- {text_count} text passages from research papers
- {paper_count} paper metadata records
- {figure_count} figure captions
- {citation_count} citations

[This is a stub response. Configure your AI_API_KEY in environment variables to enable real AI Q&A.]
"""
