"""
Sci-Pal API Server — V25.8
Wraps the retrieval layer (hybrid search + rerank + query routing +
context expansion + multi-query + reference/boilerplate filtering +
graph traversal + agentic + chunking + metadata filters + communities)
as a REST API, with a minimal built-in frontend.

Usage:
  python api_server.py
  # then open http://localhost:5000
"""
import json
import os
import sys
import threading
from pathlib import Path
from typing import Optional, Dict
from flask import Flask, g, jsonify, request, send_from_directory, Response

# Ensure project root is on sys.path for services.* imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# V26.3: 导入任务管理器
from services.review.task_manager import task_manager

# B2b 试点：统一响应契约（仅这两个只读路由使用，其余路由暂不动）
from contracts import InternalError, fail, ok
from routes.abstracts import build_abstracts_blueprint
from routes.core import build_core_blueprint
from routes.data import build_data_blueprint
from routes.evidence import build_evidence_blueprint
from routes.guard import build_guard_blueprint
from routes.ingest import build_ingest_blueprint
from routes.papers import build_papers_blueprint
from routes.papers_actions import build_papers_actions_blueprint
from routes.protocols import build_protocols_blueprint
from routes.qa import build_qa_blueprint
from routes.references import build_references_blueprint
from routes.review_actions import build_review_actions_blueprint
from routes.reviews import build_reviews_blueprint
from routes.search import build_search_blueprint
from routes.search_downloads import build_search_downloads_blueprint
from routes.system import build_system_blueprint
from routes.systematic_review import build_systematic_review_blueprint
from routes.tasks import build_tasks_blueprint
from routes.tenancy import build_tenancy_blueprint
from routes.watch import build_watch_blueprint
from services.tenancy import bootstrap_default_workspace

DB_PATH = PROJECT_ROOT / "data" / "research.db"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
OUTLINE_DIR = PROJECT_ROOT / "data" / "outlines"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.secret_key = os.environ.get("SCIPAL_SECRET_KEY") or os.urandom(32)
try:
    bootstrap_default_workspace(db_path=DB_PATH)
except Exception:
    app.logger.exception("tenancy bootstrap failed")

# Optional bearer-token guard for remote deployment (single-user token today).
_API_TOKEN = os.environ.get("SCIPAL_API_TOKEN", "")
_TOKENS = {}
try:
    _TOKENS = json.loads(os.environ.get("SCIPAL_API_TOKENS", "{}") or "{}")
except json.JSONDecodeError:
    _TOKENS = {}
_SIGNED_PDF = os.environ.get("SCIPAL_REQUIRE_SIGNED_PDF", "0") == "1"


@app.before_request
def _require_api_token():
    g.owner = os.environ.get("SCIPAL_DEFAULT_OWNER", "default")
    path = request.path
    if not path.startswith("/api/"):
        return None
    if path in ("/api/health",):
        return None
    if path.endswith("/pdf") and request.args.get("token"):
        return None
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if _TOKENS:
        owner = _TOKENS.get(token)
        if not owner:
            return jsonify({"error": "unauthorized"}), 401
        g.owner = owner
        return None
    if _API_TOKEN:
        if token != _API_TOKEN:
            return jsonify({"error": "unauthorized"}), 401
    return None

# Lazy-loaded retrieval components (loaded on first request to keep startup fast)
_retriever = None
_hybrid = None
_graph = None
_review_generator = None
_llm_client = None
_qa_service = None
_hybrid_retriever = None  # V33.1: 混合检索器（本地+在线NCBI/PMC）


def get_qa_service():
    """Lazy-load Q&A service (V26.0: RAG 学术问答)。"""
    global _qa_service
    if _qa_service is None:
        from services.qa.qa_service import QAService
        # V33.17 C-3: 复用全局检索器单例，不再让 QAService 自建一套
        _qa_service = QAService(retriever=get_retriever())
    return _qa_service


def get_llm_client():
    """Lazy-load LLM client (V25.4: 支持 Ollama 和云端 OpenAI 兼容 API)。"""
    global _llm_client
    if _llm_client is None:
        from services.review.llm_client import create_llm_client
        _llm_client = create_llm_client()
    return _llm_client


# V33.17 C-2: 同步 /api/review/generate 用的是**共享单例**（会写 use_llm_verification，
# 并读取 _last_draft / _last_evidence_cards 这两个中间结果）。threaded=True 之后，
# 并发调用会互相覆盖参数与结果 → 用模块级锁把这条同步路径串行化。
# 注意：异步版 /api/review/generate_async **不用**这把锁 —— 它每个任务 new 私有实例，天然隔离。
_review_generate_lock = threading.Lock()


def get_review_generator():
    """Lazy-load ReviewGenerator (V25.0)."""
    global _review_generator
    if _review_generator is None:
        from services.review.review_generator import ReviewGenerator
        _review_generator = ReviewGenerator(
            llm_client=get_llm_client(),
            retriever=get_retriever(),
            use_llm_verification=False,
            db_path=str(DB_PATH),  # V25.3: 用于大纲生成时复用文献聚类信息
        )
    return _review_generator


_review_store = None


def get_review_store():
    """Lazy-load ReviewStore（V25.6: 综述结果暂存，用于前端点击溯源）。"""
    global _review_store
    if _review_store is None:
        from services.review.review_store import ReviewStore
        _review_store = ReviewStore(ttl_seconds=3600, max_entries=100)
    return _review_store


_outline_store = None


def get_outline_store():
    """Lazy-load OutlineStore（V25.9: 大纲保存/加载，文件级 JSON 存储）。"""
    global _outline_store
    if _outline_store is None:
        from services.review.outline_store import OutlineStore
        _outline_store = OutlineStore(data_dir=str(OUTLINE_DIR))
    return _outline_store


def get_retriever():
    global _retriever
    if _retriever is None:
        # V31.71: 回退到旧的统一检索器（unified_retriever.py），检索层不改，只改数据层
        from services.search.unified_retriever import UnifiedRetriever
        _retriever = UnifiedRetriever(
            rerank=True, routing=True, expand=True, graph_expand=True)
    return _retriever


def get_hybrid_retriever():
    """V33.1: Lazy-load 混合检索器（本地+在线NCBI/PMC）。"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        from services.search.hybrid_retriever import HybridRetriever
        _hybrid_retriever = HybridRetriever(use_online=True, verbose=True)
    return _hybrid_retriever


def get_graph():
    global _graph
    if _graph is None:
        from services.search.graph_traverser import GraphTraverser
        _graph = GraphTraverser()
    return _graph


# B3a: system 域只读路由（graph/stats、communities）已移入 routes/system.py
app.register_blueprint(
    build_system_blueprint(db_path=DB_PATH, get_graph=get_graph, log=app.logger)
)
# B3b: papers 域只读路由（列表/详情/引文邻居）已移入 routes/papers.py
app.register_blueprint(
    build_papers_blueprint(db_path=DB_PATH, get_graph=get_graph, log=app.logger)
)


def _download_task_manager():
    """Lazy accessor so routes/search.py never imports the download subsystem."""
    from services.search.online_downloader import get_task_manager

    return get_task_manager()


# B3c: 下载状态/历史/队列三条只读路由已移入 routes/search.py
app.register_blueprint(
    build_search_blueprint(
        get_task_manager=_download_task_manager,
        log=app.logger,
        get_hybrid_retriever=lambda: get_hybrid_retriever(),
    )
)

# B3d: 摘要库只读路由已移入 routes/abstracts.py
app.register_blueprint(
    build_abstracts_blueprint(db_path=PROJECT_ROOT / "data" / "abstracts.db")
)

# B4a: 综述查询（reviews 表，CLI/外部生成的综述对前端可见）
app.register_blueprint(
    build_reviews_blueprint(
        db_path=DB_PATH,
        log=app.logger,
        get_task_manager=lambda: task_manager,
        get_review_store=lambda: get_review_store(),
        get_llm_client=lambda: get_llm_client(),
    )
)

# B4a-2: 综述动作（大纲/保存/发配/生成）已移入 routes/review_actions.py
app.register_blueprint(
    build_review_actions_blueprint(
        get_task_manager=lambda: task_manager,
        get_llm_client=lambda: get_llm_client(),
        get_review_generator=lambda: get_review_generator(),
        get_review_store=lambda: get_review_store(),
        get_outline_store=lambda: get_outline_store(),
        get_retriever=lambda: get_retriever(),
        db_path=DB_PATH,
        log=app.logger,
    )
)

# B0: 健康检查 + 统一检索已移入 routes/core.py
app.register_blueprint(
    build_core_blueprint(db_path=DB_PATH, get_retriever=lambda: get_retriever())
)
app.register_blueprint(
    build_evidence_blueprint(
        db_path=DB_PATH, get_retriever=lambda: get_retriever(), log=app.logger
    )
)
app.register_blueprint(build_watch_blueprint(db_path=DB_PATH, log=app.logger))
app.register_blueprint(build_tenancy_blueprint(db_path=DB_PATH, log=app.logger))
app.register_blueprint(build_data_blueprint(db_path=DB_PATH, log=app.logger))
app.register_blueprint(build_systematic_review_blueprint(db_path=DB_PATH, log=app.logger))

# B3e: RAG 问答 + agentic 检索已移入 routes/qa.py
app.register_blueprint(
    build_qa_blueprint(
        get_qa_service=lambda: get_qa_service(),
        get_retriever=lambda: get_retriever(),
        get_task_manager=lambda: task_manager,
    )
)

# B5: papers 本地/解析/PDF/附件/导入/标注 已移入 routes/papers_actions.py
app.register_blueprint(
    build_papers_actions_blueprint(
        db_path=DB_PATH,
        project_root=PROJECT_ROOT,
        get_task_manager=lambda: task_manager,
        log=app.logger,
    )
)

# B5b: 在线下载任务 3 条路由已移入 routes/search_downloads.py
app.register_blueprint(
    build_search_downloads_blueprint(
        db_path=DB_PATH,
        project_root=PROJECT_ROOT,
        get_task_manager=lambda: task_manager,
        log=app.logger,
    )
)

_ingest_service = None


def get_ingest_service():
    """Lazy: importing ingest pulls chromadb/torch only when first used."""
    global _ingest_service
    if _ingest_service is None:
        import os

        from services.search.ingest import IngestService

        inline = os.environ.get("SCIPAL_INGEST_INLINE", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        _ingest_service = IngestService(
            db_path=DB_PATH,
            xml_dir=PROJECT_ROOT / "documents_xml",
            chroma_path=PROJECT_ROOT / "data" / "chroma",
            # inline 模式复用 Flask 已加载的嵌入模型（不新建 CUDA 上下文）
            embed_client=get_embed_rows() if inline else None,
            # 默认交给常驻 worker，Flask 进程只负责提交与查询
            queue_dir=None if inline else PROJECT_ROOT / "data" / "runs" / "_queue",
            log=app.logger.info,
        )
    return _ingest_service


def get_embed_rows():
    """Flask owns Chroma writes: the worker posts paragraphs here to be embedded."""

    def embed(rows: list[dict]) -> int:
        import chromadb

        from services.search.shared import get_shared_hybrid

        hybrid = get_shared_hybrid()
        client = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma"))
        collection = client.get_collection("paragraphs")
        documents = [str(row.get("text") or "") for row in rows]
        embeddings = hybrid.model.encode(documents, show_progress_bar=False).tolist()
        collection.add(
            ids=[str(row["para_id"]) for row in rows],
            documents=documents,
            metadatas=[
                {
                    "paper_id": str(row.get("paper_id") or ""),
                    "section_l1": str(row.get("section") or ""),
                    "section_l2": "",
                }
                for row in rows
            ],
            embeddings=embeddings,
        )
        return len(rows)

    return embed


# B4b: 异步“下载 + 入库 + 向量化”（只提交、立即返回 task_id）
app.register_blueprint(
    build_ingest_blueprint(
        get_service=get_ingest_service,
        log=app.logger,
        embed_rows=get_embed_rows(),
    )
)

_guard = None


def get_guard():
    """Lazy scipal-guard (PubTator3 lexicon + corpus FTS landing)."""
    global _guard
    if _guard is None:
        from services.quality.guard import FtsLanding, VocabularyGuard

        _guard = VocabularyGuard(fts_lookup=FtsLanding())
    return _guard


# B4c: guard 实体校验（/api/guard/check、/stats、/term/<t>）
app.register_blueprint(build_guard_blueprint(get_guard=get_guard, log=app.logger))

_reference_library = None


def get_reference_library():
    global _reference_library
    if _reference_library is None:
        from services.references.library import ReferenceLibrary

        _reference_library = ReferenceLibrary(DB_PATH)
    return _reference_library


# B4d: 参考文献互通（RIS / EndNote XML 导入 + 库列表）
app.register_blueprint(
    build_references_blueprint(get_library=get_reference_library, log=app.logger)
)

_protocol_service = None


def get_protocol_service():
    global _protocol_service
    if _protocol_service is None:
        from services.protocols.service import ProtocolService

        service = ProtocolService(DB_PATH)
        try:
            from services.search.protocols_io_client import ProtocolsIOClient

            client = ProtocolsIOClient()
            if client.is_enabled:
                service.client = client
        except Exception:  # noqa: BLE001 - token/config optional
            pass
        _protocol_service = service
    return _protocol_service


# B4e: protocols.io P1（导入 / 列表 / 详情 / 综述转草稿）
def get_review_repository():
    from services.review.review_repository import ReviewRepository

    return ReviewRepository(DB_PATH)


app.register_blueprint(
    build_protocols_blueprint(
        get_service=get_protocol_service,
        log=app.logger,
        get_review_repo=get_review_repository,
    )
)


def _unified_list_tasks(**kwargs):
    from services.unified_task_manager import list_tasks

    return list_tasks(**kwargs)


def _unified_get_task(task_id):
    """统一入口：先查 unified，再回退 review / export / ingest 三个任务库。"""
    from services.task_lookup import lookup_task

    found = lookup_task(task_id)
    return found["task"] if found else None


def _unified_subscribe(task_id):
    from services.unified_task_manager import subscribe

    return subscribe(task_id)


# B5: 统一任务只读路由（列表 / 详情 / SSE）已移入 routes/tasks.py
app.register_blueprint(
    build_tasks_blueprint(
        list_tasks=_unified_list_tasks,
        get_task=_unified_get_task,
        subscribe=_unified_subscribe,
    )
)


def get_hybrid():
    global _hybrid
    if _hybrid is None:
        # V33.20: 复用 UnifiedRetriever 的那套 HybridSearch（避免第二个嵌入模型）
        from services.search.shared import get_shared_hybrid

        _hybrid = get_shared_hybrid()
    return _hybrid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_filters(source) -> Optional[Dict]:
    """Parse V24.2 metadata filters from request args or JSON body."""
    filters = {}
    section = source.get("section") or source.get("section_l1")
    if section:
        filters["section_l1"] = section
    year_min = source.get("year_min")
    if year_min is not None and str(year_min).strip():
        try:
            filters["year_min"] = int(year_min)
        except (ValueError, TypeError):
            pass
    year_max = source.get("year_max")
    if year_max is not None and str(year_max).strip():
        try:
            filters["year_max"] = int(year_max)
        except (ValueError, TypeError):
            pass
    journal = source.get("journal")
    if journal:
        filters["journal"] = journal
    return filters if filters else None


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


# ============================================================
# V26.0: RAG Q&A 问答 API
# ============================================================


# papers 域只读路由（列表/详情/引文邻居）已迁入 routes/papers.py（B3b）


# paper_detail 已迁入 routes/papers.py（B3b）


# paper_graph 已迁入 routes/papers.py（B3b）


# ---------------------------------------------------------------------------
# V25.0: 综述生成智能体
# ---------------------------------------------------------------------------


# V25.11: 列出本地 documents 目录所有 PDF，标记是否已解析


@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(str(FRONTEND_DIR), path)


# ---------------------------------------------------------------------------
# Database migration (V25.15: 自动为已有数据库添加缺失字段)
# ---------------------------------------------------------------------------

def run_db_migrations():
    """启动时自动检查并添加缺失的数据库字段，幂等安全。"""
    if not DB_PATH.exists():
        return
    # V33.17: 函数内局部导入（项目风格）。此前缺失导致 name 'sqlite3' is not defined，
    # 异常被下面 try/except 吞掉，迁移从未真正执行过。
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        # 获取 papers 表现有列
        cursor.execute("PRAGMA table_info(papers)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        # 需要添加的字段
        missing = []
        for col in ["volume", "issue", "pages"]:
            if col not in existing_cols:
                missing.append(col)
        if missing:
            for col in missing:
                cursor.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT")
            conn.commit()
            print(f"🔧 数据库迁移完成: papers 表新增字段 {missing}")

        # V25.17: 检查 supplementary_files 表是否存在，不存在则创建
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='supplementary_files'")
        if not cursor.fetchone():
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS supplementary_files (
                supp_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT,
                file_path TEXT,
                file_size INTEGER,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
            )
            ''')
            conn.commit()
            print("🔧 数据库迁移完成: 新增 supplementary_files 表")

        # V33.12: 检查 tasks 表是否存在，不存在则创建
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                progress_text TEXT DEFAULT '',
                progress_pct REAL DEFAULT 0,
                params TEXT,
                result TEXT,
                error TEXT,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT
            )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at)")
            conn.commit()
            print("🔧 数据库迁移完成: 新增 tasks 表（统一任务表）")

        # V33.17: 段落 FTS 触发器修复（**既有缺陷**，不是 6-B 引入）。
        # 根因：`build_db/build_fts.py` 曾 DROP TABLE paragraphs_fts 后按 5 列重建
        # （section_l1 / section_l2），但 SQLite 的 DROP TABLE **不连带删触发器** ——
        # 库里 paragraphs_ai/ad/au 仍写 section_level1/2/3，于是 paragraphs 的任何
        # INSERT/UPDATE/DELETE 都报 `no column named section_level1`：
        # 前端「解析」按钮（同步 /api/papers/parse）、6-B 的 parse_async、
        # build_db/dedup_papers.py 的去重 DELETE 全挂。
        #
        # DDL 唯一真源在 build_db/build_fts.py 的 PARAGRAPHS_TRIGGER_DDL，
        # 这里只 import 函数来跑，**不另抄一份**。
        # 判据式检测：触发器插入 paragraphs_fts 的**目标列**与 FTS 表实际列不一致
        # 才重建 → 第二次启动不 DROP、不 CREATE、不打日志（幂等）。
        # 判据实现在 build_fts.paragraphs_triggers_need_fix()，不用
        # `"section_level1" in sql` 那种子串判断（新 DDL 里必然出现
        # `new.section_level1`，会永远判定需要修）。
        # 只碰这 3 个触发器，不动历史数据行、不 rebuild 存量 FTS。
        try:
            from build_db.build_fts import (
                paragraphs_triggers_need_fix,
                rebuild_paragraphs_triggers,
            )

            if paragraphs_triggers_need_fix(cursor):
                rebuild_paragraphs_triggers(cursor)
                conn.commit()
                print("🔧 触发器迁移：paragraphs_ai/ad/au 已按 section_l1|section_l2 重建")
        except Exception as fts_exc:
            # 与整个迁移函数策略一致：失败必须可见，但**不许阻塞启动**
            print(f"⚠️  触发器迁移失败（不影响启动）: {fts_exc}")

        conn.close()
    except Exception as e:
        print(f"⚠️  数据库迁移跳过（不影响运行）: {e}")


# ---------------------------------------------------------------------------
# V33.17-6A: 启动对账（review 僵尸任务收尸）
# ---------------------------------------------------------------------------

# 持久化任务类型白名单（6-A 名为 REVIEW_TASK_TYPES，6-B 加入 parse_paper 后改名）。
# ⚠️ **另一份在 `services/review/task_manager.py` 的 `PERSISTED_TASK_TYPES`，
#    两处值必须完全一致。**
# `download_online` 属于 services/search/online_downloader.py 的另一套任务体系，
# 虽然同表，但**永远不许**进这个白名单。
PERSISTED_TASK_TYPES = (
    "qa_ask",
    "agentic_search",
    "generate_outline",
    "generate_review",
    "parse_paper",
)


def reconcile_stale_review_tasks() -> int:
    """把上次进程遗留的**持久化** `running` 任务收成 `failed`。

    为什么必须做：这些任务（review 4 类 + 6-B 的 `parse_paper`）落 `tasks` 表。
    进程被杀时正在跑的任务会永远停在 `running` —— `/api/review/running_task`
    会一直返回它，前端误以为"还在跑"，新任务也难识别。

    范围**严格限定**在 `PERSISTED_TASK_TYPES`：
        qa_ask / agentic_search / generate_outline / generate_review / parse_paper
    `download_online` 等类型属于 services/search/online_downloader.py 的**另一套**
    任务体系，绝不能在这里被顺手改掉。

    幂等：没有 running 行时 rowcount=0，什么也不做；重复启动不报错。
    返回：被收掉的条数。
    """
    if not DB_PATH.exists():
        return 0

    import sqlite3
    from datetime import datetime

    placeholders = ",".join("?" for _ in PERSISTED_TASK_TYPES)
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        cursor = conn.execute(
            f"UPDATE tasks SET status='failed', error=?, finished_at=? "
            f"WHERE status = 'running' AND type IN ({placeholders})",
            (
                "服务重启导致任务中断",
                datetime.now().isoformat(timespec="seconds"),
                *PERSISTED_TASK_TYPES,
            ),
        )
        conn.commit()
        return cursor.rowcount
    except Exception as exc:
        # 表不存在 / 库被占用等都不许阻塞启动
        print(f"⚠️ 启动对账失败（不影响启动）：{exc}")
        return 0
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("SCIPAL_HOST", "0.0.0.0")
    port = int(os.environ.get("SCIPAL_PORT", "5000"))
    debug = os.environ.get("SCIPAL_DEBUG", "0") == "1"
    print(f"🧪 Sci-Pal API V33.17 — http://{host}:{port}")
    print(f"   DB: {DB_PATH}")
    print(f"   Frontend: {FRONTEND_DIR}")
    run_db_migrations()

    # V33.17-6A: 收掉上次进程遗留的任务。范围 = PERSISTED_TASK_TYPES
    # （6-B 起含 parse_paper，故措辞用「持久化任务」而非「review 任务」）
    _stale = reconcile_stale_review_tasks()
    print(
        f"🧹 启动对账：收掉 {_stale} 个遗留持久化任务（status→failed）"
        if _stale
        else "🧹 启动对账：无遗留持久化任务"
    )

    # V33.13: 启动时预热模型，避免第一次请求超时
    print("🔥 启动预热：加载模型...")
    try:
        get_retriever()
        print("  ✅ 检索模型已加载")
    except Exception as e:
        print(f"  ⚠️ 检索模型预热失败: {e}")
    try:
        get_llm_client()
        print("  ✅ LLM 客户端已加载")
    except Exception as e:
        print(f"  ⚠️ LLM 预热失败: {e}")
    print("🔥 预热完成，启动服务")

    # V33.17 C-2: threaded=True —— 不让一次同步重请求（review/generate、agentic/search、
    # qa/ask）把整站请求循环堵死。安全阀已先就位，顺序不能反：
    #   1) 异步任务每个 new 私有 ReviewGenerator 实例（参数/中间结果不共享）
    #   2) 同步 review/generate 由 _review_generate_lock 串行化（共享单例仍安全）
    app.run(host=host, port=port, debug=debug, threaded=True)
