#!/bin/bash
# =============================================================================
# Sci-Pal 测试工作流脚本 V33.4
# 用途：自动化测试核心功能，确保每次修改后系统正常运行
# 使用：bash test_workflow.sh [--quick|--full]
# =============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 计数器
PASS=0
FAIL=0
SKIP=0

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}  Sci-Pal 测试工作流 V33.4${NC}"
echo -e "${BLUE}  项目目录: $PROJECT_DIR${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""

# -----------------------------------------------------------------------------
# 辅助函数
# -----------------------------------------------------------------------------

test_pass() {
    echo -e "  ${GREEN}✅ PASS${NC}: $1"
    PASS=$((PASS + 1))
}

test_fail() {
    echo -e "  ${RED}❌ FAIL${NC}: $1"
    FAIL=$((FAIL + 1))
}

test_skip() {
    echo -e "  ${YELLOW}⏭️  SKIP${NC}: $1"
    SKIP=$((SKIP + 1))
}

section_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# -----------------------------------------------------------------------------
# 阶段 1: 语法检查
# -----------------------------------------------------------------------------

section_header "阶段 1: Python 语法检查"

PYTHON_FILES=(
    "api_server.py"
    "services/review/models.py"
    "services/review/review_generator.py"
    "services/review/evidence_extractor.py"
    "services/review/outline_generator.py"
    "services/review/outline_store.py"
    "services/review/llm_client.py"
    "services/review/citation_verifier.py"
    "services/review/citation_formatter.py"
    "services/search/unified_retriever.py"
    "services/search/hybrid_search.py"
    "services/search/reranker.py"
    "services/search/online_search.py"
    "services/search/hybrid_retriever.py"
    "services/search/online_downloader.py"
)

for file in "${PYTHON_FILES[@]}"; do
    if [ -f "$file" ]; then
        if python3 -c "import ast; ast.parse(open('$file').read())" 2>/dev/null; then
            test_pass "$file 语法正确"
        else
            test_fail "$file 语法错误"
        fi
    else
        test_skip "$file 不存在"
    fi
done

# -----------------------------------------------------------------------------
# 阶段 2: 数据模型验证（V33.4 新增）
# -----------------------------------------------------------------------------

section_header "阶段 2: EvidenceCard 数据模型验证（V33.4）"

if python3 -c "
import sys
sys.path.insert(0, '.')
from services.review.models import EvidenceCard, ConfidenceLevel

# 测试基础字段
card = EvidenceCard(
    evidence_id='ev_test_p1_0',
    paper_id='paper1',
    para_id='para1',
    content='Test evidence content',
)

# 测试 V33.4 新增字段
assert card.source_type == 'full_text', 'source_type 默认值错误'
assert card.match_method == 'hybrid', 'match_method 默认值错误'
assert card.rerank_score == 0.0, 'rerank_score 默认值错误'
assert card.dedupe_key == '', 'dedupe_key 默认值错误'
assert card.retrieval_rank == 0, 'retrieval_rank 默认值错误'

# 测试 compute_quality_score 方法
card.source_type = 'full_text'
card.match_method = 'hybrid'
card.rerank_score = 0.9
score = card.compute_quality_score()
expected = 0.4 * 1.0 + 0.3 * 1.0 + 0.3 * 0.9
assert abs(score - expected) < 0.001, f'质量分计算错误: {score} != {expected}'

# 测试低质量证据
card_low = EvidenceCard(
    evidence_id='ev_test_low',
    paper_id='p2',
    para_id='p2',
    content='Low quality',
    source_type='abstract',
    match_method='entity',
    rerank_score=0.3,
)
low_score = card_low.compute_quality_score()
assert low_score < score, '低质量证据分数应该更低'

print('所有数据模型测试通过')
" 2>/dev/null; then
    test_pass "EvidenceCard 新增字段和 compute_quality_score() 正常"
else
    test_fail "EvidenceCard 数据模型验证失败"
fi

# -----------------------------------------------------------------------------
# 阶段 3: 证据抽取器去重测试（V33.4 新增）
# -----------------------------------------------------------------------------

section_header "阶段 3: 证据抽取器去重测试（V33.4）"

if python3 -c "
import sys
sys.path.insert(0, '.')
from services.review.evidence_extractor import EvidenceExtractor
from services.review.llm_client import LLMClient

# 创建一个 mock LLM client（不实际调用）
class MockLLM:
    def chat(self, system, user):
        return ''
    def chat_json(self, system, user):
        return []

extractor = EvidenceExtractor(MockLLM())

# 测试数据：包含重复段落
paragraphs = [
    {'paper_id': 'paper1', 'para_id': 'para1', 'text': 'This is the first paragraph about STAT1 signaling pathways.', 'section_l1': 'Intro'},
    {'paper_id': 'paper1', 'para_id': 'para1', 'text': 'This is the first paragraph about STAT1 signaling pathways.', 'section_l1': 'Intro'},  # 重复
    {'paper_id': 'paper1', 'para_id': 'para2', 'text': 'This is the second paragraph about JAK kinase activation.', 'section_l1': 'Methods'},
    {'paper_id': 'paper2', 'para_id': 'para1', 'text': 'This is another paper paragraph about immune response.', 'section_l1': 'Results'},
]

cards = extractor.extract_from_paragraphs(paragraphs, topic='STAT1')

# 应该只有 3 个唯一卡片（去掉了 1 个重复）
assert len(cards) == 3, f'去重后应该有 3 个卡片，实际有 {len(cards)}'

# 验证 dedupe_key 设置正确
for card in cards:
    assert card.dedupe_key != '', 'dedupe_key 不应该为空'

# 验证按质量排序（都是默认质量，应该保持顺序）
print(f'去重测试通过: {len(cards)} 个卡片（输入 4 个，去重 1 个）')
" 2>/dev/null; then
    test_pass "证据抽取器精确去重功能正常"
else
    test_fail "证据抽取器去重测试失败"
fi

# -----------------------------------------------------------------------------
# 阶段 3.5: P1 新模块测试（V33.5 新增）
# -----------------------------------------------------------------------------

section_header "阶段 3.5: P1 新模块测试（V33.5）"

# P1-1: 检索可观测性模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.search.retrieval_observability import RetrievalObservability, RetrievalRecord, RecallChannelResult

obs = RetrievalObservability(storage_dir='/tmp/test_retrieval_obs', max_records=10)
record = obs.start_record(task_id='test_001', query='STAT1 immunity')
record.recall_channels['vector'] = RecallChannelResult(channel='vector', count=50, avg_score=0.8)
record.recall_channels['bm25'] = RecallChannelResult(channel='bm25', count=30, avg_score=0.7)
record.hybrid_recall_count = 80
record.rerank_input_count = 80
record.rerank_output_count = 50
record.final_evidence_count = 20
record_id = obs.finish_record(record)

retrieved = obs.get_record(record_id)
assert retrieved is not None
assert retrieved.task_id == 'test_001'
assert retrieved.hybrid_recall_count == 80

stats = obs.get_stats(last_n=10)
assert stats.total_records == 1
assert stats.avg_hybrid_recall == 80

analysis = obs.analyze_retrieval(record_id)
assert analysis['status'] in ['good', 'warning', 'critical']

print('检索可观测性模块测试通过')
" 2>/dev/null; then
    test_pass "P1-1: 检索可观测性模块（retrieval_observability.py）正常"
else
    test_fail "P1-1: 检索可观测性模块测试失败"
fi

# P1-2: 句子关系判定器
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.search.sentence_relation_classifier import SentenceRelationClassifier, SentenceRelationType

classifier = SentenceRelationClassifier(use_llm=False)

# 测试反驳关系
r = classifier.classify(
    'STAT1 activation increases immune response',
    'STAT1 inhibition decreases immune response',
    paper_id1='p1', paper_id2='p2',
)
assert r.relation == SentenceRelationType.CONTRADICT

# 测试更新关系
r2 = classifier.classify(
    'We used RT-PCR to measure gene expression',
    'We developed an improved single-cell RNA-seq method that outperforms previous approaches',
    paper_id1='p1', paper_id2='p2',
    date1='2020-01-01', date2='2023-01-01',
)
assert r2.relation == SentenceRelationType.UPDATE

# 测试关系类型中文标签
assert SentenceRelationType.DUPLICATE.label_zh == '重复'
assert SentenceRelationType.SUPPORT.label_zh == '支持'

print('句子关系判定器测试通过')
" 2>/dev/null; then
    test_pass "P1-2: 句子关系判定器（sentence_relation_classifier.py）正常"
else
    test_fail "P1-2: 句子关系判定器测试失败"
fi

# P1-3: EvidenceCard 增量维护管理器
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.review.evidence_card_incremental_manager import EvidenceCardIncrementalManager, CardStatus

manager = EvidenceCardIncrementalManager(storage_dir='/tmp/test_ec_inc')

# 创建卡片
card1 = manager.create_card(
    content='STAT1 is activated by JAK phosphorylation',
    paper_id='p1', para_id='para1', section_id='sec1',
)
assert card1['status'] == CardStatus.ACTIVE.value

# 追加证据
card1_updated = manager.append_evidence(
    card_id=card1['evidence_id'],
    new_content='STAT1 also responds to IFN-gamma',
    new_paper_id='p2',
)
assert len(card1_updated['appended_evidence']) == 1

# 标记失效
result = manager.deprecate_card(
    card_id=card1['evidence_id'],
    replaced_by='new_card',
    reason='New study',
)
assert result == True
deprecated = manager.get_card(card1['evidence_id'])
assert deprecated['status'] == CardStatus.DEPRECATED.value

# 统计
stats = manager.get_stats()
assert stats['total_cards'] == 1
assert stats['deprecated_cards'] == 1

print('EvidenceCard 增量维护管理器测试通过')
" 2>/dev/null; then
    test_pass "P1-3: EvidenceCard 增量维护管理器正常"
else
    test_fail "P1-3: EvidenceCard 增量维护管理器测试失败"
fi

# -----------------------------------------------------------------------------
# 阶段 3.6: P2 新模块测试（V33.6）
# -----------------------------------------------------------------------------

section_header "阶段 3.6: P2 新模块测试（V33.6）"

# P2-1: 用户反馈闭环模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.review.user_feedback import UserFeedbackManager, FeedbackType

manager = UserFeedbackManager(storage_dir='/tmp/test_uf_workflow')

# 记录评分
fb1 = manager.record_rating(review_id='rev_001', rating='good', comment='test')
assert fb1.feedback_id is not None

# 记录评论
fb2 = manager.record_comment(review_id='rev_001', comment='test comment', section_id='sec_002')
assert fb2.feedback_id is not None

# 查询（验证不死锁）
by_review = manager.get_by_review_id('rev_001')
assert len(by_review) == 2

by_section = manager.get_by_section_id('sec_002')
assert len(by_section) == 1

by_type = manager.get_by_type(FeedbackType.RATING.value)
assert len(by_type) == 1

# 统计
stats = manager.get_stats(last_n=100)
assert stats.total_feedback == 2

# 标记处理
result = manager.mark_processed(fb1.feedback_id, notes='test')
assert result == True

# 未处理查询
unprocessed = manager.get_unprocessed(limit=10)
assert len(unprocessed) == 1

print('用户反馈闭环模块测试通过')
" 2>/dev/null; then
    test_pass "P2-1: 用户反馈闭环模块（user_feedback.py）正常"
else
    test_fail "P2-1: 用户反馈闭环模块测试失败"
fi

# P2-2: 版本管理与增量同步模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.data.version_manager import VersionManager, SyncStatus

manager = VersionManager(storage_dir='/tmp/test_vm_workflow')

# 注册数据源
source = manager.register_source(
    source_id='pubmed_test', source_type='pubmed', name='PubMed Test',
)
assert source.source_id == 'pubmed_test'
assert source.current_version == 0

# 创建同步任务
task = manager.create_sync_task(source_id='pubmed_test', incremental=True)
assert task is not None
assert task.status == SyncStatus.PENDING.value

# 更新进度
manager.update_task_progress(task.task_id, progress=50.0, current_step='downloading', processed=50, added=45)
task_updated = manager.get_task(task.task_id)
assert task_updated.progress == 50.0
assert task_updated.added == 45

# 完成任务
manager.complete_task(task.task_id)
task_completed = manager.get_task(task.task_id)
assert task_completed.status == SyncStatus.COMPLETED.value

source_updated = manager.get_source('pubmed_test')
assert source_updated.current_version == 1
assert source_updated.total_papers == 45

# 增量查询参数
params = manager.get_incremental_query_params('pubmed_test')
assert params['incremental'] == True
assert params['since_timestamp'] > 0

# 统计
stats = manager.get_stats()
assert stats.total_sources == 1
assert stats.total_papers == 45

print('版本管理与增量同步模块测试通过')
" 2>/dev/null; then
    test_pass "P2-2: 版本管理与增量同步模块（version_manager.py）正常"
else
    test_fail "P2-2: 版本管理与增量同步模块测试失败"
fi

# P2-3: 影响范围评估与局部重算模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.review.impact_analyzer import ImpactAnalyzer, ChangeType, ImpactLevel

analyzer = ImpactAnalyzer(storage_dir='/tmp/test_ia_workflow')

# 注册依赖
analyzer.register_dependency(
    evidence_id='ev_001', section_id='sec_001', review_id='rev_001',
    paper_id='paper_001', section_title='1.1 Background',
    chapter_id='ch_001', chapter_title='Chapter 1',
)
analyzer.register_dependency(
    evidence_id='ev_002', section_id='sec_001', review_id='rev_001',
    paper_id='paper_002', section_title='1.1 Background',
)
analyzer.register_dependency(
    evidence_id='ev_003', section_id='sec_002', review_id='rev_001',
    paper_id='paper_001', section_title='1.2 Purpose',
)

# 评估影响
report = analyzer.assess_impact(
    change_type=ChangeType.EVIDENCE_ADD.value,
    change_description='test',
    evidence_ids=['ev_001'],
)
assert report.total_impacted_sections == 1
assert report.should_recalc == True

# 高影响评估（证据移除）
report2 = analyzer.assess_impact(
    change_type=ChangeType.EVIDENCE_REMOVE.value,
    change_description='test',
    evidence_ids=['ev_001', 'ev_002'],
)
assert report2.overall_impact_level in [ImpactLevel.HIGH.value, ImpactLevel.MEDIUM.value]

# 通过论文 ID 评估
report3 = analyzer.assess_impact(
    change_type=ChangeType.PAPER_REMOVE.value,
    paper_ids=['paper_001'],
)
assert report3.total_impacted_sections == 2

# 标记完成
result = analyzer.mark_recalc_completed(report.report_id, recalculated_sections=['sec_001'])
assert result == True

# 查询
reports = analyzer.list_reports(limit=10)
assert len(reports) >= 3

print('影响范围评估与局部重算模块测试通过')
" 2>/dev/null; then
    test_pass "P2-3: 影响范围评估与局部重算模块（impact_analyzer.py）正常"
else
    test_fail "P2-3: 影响范围评估与局部重算模块测试失败"
fi

# P2-4: 统一错误处理与重试模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.utils.retry_utils import retry, LLMRouter, ParserFallbackChain, DeadLetterQueue

# 测试 @retry 装饰器
call_count = 0
@retry(max_attempts=3, base_delay=0.01, jitter=False)
def flaky_func():
    global call_count
    call_count += 1
    if call_count < 3:
        raise ValueError('flaky')
    return 'success'
result = flaky_func()
assert result == 'success'
assert call_count == 3

# 测试 LLMRouter
router = LLMRouter()
def primary(prompt):
    return f'primary: {prompt}'
def fallback(prompt):
    return f'fallback: {prompt}'
router.register_model('primary', primary)
router.register_model('fallback', fallback)
result = router.call('test', max_retries_per_model=1, base_delay=0.01)
assert 'primary:' in result

# 测试 ParserFallbackChain
chain = ParserFallbackChain()
def parser1(data):
    raise ValueError('failed')
def parser2(data):
    return f'parsed: {data}'
chain.add_parser('parser1', parser1)
chain.add_parser('parser2', parser2)
result, parser_used = chain.parse('test.pdf')
assert parser_used == 'parser2'

# 测试 DeadLetterQueue
dlq = DeadLetterQueue(storage_dir='/tmp/test_dlq_workflow')
task = dlq.add_task(
    task_name='test', task_type='llm_call',
    payload={'prompt': 'test'}, error_message='Timeout',
)
assert task.task_id is not None
pending = dlq.get_pending_tasks()
assert len(pending) == 1
success = dlq.retry_task(task.task_id, lambda p: True)
assert success == True
stats = dlq.get_stats()
assert stats['total'] == 1
assert stats['resolved'] == 1

print('统一错误处理与重试模块测试通过')
" 2>/dev/null; then
    test_pass "P2-4: 统一错误处理与重试模块（retry_utils.py）正常"
else
    test_fail "P2-4: 统一错误处理与重试模块测试失败"
fi

# P2-5: 结构化日志与监控模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.utils.structured_logger import StructuredLogger, LogLevel

logger = StructuredLogger(module='test', storage_dir='/tmp/test_logs_workflow', console_output=False)

# 记录日志
logger.debug('debug', details={'k': 'v'})
logger.info('info', event='test_event')
logger.warning('warning')
logger.error('error', error=ValueError('test'))
logger.critical('critical')

# 计时器
import time
with logger.timer('test_op', details={'id': '1'}):
    time.sleep(0.01)

# 查询
error_logs = logger.query(level='error', limit=10)
assert len(error_logs) == 1
event_logs = logger.query(event='test_event', limit=10)
assert len(event_logs) == 1
recent = logger.get_recent(n=5)
assert len(recent) == 5

# 统计
stats = logger.get_stats()
assert stats.total_requests >= 5
assert stats.total_errors >= 1
assert stats.avg_duration_seconds > 0

# 级别过滤
logger2 = StructuredLogger(module='filtered', storage_dir='/tmp/test_logs2', min_level='warning', console_output=False)
logger2.info('filtered out')
logger2.warning('kept')
logs = logger2.get_recent(n=10)
assert len(logs) == 1

print('结构化日志与监控模块测试通过')
" 2>/dev/null; then
    test_pass "P2-5: 结构化日志与监控模块（structured_logger.py）正常"
else
    test_fail "P2-5: 结构化日志与监控模块测试失败"
fi

# P2-6: 导出与分享功能模块
if python3 -c "
import sys
sys.path.insert(0, '.')
from services.review.export_manager import ExportManager, ExportFormat

manager = ExportManager(storage_dir='/tmp/test_exports_workflow')

# 创建导出任务
task = manager.create_export(review_id='rev_001', format='markdown', include_references=True)
assert task.task_id is not None

# Markdown 导出
sections = [{'title': '1. Intro', 'content': 'test', 'evidence_ids': []}]
references = [{'authors': 'Smith', 'year': '2023', 'title': 'Test', 'journal': 'Nature', 'doi': '10.1/test'}]
result = manager.export_to_markdown(task.task_id, 'Test Review', sections, references)
assert result.status == 'completed'
assert result.file_size_bytes > 0

# BibTeX 导出
task2 = manager.create_export(review_id='rev_001', format='bibtex')
result2 = manager.export_to_bibtex(task2.task_id, references)
assert result2.status == 'completed'

# JSON 导出
task3 = manager.create_export(review_id='rev_001', format='json')
result3 = manager.export_to_json(task3.task_id, {'title': 'test'})
assert result3.status == 'completed'

# 查询任务
tasks = manager.list_tasks(review_id='rev_001')
assert len(tasks) == 3

# 分享链接
link = manager.create_share_link(
    review_id='rev_001', export_task_id=task.task_id,
    password='123456', expires_in_hours=24,
)
assert link.link_id is not None
assert link.has_password == True

# 验证分享链接
valid, msg = manager.verify_share_link(link.link_id, password='123456')
assert valid == True
valid2, msg2 = manager.verify_share_link(link.link_id, password='wrong')
assert valid2 == False

# 撤销分享链接
revoked = manager.revoke_share_link(link.link_id)
assert revoked == True

# 统计
stats = manager.get_stats()
assert stats.total_exports == 3
assert stats.total_share_links == 1

print('导出与分享功能模块测试通过')
" 2>/dev/null; then
    test_pass "P2-6: 导出与分享功能模块（export_manager.py）正常"
else
    test_fail "P2-6: 导出与分享功能模块测试失败"
fi

# -----------------------------------------------------------------------------
# 阶段 4: 配置和依赖检查
# -----------------------------------------------------------------------------

section_header "阶段 4: 配置和依赖检查"

# 检查关键目录
for dir in "data" "frontend" "services" "documents_xml" "abstracts_xml"; do
    if [ -d "$dir" ]; then
        test_pass "目录 $dir/ 存在"
    else
        test_skip "目录 $dir/ 不存在（可选）"
    fi
done

# 检查关键配置文件
for file in "requirements.txt" ".env.example" "README.md"; do
    if [ -f "$file" ]; then
        test_pass "文件 $file 存在"
    else
        test_skip "文件 $file 不存在"
    fi
done

# 检查 Python 包依赖
echo ""
echo "  检查 Python 包依赖..."
REQUIRED_PACKAGES=("flask" "pydantic" "chromadb" "sentence_transformers" "spacy")
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import $pkg" 2>/dev/null; then
        test_pass "Python 包 $pkg 已安装"
    else
        test_skip "Python 包 $pkg 未安装（可能在虚拟环境中）"
    fi
done

# -----------------------------------------------------------------------------
# 阶段 5: 版本号一致性检查
# -----------------------------------------------------------------------------

section_header "阶段 5: 版本号一致性检查"

# 检查 VERSION 文件
if [ -f "VERSION" ]; then
    VERSION=$(cat VERSION)
    test_pass "VERSION 文件存在，当前版本: $VERSION"
else
    test_skip "VERSION 文件不存在"
fi

# 检查 api_server.py 中的版本号
if grep -q "V33" api_server.py 2>/dev/null; then
    API_VERSION=$(grep -o "V[0-9]*\.[0-9]*" api_server.py | head -1)
    test_pass "api_server.py 版本号: $API_VERSION"
else
    test_skip "api_server.py 版本号未找到"
fi

# -----------------------------------------------------------------------------
# 测试结果汇总
# -----------------------------------------------------------------------------

section_header "测试结果汇总"

TOTAL=$((PASS + FAIL + SKIP))
echo ""
echo -e "  ${GREEN}✅ 通过: $PASS${NC}"
echo -e "  ${RED}❌ 失败: $FAIL${NC}"
echo -e "  ${YELLOW}⏭️  跳过: $SKIP${NC}"
echo -e "  📊 总计: $TOTAL"
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}⚠️  有 $FAIL 个测试失败，请检查上述错误信息！${NC}"
    exit 1
else
    echo -e "${GREEN}🎉 所有关键测试通过！系统可以正常运行。${NC}"
    exit 0
fi
