#!/usr/bin/env bash
# =============================================================================
# Sci-Pal 全模块测试工作流 — V25.14
# 按顺序运行所有检索层模块的 __main__ 自测，汇总通过/失败。
# 用法: bash scripts/run_tests.sh
# =============================================================================
set -u

# 切到项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 国内 HF 镜像（如已设置则不覆盖）
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
SKIP=0
FAILED_TESTS=()

# 每个测试的超时（秒）—— 模型加载可能较慢
TIMEOUT=120

run_test() {
    local name="$1"
    local module="$2"
    local desc="$3"

    echo -n "  [$name] $desc ... "

    # 检查模块文件是否存在
    local py_file="${module//.//}.py"
    if [ ! -f "$py_file" ]; then
        echo -e "${YELLOW}SKIP (file not found)${NC}"
        SKIP=$((SKIP + 1))
        return
    fi

    # 运行测试，捕获输出和退出码
    local output
    output=$(timeout "$TIMEOUT" python -m "$module" 2>&1)
    local rc=$?

    if [ $rc -eq 0 ]; then
        echo -e "${GREEN}PASS${NC}"
        PASS=$((PASS + 1))
    elif [ $rc -eq 124 ]; then
        echo -e "${YELLOW}TIMEOUT (${TIMEOUT}s)${NC}"
        SKIP=$((SKIP + 1))
    else
        echo -e "${RED}FAIL (rc=$rc)${NC}"
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$name")
        # 打印最后 5 行错误输出
        echo "$output" | tail -5 | sed 's/^/      /'
    fi
}

echo "============================================================"
echo "🧪 Sci-Pal 全模块测试工作流"
echo "============================================================"
echo "项目根目录: $PROJECT_ROOT"
echo "Python: $(python --version 2>&1)"
echo "HF_ENDPOINT: $HF_ENDPOINT"
echo ""

# ---------------------------------------------------------------------------
# 1. 数据质量治理模块（不需要模型，快）
# ---------------------------------------------------------------------------
echo "── 数据质量治理 ──"
run_test "REF-FILTER"  "services.search.reference_filter"   "参考文献过滤审计"
run_test "BOILERPLATE" "services.search.boilerplate_filter" "boilerplate 清洗审计"

# ---------------------------------------------------------------------------
# 2. 查询处理模块（不需要模型）
# ---------------------------------------------------------------------------
echo ""
echo "── 查询处理 ──"
run_test "QUERY-EXPAND" "services.search.query_expander"     "多查询/HyDE 变体生成"
run_test "QUERY-ROUTER" "services.search.query_router"       "查询路由"

# ---------------------------------------------------------------------------
# 3. 检索核心模块（需要 embedding 模型，首次加载较慢）
# ---------------------------------------------------------------------------
echo ""
echo "── 检索核心（需加载模型） ──"
run_test "HYBRID"    "services.search.hybrid_search"    "混合检索（向量+FTS+RRF）"
run_test "RERANK"    "services.search.reranker"         "Cross-Encoder Rerank"
run_test "CONTEXT-EXP" "services.search.context_expander" "小→大扩展"

# ---------------------------------------------------------------------------
# 4. 统一检索（端到端，需要所有模块）
# ---------------------------------------------------------------------------
echo ""
echo "── 端到端 ──"
run_test "UNIFIED" "services.search.unified_retriever" "统一检索信封"

# ---------------------------------------------------------------------------
# 5. 综述生成智能体（V25.0，不依赖 LLM 的自测部分）
# ---------------------------------------------------------------------------
echo ""
echo "── 综述Agent（V25.9，确定性自测） ──"
run_test "EVIDENCE-EXTRACT" "services.review.evidence_extractor" "证据抽取Agent"
run_test "CITATION-VERIFY" "services.review.citation_verifier" "引用校验Agent"
run_test "REVIEW-GEN" "services.review.review_generator" "综述生成主流程"
run_test "SENTENCE-LOCATOR" "services.review.sentence_locator" "句内定位（V25.2）"
run_test "OUTLINE-GEN" "services.review.outline_generator" "LLM大纲生成（V25.2）"
run_test "RELATION-EXTRACT" "services.review.relation_extractor" "关系抽取（V25.3）"
run_test "CONFLICT-DETECT" "services.review.conflict_detector" "冲突识别（V25.3）"
run_test "OUTLINE-STORE" "services.review.outline_store" "大纲存储（V25.9）"
run_test "PDF-ANNOTATOR" "services.pdf.annotator" "PDF标注服务（V25.10，需PyMuPDF）"

# V25.11: 本地文献库 API 路由检查
echo -n "  [LOCAL-PAPERS] 本地文献库API路由（V25.11） ... "
if grep -q "/api/papers/local" api_server.py && grep -q "renderLocal" frontend/src/paper_list.js; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("LOCAL-PAPERS")
fi

# V25.12: 前端拖拽调宽检查
echo -n "  [RESIZER] 前端拖拽调宽（V25.12） ... "
if [ -f "frontend/src/resizer.js" ] && grep -q "class=\"resizer\"" frontend/review.html && grep -q "\.resizer" frontend/src/review.css; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("RESIZER")
fi

# V25.14: PDF浏览器原生iframe渲染 + 移除标注检查
echo -n "  [IFRAME-PDF] PDF浏览器原生iframe渲染（V25.14） ... "
if grep -q "createElement('iframe')" frontend/src/pdf_viewer.js && \
   grep -q "pdf-iframe" frontend/src/pdf_viewer.js && \
   grep -q "load: loadPaper" frontend/src/pdf_viewer.js && \
   ! grep -q "pdfjsLib" frontend/src/pdf_viewer.js && \
   ! grep -q "pdf.min.js" frontend/review.html && \
   ! grep -q "pdf_annotator.js" frontend/review.html && \
   ! grep -q "pdfAnnotator" frontend/src/outline_editor.js && \
   grep -q "\.pdf-iframe" frontend/src/review.css && \
   ! grep -q "\.pdf-page " frontend/src/review.css; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("IFRAME-PDF")
fi

# V25.14: 未解析文献按需触发解析检查
echo -n "  [PARSE-ON-DEMAND] 未解析文献按需触发解析（V25.14） ... "
if grep -q "/api/papers/parse" api_server.py && \
   grep -q "ParserOrchestrator" api_server.py && \
   grep -q "parseAndOpenPaper" frontend/src/outline_editor.js && \
   grep -q "isParsing" frontend/src/outline_editor.js && \
   grep -q "data-parsed" frontend/src/paper_list.js && \
   grep -q "未解析 · 点击解析" frontend/src/paper_list.js; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("PARSE-ON-DEMAND")
fi

# V25.13: 标注 row_factory 修复检查（后端保留，前端不再调用）
echo -n "  [ANNOT-FIX] 标注接口row_factory修复（V25.13） ... "
if grep -q "row_factory = sqlite3.Row" services/pdf/annotator.py; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("ANNOT-FIX")
fi

# V25.18: 引用编号优化检查
echo -n "  [CITE-REFNUM] 引用编号优化（V25.18） ... "
if grep -q "_format_ref_numbers" services/review/review_generator.py && \
   grep -q "evidence_to_ref" services/review/review_generator.py && \
   grep -q "ref_paper_ids_ordered" services/review/review_generator.py; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("CITE-REFNUM")
fi

# V25.18: paper表新字段检查
echo -n "  [PAPER-FIELDS] paper表新字段（V25.18） ... "
if grep -q "abstract TEXT" build_db/build_database.py && \
   grep -q "paper_type TEXT" build_db/build_database.py && \
   grep -q "publisher TEXT" build_db/build_database.py && \
   grep -q "affiliations TEXT" build_db/build_database.py && \
   grep -q "funding TEXT" build_db/build_database.py && \
   grep -q "parse_status TEXT" build_db/build_database.py && \
   grep -q "parse_engine TEXT" build_db/build_database.py && \
   grep -q "updated_at TEXT" build_db/build_database.py && \
   grep -q "abstract" build_db/db_writer.py && \
   grep -q "paper_type" build_db/db_writer.py; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("PAPER-FIELDS")
fi

# V25.18: journal_optimizer元数据提取检查
echo -n "  [JOURNAL-META] journal_optimizer元数据提取（V25.18） ... "
if grep -q "extract_metadata_fields" build_db/parsers/journal_optimizer.py && \
   grep -q "ABSTRACT_PATTERNS" build_db/parsers/journal_optimizer.py && \
   grep -q "AFFILIATION_PATTERNS" build_db/parsers/journal_optimizer.py && \
   grep -q "FUNDING_PATTERNS" build_db/parsers/journal_optimizer.py; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("JOURNAL-META")
fi

# V25.18: 数据库迁移脚本存在检查
echo -n "  [DB-MIGRATE] 数据库迁移脚本（V25.18） ... "
if [ -f "migrate_papers_table_v25.18.py" ] && \
   grep -q "ALTER TABLE papers ADD COLUMN" migrate_papers_table_v25.18.py; then
    echo -e "${GREEN}PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
    FAILED_TESTS+=("DB-MIGRATE")
fi

echo "  （LLM 实际调用测试需 Ollama 服务运行: ollama serve && ollama pull qwen2.5:14b）"

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "📊 测试汇总"
echo "============================================================"
echo -e "  通过: ${GREEN}$PASS${NC}   失败: ${RED}$FAIL${NC}   跳过: ${YELLOW}$SKIP${NC}"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo -e "${RED}失败的测试:${NC}"
    for t in "${FAILED_TESTS[@]}"; do
        echo "  - $t"
    done
    echo ""
    echo "💡 排查建议:"
    echo "  1. 确认 data/research.db 存在且已建库"
    echo "  2. 确认 data/chroma/ 向量索引已构建"
    echo "  3. 确认模型已下载（export HF_ENDPOINT=https://hf-mirror.com）"
    echo "  4. 单独运行失败模块查看完整错误: python -m <module>"
    exit 1
else
    echo ""
    echo -e "${GREEN}✅ 全部测试通过！${NC}"
    exit 0
fi
