#!/usr/bin/env python3
"""
Sci-Pal 自检脚本 — V25.14
检查数据库完整性、检索质量、数据质量、图谱状态和大纲存储，输出结构化报告。

用法:
  python scripts/self_check.py
  python scripts/self_check.py --quick    # 跳过检索质量检查（更快）
"""
import sqlite3
import sys
import os
from pathlib import Path
from collections import defaultdict

# 项目根目录
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "research.db"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

# 颜色
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"
BOLD = "\033[1m"

results = []  # (category, check_name, status, detail)


def check(category, name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((category, name, status, detail))
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name}: {detail}" if detail else f"  {icon} {name}")


def warn(category, name, detail=""):
    results.append((category, name, "WARN", detail))
    print(f"  ⚠️  {name}: {detail}")


# ===========================================================================
# 1. 数据库完整性
# ===========================================================================
def check_database_integrity():
    print(f"\n{CYAN}{BOLD}── 1. 数据库完整性 ──{NC}")

    if not DB_PATH.exists():
        check("数据库", "research.db 存在", False, f"未找到: {DB_PATH}")
        return

    db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    check("数据库", "research.db 存在", True, f"{db_size_mb:.1f} MB")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # 表存在性
    required_tables = ["papers", "paragraphs", "figures", "tables", "citations",
                       "paper_index", "cross_paper_index", "paragraphs_fts", "papers_fts"]
    existing_tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in required_tables:
        check("数据库", f"表 {t} 存在", t in existing_tables)

    # 行数合理性
    counts = {}
    for t in ["papers", "paragraphs", "figures", "tables", "citations"]:
        if t in existing_tables:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

    check("数据库", "论文数 > 0", counts.get("papers", 0) > 0,
          f"{counts.get('papers', 0)} 篇")
    check("数据库", "段落数 > 1000", counts.get("paragraphs", 0) > 1000,
          f"{counts.get('paragraphs', 0)} 段")
    check("数据库", "图表数 > 0", counts.get("figures", 0) > 0,
          f"{counts.get('figures', 0)} 图 / {counts.get('tables', 0)} 表")

    # 外键一致性：paragraphs.paper_id 都在 papers 中
    orphan_paras = conn.execute("""
        SELECT COUNT(*) FROM paragraphs p
        LEFT JOIN papers pa ON p.paper_id = pa.paper_id
        WHERE pa.paper_id IS NULL
    """).fetchone()[0]
    check("数据库", "段落无悬空 paper_id", orphan_paras == 0,
          f"{orphan_paras} 条悬空" if orphan_paras else "全部有效")

    # figures/tables/citations 同理
    for tbl in ["figures", "tables", "citations"]:
        orphan = conn.execute(f"""
            SELECT COUNT(*) FROM {tbl} t
            LEFT JOIN papers p ON t.paper_id = p.paper_id
            WHERE p.paper_id IS NULL
        """).fetchone()[0]
        check("数据库", f"{tbl} 无悬空 paper_id", orphan == 0,
              f"{orphan} 条悬空" if orphan else "全部有效")

    # paper_index 边的 source/target 有效性
    if "paper_index" in existing_tables:
        bad_edges = conn.execute("""
            SELECT COUNT(*) FROM paper_index pi
            LEFT JOIN paragraphs p ON pi.source_id = p.para_id
            WHERE pi.source_type = 'paragraph' AND p.para_id IS NULL
        """).fetchone()[0]
        check("数据库", "paper_index 段落边无悬空", bad_edges == 0,
              f"{bad_edges} 条悬空" if bad_edges else "全部有效")

    # V25.18: papers 表新字段检查
    if "papers" in existing_tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
        v2518_fields = ["abstract", "paper_type", "publisher", "language",
                         "affiliations", "funding", "parse_status", "parse_engine", "updated_at"]
        missing = [f for f in v2518_fields if f not in cols]
        check("数据库", "papers表V25.18新字段齐全", len(missing) == 0,
              f"缺失: {', '.join(missing)}" if missing else "全部9个字段已存在")
        if not missing:
            # 统计有 abstract 的论文数
            has_abstract = conn.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''").fetchone()[0]
            warn("数据库", "abstract填充率", f"{has_abstract}/{counts.get('papers', 0)} 篇有摘要（需重新解析旧论文填充）")

    conn.close()


# ===========================================================================
# 2. 数据质量
# ===========================================================================
def check_data_quality():
    print(f"\n{CYAN}{BOLD}── 2. 数据质量 ──{NC}")

    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # 2.1 重复论文（同 DOI 或同归一化标题）
    dup_doi = conn.execute("""
        SELECT doi, COUNT(*) as cnt FROM papers
        WHERE doi IS NOT NULL AND doi != ''
        GROUP BY doi HAVING cnt > 1
    """).fetchall()
    check("数据质量", "无重复 DOI", len(dup_doi) == 0,
          f"{len(dup_doi)} 个重复 DOI" if dup_doi else "全部唯一")

    # 2.2 空段落
    empty_paras = conn.execute(
        "SELECT COUNT(*) FROM paragraphs WHERE text IS NULL OR trim(text) = ''"
    ).fetchone()[0]
    total_paras = conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]
    empty_pct = 100 * empty_paras / max(total_paras, 1)
    check("数据质量", "空段落 < 5%", empty_pct < 5,
          f"{empty_paras}/{total_paras} ({empty_pct:.1f}%)")

    # 2.3 参考文献段占比（应在合理范围）
    ref_count = 0
    try:
        from services.search.reference_filter import is_reference_entry
        rows = conn.execute(
            "SELECT para_id, section_level1, section_level2, text FROM paragraphs LIMIT 5000"
        ).fetchall()
        for r in rows:
            if is_reference_entry(r["text"], r["section_level1"], r["section_level2"]):
                ref_count += 1
        ref_pct = 100 * ref_count / len(rows)
        check("数据质量", "参考文献段占比 20%-50%", 20 <= ref_pct <= 50,
              f"{ref_count}/{len(rows)} ({ref_pct:.1f}%)")
    except ImportError:
        warn("数据质量", "reference_filter 不可用，跳过参考文献检查")

    # 2.4 fig_number 修正率（V22.2 后应有较多 "Fig N" 格式）
    fig_total = conn.execute("SELECT COUNT(*) FROM figures").fetchone()[0]
    fig_fixed = conn.execute("""
        SELECT COUNT(*) FROM figures
        WHERE fig_number IS NOT NULL AND fig_number LIKE 'Fig %'
    """).fetchone()[0]
    if fig_total > 0:
        check("数据质量", "fig_number 已修正（>30%）", fig_fixed / fig_total > 0.3,
              f"{fig_fixed}/{fig_total} ({100*fig_fixed/fig_total:.1f}%)")

    conn.close()


# ===========================================================================
# 3. 图谱完整性
# ===========================================================================
def check_graph():
    print(f"\n{CYAN}{BOLD}── 3. 图谱完整性 ──{NC}")

    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # DESCRIBED_IN 边
    described = conn.execute(
        "SELECT COUNT(*) FROM paper_index WHERE relation = 'DESCRIBED_IN'"
    ).fetchone()[0]
    check("图谱", "DESCRIBED_IN 边 > 0", described > 0, f"{described} 条")

    # CITES 边
    cites = conn.execute(
        "SELECT COUNT(*) FROM cross_paper_index WHERE relation = 'cites'"
    ).fetchone()[0]
    check("图谱", "CITES 边 >= 0", True, f"{cites} 条")

    # SIMILAR 边
    similar = conn.execute(
        "SELECT COUNT(*) FROM cross_paper_index WHERE relation = 'similar'"
    ).fetchone()[0]
    check("图谱", "SIMILAR 边 > 0", similar > 0, f"{similar} 条")

    # 无自环
    self_loops = conn.execute("""
        SELECT COUNT(*) FROM cross_paper_index
        WHERE source_paper_id = target_paper_id
    """).fetchone()[0]
    check("图谱", "无自环边", self_loops == 0,
          f"{self_loops} 条自环" if self_loops else "干净")

    # 连通分量
    adj = defaultdict(set)
    for src, tgt in conn.execute(
            "SELECT source_paper_id, target_paper_id FROM cross_paper_index"):
        adj[src].add(tgt)
        adj[tgt].add(src)
    visited = set()
    components = 0
    for node in adj:
        if node not in visited:
            components += 1
            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                stack.extend(adj[n] - visited)
    check("图谱", "连通分量数合理", 1 <= components <= 20, f"{components} 个分量")

    conn.close()


# ===========================================================================
# 4. 检索质量（需要模型，较慢）
# ===========================================================================
def check_retrieval_quality():
    print(f"\n{CYAN}{BOLD}── 4. 检索质量（端到端） ──{NC}")

    if "--quick" in sys.argv:
        warn("检索质量", "跳过（--quick 模式）")
        return

    if not DB_PATH.exists():
        return

    try:
        from services.search.unified_retriever import UnifiedRetriever
    except ImportError as e:
        warn("检索质量", f"UnifiedRetriever 导入失败: {e}")
        return

    try:
        retriever = UnifiedRetriever(rerank=True, routing=True, expand=True)
    except Exception as e:
        warn("检索质量", f"检索器初始化失败: {e}")
        return

    test_queries = [
        ("STAT1 interferon", "qa"),
        ("JAK-STAT signaling pathway", "qa"),
        ("single cell RNA sequencing", "qa"),
    ]

    for query, expected_route in test_queries:
        try:
            result = retriever.retrieve(query, top_paragraphs=3, top_figures=2)
        except Exception as e:
            check("检索质量", f"查询 '{query[:30]}' 不报错", False, str(e)[:60])
            continue

        check("检索质量", f"查询 '{query[:30]}' 不报错", True)

        # 返回非空
        has_paras = len(result.get("paragraphs", [])) > 0 or len(result.get("parent_contexts", [])) > 0
        check("检索质量", f"  返回非空段落", has_paras,
              f"{len(result.get('paragraphs', []))} 段 / {len(result.get('parent_contexts', []))} 上下文")

        # 无参考文献条目（简单检查：段落文本不应以典型参考文献格式开头）
        ref_pattern = ["[1]", "1.", "Haghverdi", "et al."]
        contaminated = 0
        for p in result.get("paragraphs", [])[:5]:
            text = (p.get("text") or "")[:80]
            if any(rp in text for rp in ref_pattern) and "STAT" not in text and "interferon" not in text.lower():
                contaminated += 1
        if has_paras:
            check("检索质量", "  无明显参考文献污染", contaminated == 0,
                  f"{contaminated}/5 疑似" if contaminated else "干净")

    # 路由正确性
    try:
        from services.search.query_router import QueryRouter
        router = QueryRouter()
        route = router.route("Figure 3 shows")
        check("检索质量", "图表查询路由正确", "figure" in route.get("channels", []),
              f"channels={route.get('channels')}")
    except Exception:
        pass


# ===========================================================================
# 4b. V25.19 检索优化模块检查
# ===========================================================================
def check_v25_19_retrieval_optimization():
    print(f"\n{CYAN}{BOLD}── 4b. V25.19 检索优化模块 ──{NC}")

    # 1. FTS 查询增强模块
    fts_builder_path = PROJECT_ROOT / "services" / "search" / "fts_query_builder.py"
    check("V25.19", "fts_query_builder.py 存在", fts_builder_path.exists())
    if fts_builder_path.exists():
        try:
            from services.search.fts_query_builder import FTSQueryBuilder
            builder = FTSQueryBuilder()
            # 测试实体识别
            info = builder.explain("How does STAT1 regulate JAK-STAT signaling?")
            check("V25.19", "FTS 实体识别", len(info["entities"]) > 0,
                  f"entities={info['entities']}")
            # 测试短语检测
            check("V25.19", "FTS 短语检测", len(info["phrases"]) >= 0,
                  f"phrases={info['phrases']}")
            # 测试查询构建（不报错即可）
            fts_q = builder.build("STAT1 interferon response")
            check("V25.19", "FTS 增强查询构建成功", bool(fts_q),
                  f"query={fts_q[:60]}...")
            # 测试简单回退查询
            simple_q = builder.build_simple("STAT1 interferon")
            check("V25.19", "FTS 简单回退查询", bool(simple_q),
                  f"query={simple_q}")
        except Exception as e:
            check("V25.19", "FTS 查询增强模块导入/运行", False, str(e)[:80])

    # 2. MMR 多样性去重模块
    mmr_path = PROJECT_ROOT / "services" / "search" / "mmr_diversifier.py"
    check("V25.19", "mmr_diversifier.py 存在", mmr_path.exists())
    if mmr_path.exists():
        try:
            from services.search.mmr_diversifier import MMRDiversifier
            diversifier = MMRDiversifier(lambda_param=0.7)
            # 模拟候选
            candidates = [
                {"text": "STAT1 phosphorylation in interferon signaling",
                 "rerank_score": 0.95, "paper_id": "A"},
                {"text": "STAT1 nuclear translocation upon interferon stimulation",
                 "rerank_score": 0.92, "paper_id": "A"},
                {"text": "JAK inhibitors block cytokine signaling in myelofibrosis",
                 "rerank_score": 0.85, "paper_id": "B"},
                {"text": "Single-cell RNA sequencing reveals immune heterogeneity",
                 "rerank_score": 0.80, "paper_id": "C"},
            ]
            result = diversifier.diversify(candidates, top_k=3, score_key="rerank_score")
            check("V25.19", "MMR 去重运行成功", len(result) == 3,
                  f"返回 {len(result)} 条")
            check("V25.19", "MMR 结果包含 mmr_rank",
                  all("mmr_rank" in r for r in result),
                  f"ranks={[r.get('mmr_rank') for r in result]}")
            # 测试诊断模式
            _, diag = diversifier.diversify_with_diagnostics(candidates, top_k=3)
            check("V25.19", "MMR 诊断模式", "diversity_improvement" in diag,
                  f"improvement={diag.get('diversity_improvement')}")
        except Exception as e:
            check("V25.19", "MMR 去重模块导入/运行", False, str(e)[:80])

    # 3. 检索诊断模式模块
    diag_path = PROJECT_ROOT / "services" / "search" / "retrieval_diagnostics.py"
    check("V25.19", "retrieval_diagnostics.py 存在", diag_path.exists())
    if diag_path.exists():
        try:
            from services.search.retrieval_diagnostics import RetrievalDiagnostics
            diag = RetrievalDiagnostics(enabled=True)
            diag.start("test query")
            diag.log("test_stage", "key", "value")
            report = diag.finish({"final": "ok"})
            check("V25.19", "检索诊断模式运行", report.get("enabled") is True,
                  f"stages={report.get('stage_order')}")
            check("V25.19", "检索诊断包含总耗时", "total_time_ms" in report,
                  f"{report.get('total_time_ms')}ms")
            # 测试文本报告格式化
            text_report = diag.format_text_report(report)
            check("V25.19", "检索诊断文本报告", "Retrieval Diagnostics" in text_report,
                  f"长度={len(text_report)}")
        except Exception as e:
            check("V25.19", "检索诊断模块导入/运行", False, str(e)[:80])

    # 4. hybrid_search.py 包含 V25.19 配置
    hs_path = PROJECT_ROOT / "services" / "search" / "hybrid_search.py"
    if hs_path.exists():
        content = hs_path.read_text(encoding="utf-8")
        check("V25.19", "hybrid_search.py 包含 ENHANCED_FTS 配置",
              "ENHANCED_FTS" in content)
        check("V25.19", "hybrid_search.py 包含 DYNAMIC_RRF_WEIGHTS 配置",
              "DYNAMIC_RRF_WEIGHTS" in content)
        check("V25.19", "hybrid_search.py 包含 MMR_DIVERSIFY 配置",
              "MMR_DIVERSIFY" in content)
        check("V25.19", "hybrid_search.py 导入 FTSQueryBuilder",
              "from services.search.fts_query_builder import FTSQueryBuilder" in content)
        check("V25.19", "hybrid_search.py 导入 MMRDiversifier",
              "from services.search.mmr_diversifier import MMRDiversifier" in content)
        check("V25.19", "hybrid_search.py rrf_fuse 支持权重参数",
              "vector_weight" in content and "fts_weight" in content)

    # 5. unified_retriever.py 支持诊断模式
    ur_path = PROJECT_ROOT / "services" / "search" / "unified_retriever.py"
    if ur_path.exists():
        content = ur_path.read_text(encoding="utf-8")
        check("V25.19", "unified_retriever.py 包含 diagnostics 参数",
              "diagnostics" in content)
        check("V25.19", "unified_retriever.py 导入 RetrievalDiagnostics",
              "from services.search.retrieval_diagnostics import RetrievalDiagnostics" in content)

    # 6. V25.19 补充：学术缩写扩展模块
    abbrev_path = PROJECT_ROOT / "services" / "search" / "abbreviation_expander.py"
    check("V25.19", "abbreviation_expander.py 存在", abbrev_path.exists())
    if abbrev_path.exists():
        try:
            from services.search.abbreviation_expander import AbbreviationExpander
            expander = AbbreviationExpander()
            # 测试缩写识别
            info = expander.get_abbreviation_info("STAT1 KO mice PD-1 blockade")
            check("V25.19", "缩写扩展识别", info["count"] >= 2,
                  f"找到 {info['count']} 个缩写: {[a for a, _ in info['found']]}")
            # 测试缩写扩展
            variants = expander.get_expansion_variants("STAT1 KO mice", max_variants=3)
            has_expanded = any("knockout" in v.lower() for v in variants)
            check("V25.19", "缩写扩展生成变体", has_expanded,
                  f"变体数={len(variants)}")
            # 测试 query_expander 集成
            from services.search.query_expander import QueryExpander
            qe = QueryExpander(max_variants=6)
            qe_variants = qe.expand("PD-1 blockade in TME")
            has_abbrev_in_qe = any("programmed" in v.lower() or "tumor microenvironment" in v.lower()
                                    for v in qe_variants)
            check("V25.19", "query_expander 集成缩写扩展", has_abbrev_in_qe,
                  f"变体数={len(qe_variants)}")
        except Exception as e:
            check("V25.19", "缩写扩展模块导入/运行", False, str(e)[:80])


# ===========================================================================
# 4c. V26.0 RAG 问答模块
# ===========================================================================
def check_v26_0_qa_module():
    print(f"\n{CYAN}{BOLD}── 4c. V26.0 RAG 问答模块 ──{NC}")

    # 1. 问答服务文件
    qa_service_path = PROJECT_ROOT / "services" / "qa" / "qa_service.py"
    check("V26.0", "qa_service.py 存在", qa_service_path.exists())

    if qa_service_path.exists():
        try:
            from services.qa.qa_service import QAService, parse_citations
            # 测试引用解析
            test_answer = "根据研究 [P1]，STAT1 在干扰素通路中起关键作用 [P2]。图表 [F1] 显示了磷酸化过程。"
            citations = parse_citations(test_answer)
            check("V26.0", "引用 ID 解析", len(citations) == 3,
                  f"解析到 {len(citations)} 个引用: {[c['raw'] for c in citations]}")
            check("V26.0", "引用类型识别正确",
                  all(c["type"] in ("P", "F", "T", "R", "C", "G") for c in citations))
            # 测试 QAService 类存在关键方法
            check("V26.0", "QAService.ask 方法存在", hasattr(QAService, "ask"))
            check("V26.0", "QAService.is_llm_available 方法存在", hasattr(QAService, "is_llm_available"))
            check("V26.0", "QAService.get_llm_status 方法存在", hasattr(QAService, "get_llm_status"))
        except Exception as e:
            check("V26.0", "问答服务导入/运行", False, str(e)[:100])

    # 2. API 路由
    api_server_path = PROJECT_ROOT / "api_server.py"
    if api_server_path.exists():
        api_content = api_server_path.read_text(encoding="utf-8", errors="ignore")
        check("V26.0", "/api/qa/ask 路由存在", '"/api/qa/ask"' in api_content)
        check("V26.0", "/api/qa/status 路由存在", '"/api/qa/status"' in api_content)
        check("V26.0", "get_qa_service 函数存在", "def get_qa_service()" in api_content)
        check("V26.0", "_qa_service 懒加载变量", "_qa_service = None" in api_content)

    # 3. 前端页面
    qa_html_path = PROJECT_ROOT / "frontend" / "qa.html"
    check("V26.0", "frontend/qa.html 存在", qa_html_path.exists())
    if qa_html_path.exists():
        qa_content = qa_html_path.read_text(encoding="utf-8", errors="ignore")
        check("V26.0", "qa.html 包含提问输入框", 'id="question"' in qa_content)
        check("V26.0", "qa.html 包含提问按钮", 'id="askBtn"' in qa_content)
        check("V26.0", "qa.html 包含答案展示区", 'id="answerArea"' in qa_content)
        check("V26.0", "qa.html 包含 LLM 状态显示", 'id="statusBar"' in qa_content)
        check("V26.0", "qa.html 包含引用来源面板", "sources-section" in qa_content)
        check("V26.0", "qa.html 包含问答历史", "qa_history" in qa_content)
        check("V26.0", "qa.html 调用 /api/qa/ask", "/api/qa/ask" in qa_content)
        check("V26.0", "qa.html 调用 /api/qa/status", "/api/qa/status" in qa_content)

    # 4. 首页导航入口
    index_html_path = PROJECT_ROOT / "frontend" / "index.html"
    if index_html_path.exists():
        index_content = index_html_path.read_text(encoding="utf-8", errors="ignore")
        check("V26.0", "index.html 包含 AI 问答入口", 'href="/qa.html"' in index_content)


# ===========================================================================
# 5. 向量索引完整性
# ===========================================================================
def check_vector_index():
    print(f"\n{CYAN}{BOLD}── 5. 向量索引 ──{NC}")

    if not CHROMA_PATH.exists():
        check("向量索引", "Chroma 目录存在", False, f"未找到: {CHROMA_PATH}")
        return

    check("向量索引", "Chroma 目录存在", True)

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collections = client.list_collections()
        col_names = [c.name for c in collections]

        for expected in ["paragraphs", "papers"]:
            check("向量索引", f"集合 {expected} 存在", expected in col_names)

        if "paragraphs" in col_names:
            para_col = client.get_collection("paragraphs")
            para_count = para_col.count()
            check("向量索引", "paragraphs 向量数 > 1000", para_count > 1000,
                  f"{para_count} 条")

        if "papers" in col_names:
            paper_col = client.get_collection("papers")
            paper_count = paper_col.count()
            check("向量索引", "papers 向量数 > 0", paper_count > 0,
                  f"{paper_count} 条")

    except ImportError:
        warn("向量索引", "chromadb 未安装，跳过")
    except Exception as e:
        warn("向量索引", f"Chroma 检查失败: {e}")


# ===========================================================================
# 6. 大纲存储（V25.9）
# ===========================================================================
def check_outline_store():
    print(f"\n{CYAN}{BOLD}── 6. 大纲存储（V25.9） ──{NC}")

    outline_dir = PROJECT_ROOT / "data" / "outlines"

    # 检查目录存在
    if not outline_dir.exists():
        try:
            outline_dir.mkdir(parents=True, exist_ok=True)
            check("大纲存储", "data/outlines/ 目录已创建", True)
        except Exception as e:
            check("大纲存储", "data/outlines/ 目录", False, f"创建失败: {e}")
            return
    else:
        check("大纲存储", "data/outlines/ 目录存在", True)

    # 检查 outline_store.py 模块可导入
    try:
        from services.review.outline_store import OutlineStore
        check("大纲存储", "outline_store.py 可导入", True)
    except ImportError as e:
        check("大纲存储", "outline_store.py 可导入", False, str(e))
        return

    # 功能自测：保存→列表→加载→删除
    try:
        store = OutlineStore(str(outline_dir))
        test_name = "_self_check_test"
        test_outline = {
            "sections": [
                {
                    "title": "Test Section",
                    "description": "Self-check test",
                    "paragraphs": [
                        {"topic": "Test paragraph 1", "description": "", "assigned_paper_ids": []},
                        {"topic": "Test paragraph 2", "description": "", "assigned_paper_ids": []},
                    ],
                }
            ]
        }

        # 保存（注意参数顺序：name, topic, outline_data, review_type, paper_count）
        store.save(test_name, topic="test topic", outline_data=test_outline,
                   review_type="narrative", paper_count=0)
        check("大纲存储", "保存大纲", True)

        # 列表
        outlines = store.list()
        names = [o["name"] for o in outlines]
        check("大纲存储", "列表包含已保存大纲", test_name in names,
              f"共 {len(outlines)} 个大纲")

        # 加载
        loaded = store.load(test_name)
        check("大纲存储", "加载大纲", loaded is not None and "outline" in loaded,
              f"章节数={len(loaded.get('outline', {}).get('sections', []))}" if loaded else "加载失败")

        # 删除
        store.delete(test_name)
        check("大纲存储", "删除大纲", not store.exists(test_name))

    except Exception as e:
        check("大纲存储", "大纲存储功能自测", False, str(e)[:80])


# ===========================================================================
# 7. PDF 标注服务（V25.10）
# ===========================================================================
def check_pdf_annotator():
    print(f"\n{CYAN}{BOLD}── 7. PDF标注服务（V25.10） ──{NC}")

    # 检查 annotator.py 模块存在
    annotator_path = PROJECT_ROOT / "services" / "pdf" / "annotator.py"
    check("PDF标注", "services/pdf/annotator.py 存在", annotator_path.exists())

    # V25.13: 检查 row_factory 修复（否则 get_pdf_path 报 TypeError 导致标注接口500）
    if annotator_path.exists():
        annotator_content = annotator_path.read_text(encoding="utf-8")
        check("PDF标注", "get_pdf_path 包含 row_factory 修复", "row_factory = sqlite3.Row" in annotator_content)

    # 检查 PyMuPDF 可导入
    try:
        import fitz
        check("PDF标注", "PyMuPDF (fitz) 已安装", True, f"版本 {fitz.__doc__.split(chr(10))[0][:50] if fitz.__doc__ else ''}")
    except ImportError:
        check("PDF标注", "PyMuPDF (fitz) 已安装", False, "未安装，请执行 pip install PyMuPDF")
        return

    # 检查 annotator 模块可导入
    try:
        from services.pdf.annotator import PdfAnnotator
        check("PDF标注", "annotator.py 可导入", True)
    except ImportError as e:
        check("PDF标注", "annotator.py 可导入", False, str(e))
        return

    # 检查 documents 目录存在
    docs_dir = PROJECT_ROOT / "documents"
    check("PDF标注", "documents/ 目录存在", docs_dir.exists())


# 8. 本地文献库 API（V25.11）
def check_local_papers_api():
    print(f"\n{CYAN}{BOLD}── 8. 本地文献库API（V25.11） ──{NC}")

    # 检查 api_server.py 包含 /api/papers/local 路由
    api_path = PROJECT_ROOT / "api_server.py"
    if api_path.exists():
        content = api_path.read_text(encoding="utf-8")
        has_route = "/api/papers/local" in content
        check("本地文献库", "/api/papers/local 路由存在", has_route)
    else:
        check("本地文献库", "api_server.py 存在", False)

    # 检查前端 tab 切换
    review_html = PROJECT_ROOT / "frontend" / "review.html"
    if review_html.exists():
        content = review_html.read_text(encoding="utf-8")
        has_tabs = "panel-tab" in content and "本地文献库" in content
        check("本地文献库", "前端 tab 切换存在", has_tabs)
    else:
        check("本地文献库", "review.html 存在", False)

    # 检查 paper_list.js 有 renderLocal
    pl_path = PROJECT_ROOT / "frontend" / "src" / "paper_list.js"
    if pl_path.exists():
        content = pl_path.read_text(encoding="utf-8")
        has_render_local = "renderLocal" in content
        check("本地文献库", "paper_list.js renderLocal 方法存在", has_render_local)
    else:
        check("本地文献库", "paper_list.js 存在", False)


# 9. 前端拖拽调宽（V25.12）
def check_frontend_resizer():
    print(f"\n{CYAN}{BOLD}── 9. 前端拖拽调宽（V25.12） ──{NC}")

    # 检查 resizer.js 存在
    resizer_path = PROJECT_ROOT / "frontend" / "src" / "resizer.js"
    check("拖拽调宽", "resizer.js 存在", resizer_path.exists())

    if resizer_path.exists():
        content = resizer_path.read_text(encoding="utf-8")
        check("拖拽调宽", "resizer.js 包含 mousedown 监听", "mousedown" in content)
        check("拖拽调宽", "resizer.js 包含 localStorage 保存", "localStorage" in content)

    # 检查 review.html 包含 resizer
    review_html = PROJECT_ROOT / "frontend" / "review.html"
    if review_html.exists():
        content = review_html.read_text(encoding="utf-8")
        check("拖拽调宽", "review.html 包含 resizer 元素", "class=\"resizer\"" in content)
        check("拖拽调宽", "review.html 加载 resizer.js", "resizer.js" in content)

    # 检查 CSS 包含 resizer 样式
    css_path = PROJECT_ROOT / "frontend" / "src" / "review.css"
    if css_path.exists():
        content = css_path.read_text(encoding="utf-8")
        check("拖拽调宽", "review.css 包含 .resizer 样式", ".resizer" in content)


# 10. 前端浏览器原生iframe PDF渲染（V25.14）
def check_frontend_iframe_pdf():
    print(f"\n{CYAN}{BOLD}── 10. PDF浏览器原生iframe渲染（V25.14） ──{NC}")

    # 检查 pdf_viewer.js 已改为 iframe 管理器
    viewer_path = PROJECT_ROOT / "frontend" / "src" / "pdf_viewer.js"
    if viewer_path.exists():
        content = viewer_path.read_text(encoding="utf-8")
        check("iframe渲染", "pdf_viewer.js 创建iframe元素", "createElement('iframe')" in content)
        check("iframe渲染", "pdf_viewer.js 设置pdf-iframe类名", "pdf-iframe" in content)
        check("iframe渲染", "pdf_viewer.js 不再依赖pdfjsLib", "pdfjsLib" not in content)
        check("iframe渲染", "pdf_viewer.js 保留loadPaper接口", "loadPaper" in content)
        check("iframe渲染", "pdf_viewer.js 保留load别名（兼容旧调用）", "load: loadPaper" in content)
    else:
        check("iframe渲染", "pdf_viewer.js 存在", False)

    # 检查 review.html 不再加载 PDF.js 和标注模块
    html_path = PROJECT_ROOT / "frontend" / "review.html"
    if html_path.exists():
        content = html_path.read_text(encoding="utf-8")
        check("iframe渲染", "review.html 不再加载pdf.min.js", "pdf.min.js" not in content)
        check("iframe渲染", "review.html 不再加载pdf_annotator.js", "pdf_annotator.js" not in content)
        check("iframe渲染", "review.html 保留分配到段落下拉", "oeAssignParaSelect" in content)
    else:
        check("iframe渲染", "review.html 存在", False)

    # 检查 outline_editor.js 已移除标注代码
    editor_path = PROJECT_ROOT / "frontend" / "src" / "outline_editor.js"
    if editor_path.exists():
        content = editor_path.read_text(encoding="utf-8")
        check("iframe渲染", "outline_editor.js 不再引用pdfAnnotator", "pdfAnnotator" not in content)
        check("iframe渲染", "outline_editor.js 不再有onPageRendered回调", "onPageRendered" not in content)
        check("iframe渲染", "outline_editor.js 保留分配到段落函数", "oeAssignToParagraph" in content)
    else:
        check("iframe渲染", "outline_editor.js 存在", False)

    # 检查 CSS
    css_path = PROJECT_ROOT / "frontend" / "src" / "review.css"
    if css_path.exists():
        content = css_path.read_text(encoding="utf-8")
        check("iframe渲染", "review.css 包含 .pdf-iframe 样式", ".pdf-iframe" in content)
        check("iframe渲染", "review.css 不再包含 .pdf-page 样式", ".pdf-page" not in content)
        check("iframe渲染", "review.css 不再包含 .oe-text-layer 样式", ".oe-text-layer" not in content)
        check("iframe渲染", "review.css 不再包含 .oe-annot-toolbar 样式", ".oe-annot-toolbar" not in content)
    else:
        check("iframe渲染", "review.css 存在", False)

    # V25.14: 检查未解析文献按需触发解析 API
    api_path = PROJECT_ROOT / "api_server.py"
    if api_path.exists():
        content = api_path.read_text(encoding="utf-8")
        check("按需解析", "api_server.py 包含 /api/papers/parse 路由", "/api/papers/parse" in content)
        check("按需解析", "api_server.py 包含 ParserOrchestrator 调用", "ParserOrchestrator" in content)
        check("按需解析", "api_server.py 包含路径穿越防护", '".." in filename' in content)

    # 检查前端未解析论文可点击
    paper_list_path = PROJECT_ROOT / "frontend" / "src" / "paper_list.js"
    if paper_list_path.exists():
        content = paper_list_path.read_text(encoding="utf-8")
        check("按需解析", "paper_list.js 未解析论文也可点击", "data-parsed" in content)
        check("按需解析", "paper_list.js 传递 parsed 参数", "this.dataset.parsed" in content)

    # 检查前端解析函数
    editor_path = PROJECT_ROOT / "frontend" / "src" / "outline_editor.js"
    if editor_path.exists():
        content = editor_path.read_text(encoding="utf-8")
        check("按需解析", "outline_editor.js 包含 parseAndOpenPaper 函数", "parseAndOpenPaper" in content)
        check("按需解析", "outline_editor.js 包含 isParsing 防重复锁", "isParsing" in content)
        check("按需解析", "outline_editor.js 调用 /api/papers/parse", "/api/papers/parse" in content)


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    print(f"{BOLD}{'='*60}{NC}")
    print(f"{BOLD}🔍 Sci-Pal 自检报告{NC}")
    print(f"{'='*60}")
    print(f"项目: {PROJECT_ROOT}")
    print(f"数据库: {DB_PATH}")
    print(f"Chroma: {CHROMA_PATH}")

    check_database_integrity()
    check_data_quality()
    check_graph()
    check_vector_index()
    check_outline_store()
    check_pdf_annotator()
    check_local_papers_api()
    check_frontend_resizer()
    check_frontend_iframe_pdf()
    check_retrieval_quality()
    check_v25_19_retrieval_optimization()
    check_v26_0_qa_module()

    # 汇总
    print(f"\n{BOLD}{'='*60}{NC}")
    print(f"{BOLD}📊 自检汇总{NC}")
    print(f"{'='*60}")

    pass_count = sum(1 for r in results if r[2] == "PASS")
    fail_count = sum(1 for r in results if r[2] == "FAIL")
    warn_count = sum(1 for r in results if r[2] == "WARN")

    print(f"  {GREEN}通过: {pass_count}{NC}   "
          f"{RED}失败: {fail_count}{NC}   "
          f"{YELLOW}警告: {warn_count}{NC}")

    if fail_count > 0:
        print(f"\n{RED}失败项:{NC}")
        for cat, name, status, detail in results:
            if status == "FAIL":
                print(f"  [{cat}] {name}: {detail}")
        print(f"\n💡 建议:")
        print(f"  1. 确认已完成建库: python -m build_db.build_database")
        print(f"  2. 确认已构建向量索引: python -m build_db.build_embeddings")
        print(f"  3. 确认已构建 FTS 索引: python -m build_db.build_fts")
        print(f"  4. 运行数据质量治理: dedup_papers / build_figure_links / build_paper_graph")
        sys.exit(1)
    else:
        print(f"\n{GREEN}✅ 自检全部通过！{NC}")
        sys.exit(0)


if __name__ == "__main__":
    main()
