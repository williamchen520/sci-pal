#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sci-Pal 系统自检脚本 V33.4
用途：检查系统配置、依赖、数据库、模型等是否正常，确保系统可以运行
使用：python self_check.py [--verbose]
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# 颜色定义（ANSI）
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'

# 全局统计
stats = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}


def print_header(title):
    """打印章节标题"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}  {title}{Colors.NC}")
    print(f"{Colors.BLUE}{'='*70}{Colors.NC}\n")


def check_pass(msg):
    print(f"  {Colors.GREEN}✅ PASS{Colors.NC}: {msg}")
    stats["pass"] += 1


def check_fail(msg):
    print(f"  {Colors.RED}❌ FAIL{Colors.NC}: {msg}")
    stats["fail"] += 1


def check_warn(msg):
    print(f"  {Colors.YELLOW}⚠️  WARN{Colors.NC}: {msg}")
    stats["warn"] += 1


def check_skip(msg):
    print(f"  {Colors.CYAN}⏭️  SKIP{Colors.NC}: {msg}")
    stats["skip"] += 1


def get_project_root():
    """获取项目根目录"""
    return Path(__file__).parent.resolve()


# =============================================================================
# 检查 1: Python 环境
# =============================================================================

def check_python_env():
    print_header("检查 1: Python 环境")

    # Python 版本
    version = sys.version_info
    print(f"  Python 版本: {version.major}.{version.minor}.{version.micro}")
    if version.major >= 3 and version.minor >= 10:
        check_pass(f"Python 版本符合要求 (>=3.10)")
    else:
        check_fail(f"Python 版本过低，需要 >=3.10，当前 {version.major}.{version.minor}")

    # 虚拟环境
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        check_pass(f"运行在虚拟环境中: {sys.prefix}")
    else:
        check_warn("未使用虚拟环境，建议使用 venv 或 conda")

    # 工作目录
    cwd = os.getcwd()
    print(f"  当前工作目录: {cwd}")


# =============================================================================
# 检查 2: 项目结构
# =============================================================================

def check_project_structure():
    print_header("检查 2: 项目结构")

    root = get_project_root()

    # 关键目录
    required_dirs = ["services", "frontend", "data", "build_db"]
    optional_dirs = ["documents_xml", "abstracts_xml", "models", "tests", "abstracts_protocols", "documents_protocols"]

    for d in required_dirs:
        path = root / d
        if path.is_dir():
            check_pass(f"目录 {d}/ 存在")
        else:
            check_fail(f"目录 {d}/ 不存在")

    for d in optional_dirs:
        path = root / d
        if path.is_dir():
            check_pass(f"目录 {d}/ 存在（可选）")
        else:
            check_skip(f"目录 {d}/ 不存在（可选）")

    # 关键文件
    key_files = [
        "api_server.py",
        "requirements.txt",
        "README.md",
        "WORK_LOG.md",
        "services/review/models.py",
        "services/review/review_generator.py",
        "services/review/evidence_extractor.py",
        "services/search/unified_retriever.py",
        "download_protocols.py",
    ]

    for f in key_files:
        path = root / f
        if path.is_file():
            size = path.stat().st_size
            check_pass(f"文件 {f} 存在 ({size:,} bytes)")
        else:
            check_fail(f"文件 {f} 不存在")


# =============================================================================
# 检查 3: Python 依赖包
# =============================================================================

def check_dependencies():
    print_header("检查 3: Python 依赖包")

    required_packages = [
        ("flask", "Web 框架"),
        ("pydantic", "数据验证"),
        ("chromadb", "向量数据库"),
        ("sentence_transformers", "Embedding 模型"),
        ("spacy", "NER 实体识别"),
        ("sqlite3", "SQLite 数据库（标准库）"),
    ]

    optional_packages = [
        ("torch", "PyTorch（GPU 加速）"),
        ("transformers", "HuggingFace Transformers"),
        ("pdfplumber", "PDF 解析"),
        ("docling", "Docling 文档解析"),
        ("ollama", "Ollama LLM 客户端"),
        ("requests", "HTTP 请求"),
        ("numpy", "数值计算"),
    ]

    print("  必需包:")
    for pkg, desc in required_packages:
        try:
            if pkg == "sqlite3":
                import sqlite3
                version = sqlite3.sqlite_version
            else:
                mod = __import__(pkg)
                version = getattr(mod, "__version__", "unknown")
            check_pass(f"{pkg} ({desc}) - v{version}")
        except ImportError:
            check_fail(f"{pkg} ({desc}) - 未安装")

    print("\n  可选包:")
    for pkg, desc in optional_packages:
        try:
            mod = __import__(pkg)
            version = getattr(mod, "__version__", "unknown")
            check_pass(f"{pkg} ({desc}) - v{version}")
        except ImportError:
            check_skip(f"{pkg} ({desc}) - 未安装（可选）")


# =============================================================================
# 检查 4: 数据库
# =============================================================================

def check_databases():
    print_header("检查 4: 数据库")

    root = get_project_root()
    data_dir = root / "data"

    if not data_dir.is_dir():
        check_warn("data/ 目录不存在，跳过数据库检查")
        return

    # 全文数据库
    research_db = data_dir / "research.db"
    if research_db.is_file():
        size_mb = research_db.stat().st_size / (1024 * 1024)
        try:
            conn = sqlite3.connect(str(research_db))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM papers")
            paper_count = cursor.fetchone()[0]
            conn.close()
            check_pass(f"research.db 可连接，{len(tables)} 个表，{paper_count:,} 篇论文 ({size_mb:.1f} MB)")
        except Exception as e:
            check_fail(f"research.db 连接失败: {e}")
    else:
        check_warn("research.db 不存在（需要先建库）")

    # 摘要数据库
    abstracts_db = data_dir / "abstracts.db"
    if abstracts_db.is_file():
        size_mb = abstracts_db.stat().st_size / (1024 * 1024)
        try:
            conn = sqlite3.connect(str(abstracts_db))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM abstracts")
            abstract_count = cursor.fetchone()[0]
            conn.close()
            check_pass(f"abstracts.db 可连接，{abstract_count:,} 条摘要 ({size_mb:.1f} MB)")
        except Exception as e:
            check_fail(f"abstracts.db 连接失败: {e}")
    else:
        check_skip("abstracts.db 不存在（可选）")

    # 向量库
    chroma_dir = data_dir / "chroma"
    if chroma_dir.is_dir():
        collections = list(chroma_dir.glob("*"))
        check_pass(f"Chroma 向量库目录存在，{len(collections)} 个集合/文件")
    else:
        check_warn("Chroma 向量库目录不存在（需要先建索引）")


# =============================================================================
# 检查 5: AI 模型
# =============================================================================

def check_ai_models():
    print_header("检查 5: AI 模型")

    # 检查常见模型路径
    model_paths = [
        ("D:\\models\\models\\BAAI--bge-base-en-v1.5", "Embedding 模型 (Windows)"),
        ("D:\\models\\models\\BAAI--bge-reranker-base", "Reranker 模型 (Windows)"),
        ("/data/models/BAAI--bge-base-en-v1.5", "Embedding 模型 (Linux)"),
        ("/data/models/BAAI--bge-reranker-base", "Reranker 模型 (Linux)"),
        ("models/BAAI--bge-base-en-v1.5", "Embedding 模型 (相对路径)"),
        ("models/BAAI--bge-reranker-base", "Reranker 模型 (相对路径)"),
    ]

    found_models = 0
    for path, desc in model_paths:
        if os.path.isdir(path):
            # 检查关键文件
            config = os.path.join(path, "config.json")
            model_bin = os.path.join(path, "model.safetensors")
            pytorch_bin = os.path.join(path, "pytorch_model.bin")
            has_model = os.path.isfile(model_bin) or os.path.isfile(pytorch_bin)
            has_config = os.path.isfile(config)
            if has_model and has_config:
                check_pass(f"{desc}: {path}")
                found_models += 1
            else:
                check_warn(f"{desc}: 目录存在但缺少关键文件 (config.json/model.safetensors)")
        else:
            check_skip(f"{desc}: {path} 不存在")

    if found_models == 0:
        check_warn("未找到本地 AI 模型，首次运行时会自动下载（可能较慢）")

    # 检查 Ollama 服务
    print("\n  检查 LLM 服务:")
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            check_pass(f"Ollama 服务运行中，可用模型: {', '.join(model_names[:5])}")
        else:
            check_warn(f"Ollama 服务响应异常: HTTP {response.status_code}")
    except Exception:
        check_warn("Ollama 服务未运行（需要启动 Ollama 才能生成综述）")


# =============================================================================
# 检查 6: V33.4 新功能验证
# =============================================================================

def check_v334_features():
    print_header("检查 6: V33.4 新功能验证")

    root = get_project_root()
    sys.path.insert(0, str(root))

    # 测试 EvidenceCard 新字段
    try:
        from services.review.models import EvidenceCard

        card = EvidenceCard(
            evidence_id="ev_selfcheck_001",
            paper_id="paper_test",
            para_id="para_test",
            content="Self-check test evidence",
            source_type="full_text",
            match_method="hybrid",
            rerank_score=0.85,
            dedupe_key="paper_test_para_test",
            retrieval_rank=1,
        )

        # 验证字段
        assert card.source_type == "full_text"
        assert card.match_method == "hybrid"
        assert card.rerank_score == 0.85
        assert card.dedupe_key == "paper_test_para_test"
        assert card.retrieval_rank == 1

        # 验证质量分计算
        score = card.compute_quality_score()
        expected = 0.4 * 1.0 + 0.3 * 1.0 + 0.3 * 0.85
        assert abs(score - expected) < 0.001, f"Expected {expected}, got {score}"

        check_pass(f"EvidenceCard 新字段正常，质量分={score:.4f}")
    except Exception as e:
        check_fail(f"EvidenceCard 新字段验证失败: {e}")

    # 测试证据不足 fallback
    try:
        from services.review.review_generator import ReviewGenerator
        # 检查方法是否存在
        assert hasattr(ReviewGenerator, "_generate_fallback_section")
        assert hasattr(ReviewGenerator, "get_insufficient_evidence_sections")
        check_pass("ReviewGenerator fallback 方法存在")
    except Exception as e:
        check_fail(f"ReviewGenerator fallback 验证失败: {e}")

    # 测试证据抽取器去重
    try:
        from services.review.evidence_extractor import EvidenceExtractor
        # 检查去重逻辑是否在代码中
        import inspect
        source = inspect.getsource(EvidenceExtractor.extract_from_paragraphs)
        assert "dedupe_key" in source or "seen_keys" in source
        check_pass("EvidenceExtractor 去重逻辑存在")
    except Exception as e:
        check_fail(f"EvidenceExtractor 去重验证失败: {e}")

    # P1-1: 检索可观测性模块
    try:
        from services.search.retrieval_observability import RetrievalObservability
        assert hasattr(RetrievalObservability, "start_record")
        assert hasattr(RetrievalObservability, "finish_record")
        assert hasattr(RetrievalObservability, "get_record")
        assert hasattr(RetrievalObservability, "get_stats")
        assert hasattr(RetrievalObservability, "analyze_retrieval")
        check_pass("P1-1: 检索可观测性模块方法完整")
    except Exception as e:
        check_fail(f"P1-1: 检索可观测性模块验证失败: {e}")

    # P1-2: 句子关系判定器
    try:
        from services.search.sentence_relation_classifier import SentenceRelationClassifier, SentenceRelationType
        assert hasattr(SentenceRelationClassifier, "classify")
        assert hasattr(SentenceRelationClassifier, "classify_batch")
        assert hasattr(SentenceRelationClassifier, "find_relations_for_new_sentence")
        # 验证5种关系类型都存在
        for rel in ["duplicate", "supplement", "support", "contradict", "update"]:
            assert SentenceRelationType(rel) is not None
        check_pass("P1-2: 句子关系判定器方法完整，5种关系类型齐全")
    except Exception as e:
        check_fail(f"P1-2: 句子关系判定器验证失败: {e}")

    # P1-3: EvidenceCard 增量维护管理器
    try:
        from services.review.evidence_card_incremental_manager import EvidenceCardIncrementalManager, CardStatus
        assert hasattr(EvidenceCardIncrementalManager, "create_card")
        assert hasattr(EvidenceCardIncrementalManager, "append_evidence")
        assert hasattr(EvidenceCardIncrementalManager, "merge_cards")
        assert hasattr(EvidenceCardIncrementalManager, "deprecate_card")
        assert hasattr(EvidenceCardIncrementalManager, "flag_conflict")
        assert hasattr(EvidenceCardIncrementalManager, "assess_impact")
        assert hasattr(EvidenceCardIncrementalManager, "get_stats")
        # 验证5种卡片状态都存在
        for status in ["active", "deprecated", "conflict", "merged", "draft"]:
            assert CardStatus(status) is not None
        check_pass("P1-3: EvidenceCard 增量维护管理器方法完整，5种状态齐全")
    except Exception as e:
        check_fail(f"P1-3: EvidenceCard 增量维护管理器验证失败: {e}")

    # P2-1: 用户反馈闭环模块
    try:
        from services.review.user_feedback import UserFeedbackManager, FeedbackType, FeedbackRating
        assert hasattr(UserFeedbackManager, "record_feedback")
        assert hasattr(UserFeedbackManager, "record_content_edit")
        assert hasattr(UserFeedbackManager, "record_citation_fix")
        assert hasattr(UserFeedbackManager, "record_rating")
        assert hasattr(UserFeedbackManager, "get_by_review_id")
        assert hasattr(UserFeedbackManager, "get_by_section_id")
        assert hasattr(UserFeedbackManager, "get_unprocessed")
        assert hasattr(UserFeedbackManager, "get_stats")
        assert hasattr(UserFeedbackManager, "get_improvement_suggestions")
        assert hasattr(UserFeedbackManager, "mark_processed")
        # 验证反馈类型齐全（11种）
        for ft in ["content_edit", "citation_fix", "section_add", "section_delete",
                    "section_reorder", "evidence_add", "evidence_remove", "evidence_reassign",
                    "rating", "comment", "other"]:
            assert FeedbackType(ft) is not None
        # 验证评分等级齐全（5级）
        for fr in ["excellent", "good", "fair", "poor", "bad"]:
            assert FeedbackRating(fr) is not None
        check_pass("P2-1: 用户反馈闭环模块方法完整，11种反馈类型+5级评分齐全")
    except Exception as e:
        check_fail(f"P2-1: 用户反馈闭环模块验证失败: {e}")

    # P2-2: 版本管理与增量同步模块
    try:
        from services.data.version_manager import VersionManager, DataSourceType, SyncStatus
        assert hasattr(VersionManager, "register_source")
        assert hasattr(VersionManager, "get_source")
        assert hasattr(VersionManager, "list_sources")
        assert hasattr(VersionManager, "create_sync_task")
        assert hasattr(VersionManager, "update_task_progress")
        assert hasattr(VersionManager, "complete_task")
        assert hasattr(VersionManager, "fail_task")
        assert hasattr(VersionManager, "cancel_task")
        assert hasattr(VersionManager, "list_tasks")
        assert hasattr(VersionManager, "get_incremental_query_params")
        assert hasattr(VersionManager, "should_auto_sync")
        assert hasattr(VersionManager, "get_due_auto_sync_sources")
        assert hasattr(VersionManager, "get_stats")
        # 验证数据源类型齐全（6种）
        for dst in ["pubmed", "pmc", "openalex", "arxiv", "zotero", "local"]:
            assert DataSourceType(dst) is not None
        # 验证同步状态齐全（7种）
        for ss in ["idle", "pending", "running", "paused", "completed", "failed", "cancelled"]:
            assert SyncStatus(ss) is not None
        check_pass("P2-2: 版本管理与增量同步模块方法完整，6种数据源+7种状态齐全")
    except Exception as e:
        check_fail(f"P2-2: 版本管理与增量同步模块验证失败: {e}")

    # P2-3: 影响范围评估与局部重算模块
    try:
        from services.review.impact_analyzer import ImpactAnalyzer, ChangeType, ImpactLevel, RecalcStrategy
        assert hasattr(ImpactAnalyzer, "register_dependency")
        assert hasattr(ImpactAnalyzer, "unregister_dependency")
        assert hasattr(ImpactAnalyzer, "assess_impact")
        assert hasattr(ImpactAnalyzer, "mark_recalc_completed")
        assert hasattr(ImpactAnalyzer, "mark_recalc_skipped")
        assert hasattr(ImpactAnalyzer, "get_pending_reports")
        assert hasattr(ImpactAnalyzer, "get_report")
        assert hasattr(ImpactAnalyzer, "list_reports")
        # 验证变更类型齐全（12种）
        for ct in ["evidence_add", "evidence_remove", "evidence_update", "evidence_merge",
                    "evidence_deprecate", "evidence_conflict", "paper_add", "paper_remove",
                    "outline_change", "data_sync"]:
            assert ChangeType(ct) is not None
        # 验证影响级别齐全（5种）
        for il in ["none", "low", "medium", "high", "critical"]:
            assert ImpactLevel(il) is not None
        # 验证重算策略齐全（4种）
        for rs in ["auto", "manual", "threshold", "none"]:
            assert RecalcStrategy(rs) is not None
        check_pass("P2-3: 影响范围评估模块方法完整，12种变更+5级影响+4种策略齐全")
    except Exception as e:
        check_fail(f"P2-3: 影响范围评估模块验证失败: {e}")

    # P2-4: 统一错误处理与重试模块
    try:
        from services.utils.retry_utils import retry, LLMRouter, ParserFallbackChain, DeadLetterQueue, RetryStatus
        # 验证 retry 装饰器存在且可调用
        assert callable(retry)
        # 验证 LLMRouter 方法
        assert hasattr(LLMRouter, "register_model")
        assert hasattr(LLMRouter, "call")
        assert hasattr(LLMRouter, "get_stats")
        # 验证 ParserFallbackChain 方法
        assert hasattr(ParserFallbackChain, "add_parser")
        assert hasattr(ParserFallbackChain, "parse")
        assert hasattr(ParserFallbackChain, "get_stats")
        # 验证 DeadLetterQueue 方法
        assert hasattr(DeadLetterQueue, "add_task")
        assert hasattr(DeadLetterQueue, "get_task")
        assert hasattr(DeadLetterQueue, "get_pending_tasks")
        assert hasattr(DeadLetterQueue, "retry_task")
        assert hasattr(DeadLetterQueue, "dismiss_task")
        assert hasattr(DeadLetterQueue, "get_stats")
        # 验证重试状态齐全（5种）
        for rs in ["pending", "retrying", "success", "failed", "dead_letter"]:
            assert RetryStatus(rs) is not None
        check_pass("P2-4: 统一错误处理与重试模块方法完整，retry装饰器+LLMRouter+ParserFallbackChain+DeadLetterQueue齐全")
    except Exception as e:
        check_fail(f"P2-4: 统一错误处理与重试模块验证失败: {e}")

    # P2-5: 结构化日志与监控模块
    try:
        from services.utils.structured_logger import StructuredLogger, LogLevel
        assert hasattr(StructuredLogger, "debug")
        assert hasattr(StructuredLogger, "info")
        assert hasattr(StructuredLogger, "warning")
        assert hasattr(StructuredLogger, "error")
        assert hasattr(StructuredLogger, "critical")
        assert hasattr(StructuredLogger, "timer")
        assert hasattr(StructuredLogger, "query")
        assert hasattr(StructuredLogger, "get_recent")
        assert hasattr(StructuredLogger, "get_stats")
        assert hasattr(StructuredLogger, "reset_stats")
        # 验证日志级别齐全（5种）
        for ll in ["debug", "info", "warning", "error", "critical"]:
            assert LogLevel(ll) is not None
        check_pass("P2-5: 结构化日志与监控模块方法完整，5种级别+计时器+查询+统计齐全")
    except Exception as e:
        check_fail(f"P2-5: 结构化日志与监控模块验证失败: {e}")

    # P2-6: 导出与分享功能模块
    try:
        from services.review.export_manager import ExportManager, ExportFormat, ExportStatus
        assert hasattr(ExportManager, "create_export")
        assert hasattr(ExportManager, "get_task")
        assert hasattr(ExportManager, "update_task_progress")
        assert hasattr(ExportManager, "complete_task")
        assert hasattr(ExportManager, "fail_task")
        assert hasattr(ExportManager, "list_tasks")
        assert hasattr(ExportManager, "export_to_markdown")
        assert hasattr(ExportManager, "export_to_bibtex")
        assert hasattr(ExportManager, "export_to_json")
        assert hasattr(ExportManager, "export_to_plain_text")
        assert hasattr(ExportManager, "create_share_link")
        assert hasattr(ExportManager, "verify_share_link")
        assert hasattr(ExportManager, "revoke_share_link")
        assert hasattr(ExportManager, "list_share_links")
        assert hasattr(ExportManager, "get_stats")
        # 验证导出格式齐全（7种）
        for ef in ["markdown", "pdf", "word", "stats_report", "bibtex", "json", "plain_text"]:
            assert ExportFormat(ef) is not None
        # 验证导出状态齐全（5种）
        for es in ["pending", "processing", "completed", "failed", "expired"]:
            assert ExportStatus(es) is not None
        check_pass("P2-6: 导出与分享功能模块方法完整，7种格式+5种状态+分享链接齐全")
    except Exception as e:
        check_fail(f"P2-6: 导出与分享功能模块验证失败: {e}")


# =============================================================================
# 检查 6.5: Protocol 专项下载脚本（V33.7 新增）
# =============================================================================

def check_v337_protocol_downloader():
    print_header("检查 6.5: Protocol 专项下载脚本（V33.7）")

    root = get_project_root()
    script_path = root / "download_protocols.py"

    # 检查1: 文件存在
    if not script_path.is_file():
        check_fail("download_protocols.py 不存在")
        return
    size = script_path.stat().st_size
    check_pass(f"download_protocols.py 存在 ({size:,} bytes)")

    # 检查2: 语法正确
    try:
        import ast
        with open(script_path, "r") as f:
            ast.parse(f.read())
        check_pass("download_protocols.py 语法正确")
    except SyntaxError as e:
        check_fail(f"download_protocols.py 语法错误: {e}")
        return

    # 检查3: 核心类和方法存在
    try:
        with open(script_path, "r") as f:
            content = f.read()

        required_classes = ["ProtocolDownloader"]
        required_methods = [
            "search_pubmed",
            "fetch_abstracts",
            "fetch_pmc_xml",
            "download_by_topic",
            "download_batch",
            "_check_xml_has_body",
        ]
        required_consts = ["PROTOCOL_JOURNALS", "BATCH_TOPICS"]

        for cls in required_classes:
            if f"class {cls}" in content:
                check_pass(f"类 {cls} 存在")
            else:
                check_fail(f"类 {cls} 缺失")

        for method in required_methods:
            if f"def {method}" in content:
                check_pass(f"方法 {method} 存在")
            else:
                check_fail(f"方法 {method} 缺失")

        for const in required_consts:
            if const in content:
                check_pass(f"常量 {const} 存在")
            else:
                check_fail(f"常量 {const} 缺失")

        # 检查4: 支持的期刊数量
        journal_count = content.count('"pmc_journal_title"')
        if journal_count >= 6:
            check_pass(f"支持 {journal_count} 种 Protocol 专刊（≥6）")
        else:
            check_warn(f"仅支持 {journal_count} 种 Protocol 专刊（建议≥6）")

        # 检查5: 批量主题分类数量
        category_count = content.count('": [')  # 粗略统计分类
        if category_count >= 6:
            check_pass(f"内置 {category_count} 个批量主题分类（≥6）")
        else:
            check_warn(f"仅内置 {category_count} 个批量主题分类（建议≥6）")

        # 检查6: 关键功能特性
        features = [
            ("free full text[Filter]", "免费全文过滤（正确语法）"),
            ("filter_no_fulltext", "只有摘要过滤开关"),
            ("--journal", "特定期刊筛选参数"),
            ("--batch", "批量下载参数"),
            ("--dry-run", "预览模式参数"),
            ("--no-xml", "仅下载摘要参数"),
            ("MAX_RETRIES", "重试机制"),
            ("RATE_LIMIT", "NCBI速率限制"),
            ("Windows", "Windows编码兼容"),
        ]
        for keyword, desc in features:
            if keyword in content:
                check_pass(f"功能: {desc}")
            else:
                check_warn(f"功能缺失: {desc}")

    except Exception as e:
        check_fail(f"Protocol 下载脚本验证失败: {e}")


# =============================================================================
# 检查 7: 配置文件
# =============================================================================

def check_config():
    print_header("检查 7: 配置文件")

    root = get_project_root()

    # .env 文件
    env_file = root / ".env"
    env_example = root / ".env.example"
    if env_file.is_file():
        check_pass(".env 配置文件存在")
        # 检查关键配置项
        with open(env_file, "r") as f:
            content = f.read()
            key_configs = ["OLLAMA", "MODEL", "DATABASE", "CHROMA"]
            for cfg in key_configs:
                if cfg.lower() in content.lower():
                    check_pass(f"配置项 {cfg} 存在")
    else:
        if env_example.is_file():
            check_warn(".env 不存在，但 .env.example 存在（请复制并修改）")
        else:
            check_skip(".env 配置文件不存在（使用默认配置）")

    # NCBI 配置
    ncbi_key = os.environ.get("NCBI_API_KEY", "")
    if ncbi_key:
        check_pass(f"NCBI API Key 已配置 ({ncbi_key[:8]}...)")
    else:
        check_warn("NCBI API Key 未配置（在线搜索会限速）")


# =============================================================================
# 主函数
# =============================================================================

def main():
    print(f"\n{Colors.CYAN}{Colors.BOLD}")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║           Sci-Pal 系统自检脚本 V33.7                              ║")
    print("║           检查时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "                          ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.NC}")

    verbose = "--verbose" in sys.argv

    # 运行所有检查
    check_python_env()
    check_project_structure()
    check_dependencies()
    check_databases()
    check_ai_models()
    check_v334_features()
    check_v337_protocol_downloader()
    check_config()

    # 汇总结果
    print_header("自检结果汇总")

    total = stats["pass"] + stats["fail"] + stats["warn"] + stats["skip"]
    print(f"\n  {Colors.GREEN}✅ 通过: {stats['pass']}{Colors.NC}")
    print(f"  {Colors.RED}❌ 失败: {stats['fail']}{Colors.NC}")
    print(f"  {Colors.YELLOW}⚠️  警告: {stats['warn']}{Colors.NC}")
    print(f"  {Colors.CYAN}⏭️  跳过: {stats['skip']}{Colors.NC}")
    print(f"  📊 总计: {total}")
    print()

    if stats["fail"] > 0:
        print(f"{Colors.RED}{Colors.BOLD}⚠️  有 {stats['fail']} 项检查失败，请修复后再运行系统！{Colors.NC}")
        print(f"{Colors.RED}    失败项会影响系统正常运行，请查看上述 FAIL 标记。{Colors.NC}\n")
        sys.exit(1)
    elif stats["warn"] > 0:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  有 {stats['warn']} 项警告，系统可以运行但建议优化。{Colors.NC}")
        print(f"{Colors.YELLOW}    警告项不影响核心功能，但可能影响性能或体验。{Colors.NC}\n")
        sys.exit(0)
    else:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 所有检查通过！系统可以正常运行！{Colors.NC}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
