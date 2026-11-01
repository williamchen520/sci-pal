# API Reference

> This document records the signatures, parameters, return values, exceptions, and callers of all public functions.
> Verified line by line against the code; uncertain items are marked "TBD".

---

## 1. Retrieval Layer

### 1.1 UnifiedRetriever

**File**: `services/search/unified_retriever.py`

#### `__init__(rerank=True, routing=True, ...)`
- **Parameters**:
  - `rerank: bool = True` — whether to enable Cross-Encoder reranking
  - `routing: bool = True` — whether to enable query intent routing
  - Other parameters TBD (initialization loads HybridSearch, Reranker, QueryRouter, Diagnostics)
- **Returns**: A UnifiedRetriever instance
- **Exceptions**: Caught internally when model loading fails; not raised
- **Callers**: `api_server.py: get_retriever()` singleton
- **Reusable**: Yes

#### `retrieve(query, paper_id=None, top_paragraphs=6, top_figures=3, top_tables=2, top_papers=3, filters=None) -> Dict`
- **Parameters**:
  - `query: str` — the retrieval query
  - `paper_id: Optional[str]` — restrict retrieval to a single paper
  - `top_paragraphs: int = 6` — number of paragraphs to return
  - `top_figures: int = 3` — number of figures to return
  - `top_tables: int = 2` — number of tables to return
  - `top_papers: int = 3` — number of related papers to return
  - `filters: Optional[Dict]` — filter conditions `{section_l1, year_min, year_max, journal}`
- **Returns**: Dict containing keys such as `paragraphs`, `figures`, `tables`, `papers`, `route`, and `diagnostics`
- **Exceptions**: Handled internally; not propagated upward
- **Callers**:
  - `api_server.py: retrieve()` — `/api/retrieve` endpoint
  - `qa_service.py: ask()` — RAG question answering
- **Reusable**: Yes; this is the core retrieval entry point

#### `get_diagnostics_report() -> Optional[Dict]`
- **Returns**: The retrieval diagnostics report (if diagnostics are enabled)
- **Callers**: TBD
- **Reusable**: Yes

#### `to_envelope(query, paper_id=None, ...) -> Dict`
- **Returns**: Data in evidence envelope format
- **Callers**: TBD
- **Reusable**: Yes

---

### 1.2 HybridRetriever

**File**: `services/search/hybrid_retriever.py`

#### `__init__(use_online=True, online_max_results=30, use_protocols_io=True, protocols_io_max_results=10, verbose=True)`
- **Parameters**:
  - `use_online: bool = True` — whether to enable NCBI online search
  - `online_max_results: int = 30` — maximum results per database for online search
  - `use_protocols_io: bool = True` — whether to enable Protocols.io
  - `protocols_io_max_results: int = 10` — maximum Protocols.io results
  - `verbose: bool = True` — whether to print logs
- **Exceptions**: Caught internally and logged as warnings when a submodule fails to load
- **Callers**: `api_server.py: get_hybrid_retriever()` singleton
- **Reusable**: Yes

#### `search_papers(query, top_k=20, use_online=None, online_max_results=None, use_protocols_io=None, protocols_io_max_results=None) -> Dict`
- **Parameters**:
  - `query: str` — search keywords
  - `top_k: int = 20` — maximum number of papers to return
  - `use_online: Optional[bool]` — overrides the initialization setting
  - `online_max_results: Optional[int]` — overrides the initialization setting
  - `use_protocols_io: Optional[bool]` — overrides the initialization setting
  - `protocols_io_max_results: Optional[int]` — overrides the initialization setting
- **Returns**:
  ```python
  {
      "query": str,
      "total": int,
      "local_count": int,
      "online_count": int,
      "online_in_local_count": int,
      "papers": List[Dict],      # merged and deduplicated, sorted by score descending
      "local_papers": List[Dict],
      "online_papers": List[Dict],
      "protocols": List[Dict],   # Protocols.io experimental methods
      "protocols_count": int,
  }
  ```
- **Exceptions**: Handled internally; not propagated upward
- **Callers**: `api_server.py: hybrid_search_api()` — `/api/search/hybrid` endpoint
- **Reusable**: Yes; this is the core entry point for hybrid search

---

### 1.3 OnlineSearcher

**File**: `services/search/online_search.py`

#### `OnlineSearchResult` (dataclass)
- **Fields**: pmid, pmcid, title, authors, journal, pubdate, abstract, doi, url, source_db
- **Methods**: `to_dict() -> Dict`

#### `__init__(...)`
- **Parameters**: TBD (includes NCBI API key, email, cache directory, rate-limit settings)
- **Callers**: `get_online_searcher()` singleton, HybridRetriever

#### `search_pubmed(query, max_results=50) -> List[OnlineSearchResult]`
- **Parameters**:
  - `query: str` — search terms
  - `max_results: int = 50`
- **Returns**: A list of OnlineSearchResult
- **Exceptions**: Retried on network errors; returns an empty list on failure
- **Reusable**: Yes

#### `search_pmc(query, max_results=50) -> List[OnlineSearchResult]`
- **Parameters**: Same as above
- **Returns**: Same as above
- **Reusable**: Yes

#### `search(query, max_results=50, search_pubmed=True, search_pmc=True) -> List[OnlineSearchResult]`
- **Parameters**:
  - `query: str`
  - `max_results: int = 50` — maximum number of results per database
  - `search_pubmed: bool = True`
  - `search_pmc: bool = True`
- **Returns**: Merged PubMed + PMC results (not deduplicated; deduplication is done by HybridRetriever)
- **Callers**: HybridRetriever, the online search endpoints in api_server.py
- **Reusable**: Yes

---

### 1.4 ProtocolsIOClient

**File**: `services/search/protocols_io_client.py`

#### `ProtocolsIOResult` (dataclass)
- **Fields**: protocol_id, title, authors, description, doi, uri, url, number_of_steps, published_on, created_on, creator_name, creator_username, source, is_protocol, year
- **Methods**: `to_dict() -> Dict`, `from_api_response(item) -> ProtocolsIOResult` (classmethod)

#### `__init__(token=None, cache_dir=None, rate_limit=1.0, max_retries=3)`
- **Parameters**:
  - `token: Optional[str]` — if omitted, read from the `SCIPAL_PROTOCOLS_IO_TOKEN` environment variable
  - `cache_dir: Optional[Path]` — defaults to `data/protocols_io_cache`
- **Callers**: HybridRetriever

#### `is_enabled -> bool` (property)
- **Returns**: Whether a token is present and the client is not disabled by an environment variable
- **Reusable**: Yes

#### `search(query, max_results=10, order_field="activity", order_dir="desc") -> List[ProtocolsIOResult]`
- **Parameters**:
  - `query: str`
  - `max_results: int = 10` — maximum 50
  - `order_field: str = "activity"` — activity/date/name/id
  - `order_dir: str = "desc"`
- **Returns**: A list of ProtocolsIOResult
- **Exceptions**: Retried on network errors; returns an empty list if the token is invalid
- **Reusable**: Yes

#### `get_protocol(protocol_id: int) -> Optional[Dict]`
- **Parameters**: `protocol_id: int`
- **Returns**: Protocol details; returns None on failure
- **Reusable**: Yes

#### `search_and_format(query, max_results=10) -> str`
- **Returns**: Formatted text (exact format TBD)
- **Reusable**: TBD

---

### 1.5 OnlineDownloader

**File**: `services/search/online_downloader.py`

#### `DownloadTask` (dataclass)
- **Fields**: task_id, pmc_ids, status, progress, created_at, completed_at, error, results
- **Methods**: `to_dict() -> Dict`

#### `DownloadTaskManager`
- Manages the download task queue and persists tasks to disk
- **Methods**: `create_task(pmc_ids) -> DownloadTask`, `get_task(task_id) -> Optional[DownloadTask]`, `list_tasks(limit=20) -> List[Dict]`, `get_queue_status() -> Dict`, `clear_history() -> int`

#### `start_download(pmc_ids: List[str]) -> str`
- **Parameters**: `pmc_ids: List[str]` — for example `["PMC1234567"]`
- **Returns**: `task_id: str`, used to query progress
- **Notes**: Runs asynchronously and returns immediately; a background thread completes download → import → index building
- **Callers**: `api_server.py: download_online()` — `/api/search/download_online` endpoint
- **Reusable**: Yes

---

## 2. Review Layer

### 2.1 ReviewGenerator

**File**: `services/review/review_generator.py`

#### `__init__(...)`
- **Parameters**: TBD (includes retriever, evidence_extractor, llm_client, outline_store, etc.)
- **Callers**: `api_server.py: get_review_generator()` singleton

#### `generate(topic, max_papers=20, outline=None, citation_style="apa", review_type="narrative", custom_outline=None, language="en", include_abstracts=True, selected_paper_ids=None, excluded_paper_ids=None) -> ReviewOutput`
- **Parameters**:
  - `topic: str` — review topic
  - `max_papers: int = 20` — maximum number of papers to retrieve
  - `outline: Optional[ReviewOutline]` — user-defined outline object
  - `citation_style: str = "apa"` — apa/nature/vancouver
  - `review_type: str = "narrative"` — narrative/comparative/systematic
  - `custom_outline: Optional[dict]` — paragraph-level custom outline JSON
  - `language: str = "en"` — en/zh
  - `include_abstracts: bool = True` — whether to include the abstract library
  - `selected_paper_ids: Optional[list[str]]` — use only the specified papers
  - `excluded_paper_ids: Optional[list[str]]` — exclude the specified papers
- **Returns**: ReviewOutput (including the full Markdown text, references, statistics, and warnings)
- **Exceptions**: Handled internally; warnings are returned through ReviewOutput.warnings
- **Callers**: `api_server.py: generate_review()` — `/api/review/generate` endpoint
- **Reusable**: Yes

#### `generate_outline(topic, ...) -> ReviewOutline`
- **Parameters**: TBD
- **Returns**: A ReviewOutline object
- **Callers**: `api_server.py: generate_outline()` — `/api/review/outline` endpoint
- **Reusable**: Yes

#### `get_insufficient_evidence_sections() -> list[str]`
- **Returns**: A list of section titles with insufficient evidence
- **Reusable**: Yes

---

### 2.2 EvidenceExtractor

**File**: `services/review/evidence_extractor.py`

#### `__init__(...)`
- **Parameters**: TBD (includes llm_client, cache directory, minimum paragraph length, etc.)

#### `extract_from_paragraphs(paragraphs, topic="", language="en") -> list[EvidenceCard]`
- **Parameters**:
  - `paragraphs: list[dict]` — each dict contains `para_id`, `paper_id`, and `text`, and optionally `section_l1`, `page`, `paper_title`, `source_type`, `match_method`, `rerank_score`, `retrieval_rank`
  - `topic: str = ""` — review topic
  - `language: str = "en"` — en/zh
- **Returns**: A list of EvidenceCard (already deduplicated, sorted by overall quality score in descending order)
- **Notes**: V33.4 adds exact deduplication (paper_id+para_id), source/match metadata, and confidence calculation
- **Callers**: ReviewGenerator
- **Reusable**: Yes

---

### 2.3 LLMClient

**File**: `services/review/llm_client.py`

#### `LLMError(Exception)`
- Exception raised on LLM calls

#### `__init__(...)`
- **Parameters**: TBD (includes provider, model, host, api_key, temperature, max_retries, timeout)

#### `is_available() -> bool`
- **Returns**: Whether the LLM service is available
- **Reusable**: Yes

#### `list_models() -> list[str]`
- **Returns**: A list of available models
- **Reusable**: Yes

#### `chat(system_prompt, user_prompt, temperature=None) -> str`
- **Parameters**:
  - `system_prompt: str`
  - `user_prompt: str`
  - `temperature: Optional[float]` — overrides the default temperature
- **Returns**: The text generated by the model
- **Exceptions**: `LLMError` — service unavailable or retries exhausted
- **Callers**: ReviewGenerator, QAService, EvidenceExtractor
- **Reusable**: Yes; this is the core entry point for LLM calls

#### `chat_json(system_prompt, user_prompt, ...) -> dict`
- **Parameters**: TBD
- **Returns**: The parsed JSON dict
- **Exceptions**: LLMError, JSON parse failure (TBD)
- **Reusable**: Yes

---

### 2.4 OutlineStore

**File**: `services/review/outline_store.py`

#### `__init__(data_dir="data/outlines")`
- **Parameters**: `data_dir: str` — outline storage directory

#### `save(name, outline) -> None`
- **Parameters**: `name: str`, `outline: dict`
- **Reusable**: Yes

#### `load(name) -> Optional[dict]`
- **Returns**: The outline dict, or None if it does not exist
- **Reusable**: Yes

#### `list() -> list[dict]`
- **Returns**: A list of metadata for all saved outlines
- **Reusable**: Yes

#### `delete(name) -> bool`
- **Returns**: Whether the deletion succeeded
- **Reusable**: Yes

#### `exists(name) -> bool`
- **Reusable**: Yes

---

### 2.5 ReviewStore

**File**: `services/review/review_store.py`

#### `__init__(ttl_seconds=3600, max_entries=100)`
- **Parameters**: In-memory cache TTL and maximum number of entries

#### `store(review_id, data) -> None`
- **Reusable**: Yes

#### `get(review_id) -> Optional[dict]`
- **Reusable**: Yes

#### `get_sentence(review_id, sentence_id) -> Optional[dict]`
- **Reusable**: Yes

#### `get_evidence(review_id, evidence_id) -> Optional[dict]`
- **Reusable**: Yes

#### `stats() -> dict`
- **Reusable**: Yes

---

### 2.6 TaskManager

**File**: `services/review/task_manager.py`

#### `create_task(task_type: str) -> str`
- **Returns**: task_id
- **Reusable**: Yes

#### `get_task(task_id) -> Optional[Dict]`
- **Reusable**: Yes

#### `cancel_task(task_id) -> bool`
- **Reusable**: Yes

#### `complete_task(task_id, result) -> None`
- **Reusable**: Yes

#### `fail_task(task_id, error) -> None`
- **Reusable**: Yes

#### `is_cancelled(task_id) -> bool`
- **Reusable**: Yes

#### `update_progress(task_id, progress) -> None`
- **Reusable**: Yes

#### `get_running_task() -> Optional[Dict]`
- **Reusable**: Yes

---

## 3. Q&A Layer

### QAService

**File**: `services/qa/qa_service.py`

#### `__init__(...)`
- **Parameters**: TBD (includes retriever, llm_client, top_paragraphs, top_figures)

#### `llm() -> LLMClient` (property)
- **Reusable**: Yes

#### `is_llm_available() -> bool`
- **Reusable**: Yes

#### `get_llm_status() -> Dict[str, Any]`
- **Returns**: LLM status information (provider, model, availability)
- **Reusable**: Yes

#### `ask(question, paper_id=None, include_diagnostics=False) -> Dict[str, Any]`
- **Parameters**:
  - `question: str`
  - `paper_id: Optional[str]` — restrict to a single paper
  - `include_diagnostics: bool = False`
- **Returns**:
  ```python
  {
      "answer": str,
      "citations": list,
      "sources": {paragraphs, figures, papers},
      "llm_provider": str,
      "llm_model": str,
      "diagnostics": dict,  # optional
  }
  ```
- **Exceptions**: Handled internally; returned through the `error` field of the returned dict
- **Callers**: `api_server.py: qa_ask()` — `/api/qa/ask` endpoint
- **Reusable**: Yes

---

## 4. API Routes (Flask)

### 4.1 Retrieval

| Route | Method | Handler | Notes |
|------|------|----------|------|
| `/api/health` | GET | `health()` | Health check |
| `/api/retrieve` | GET/POST | `retrieve()` | Unified retrieval (paragraphs/figures/tables) |
| `/api/search/hybrid` | GET/POST | `hybrid_search_api()` | Hybrid search (local + online + Protocols.io) |
| `/api/search/online` | GET/POST | `online_search_api()` | NCBI online search only |

### 4.2 Q&A

| Route | Method | Handler | Notes |
|------|------|----------|------|
| `/api/qa/ask` | POST | `qa_ask()` | RAG question answering |
| `/api/qa/status` | GET | `qa_status()` | LLM status |

### 4.3 Review

| Route | Method | Handler | Notes |
|------|------|----------|------|
| `/api/review/outline` | GET/POST | `generate_outline()` | Generate outline |
| `/api/review/generate` | GET/POST | `generate_review()` | Generate review |
| `/api/review/<review_id>` | GET | `get_review_detail()` | Get review details |
| `/api/review/running_task` | GET | `get_running_task()` | Currently running task |
| `/api/review/task/<task_id>` | GET | `get_task_status()` | Task status |
| `/api/review/cancel/<task_id>` | POST | `cancel_task()` | Cancel task |
| `/api/review/assign_papers` | POST | `assign_papers_to_outline_route()` | Assign papers to outline sections |
| `/api/review/search_and_assign` | POST | `search_and_assign_route()` | Search and assign papers by section |
| `/api/review/outline/saved` | GET | `list_saved_outlines()` | List saved outlines |
| `/api/review/outline/save` | POST | `save_outline()` | Save outline |
| `/api/review/outline/saved/<name>` | GET/DELETE | `load_saved_outline()` / `delete_saved_outline()` | Load/delete outline |
| `/api/review/llm_status` | GET | `review_llm_status()` | LLM status |

### 4.4 Downloads

| Route | Method | Handler | Notes |
|------|------|----------|------|
| `/api/search/download_online` | POST | `download_online()` | Start online download |
| `/api/search/download_status` | GET | `download_status()` | Download progress |
| `/api/search/download_history` | GET | `download_history()` | Download history |
| `/api/search/download_queue` | GET | `download_queue_status()` | Download queue status |
| `/api/search/retry_download` | POST | `retry_download()` | Retry failed downloads |
| `/api/search/clear_download_history` | POST | `clear_download_history()` | Clear history |

### 4.5 Papers

| Route | Method | Handler | Notes |
|------|------|----------|------|
| `/api/papers` | GET | `list_papers()` | Paper list |
| `/api/papers/<paper_id>` | GET | `paper_detail()` | Paper details |
| `/api/papers/local` | GET | `list_local_papers()` | Local paper list |
| `/api/papers/<paper_id>/pdf` | GET | `serve_pdf()` | Retrieve PDF |
| `/api/papers/parse` | POST | `parse_local_paper()` | Parse local paper |
| `/api/papers/import` | POST | `import_paper()` | Import paper |
| `/api/papers/<paper_id>/graph` | GET | `paper_graph()` | Paper citation graph |
| `/api/papers/<paper_id>/annotate` | POST | `annotate_pdf()` | PDF annotation |
| `/api/papers/<paper_id>/annotations` | GET | `list_pdf_annotations()` | Annotation list |

### 4.6 Other

| Route | Method | Handler | Notes |
|------|------|----------|------|
| `/api/abstracts/list` | GET | `list_abstracts()` | Abstract list |
| `/api/abstracts/<paper_id>` | GET | `get_abstract()` | Abstract details |
| `/api/graph/stats` | GET | `graph_stats()` | Graph statistics |
| `/api/communities` | GET | `list_communities()` | Community detection |
| `/api/agentic/search` | GET/POST | `agentic_search()` | Agentic search |
