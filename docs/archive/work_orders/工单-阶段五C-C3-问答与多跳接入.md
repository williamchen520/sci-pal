# 工单 · 阶段五-C 的 C-3：问答与多跳检索接入（含重复加载模型的修复）

> 派单方：WorkBuddy ｜ 执行方：CodeBuddy ｜ 生成时间：2026-10-25 09:05
> 前置：C-2 已验收（16 工具在线，`threaded=True` + 私有 ReviewGenerator 已就位）；
> 看门狗修复已验收（单实例不再堆积）。
> 本工单**允许改业务代码**。

---

## 零、背景事实（我已现查 + 实测量得，**直接采信，不要重复排查**）

### 0.1 实测耗时：两个能力都远超 MCP 的 60 s 上限

| 接口 | 参数 | 实测 | 结论 |
|---|---|---|---|
| `POST /api/qa/ask` | 默认 | **> 120 s**（curl 120 s 超时仍未返回，服务端最终完成） | 必须异步 |
| `POST /api/agentic/search` | `max_hops=1, top_paragraphs=4`（**最小参数**） | **71.5 s**，返回体 99 KB | 必须异步（1 跳就已经超 60 s） |

### 0.2 更要紧的发现：**这两个能力每次都在重复加载检索模型**

`services/search/unified_retriever.py:23` 的 `UnifiedRetriever.__init__` 是**饿汉式**：
构造时立刻 new `HybridSearch` / `Reranker` / `ContextExpander` / `GraphTraverser` / `AbstractSearch`
—— **模型在 `__init__` 里就加载了**。而：

```python
# services/qa/qa_service.py:54
class QAService:
    def __init__(self, rerank=True, graph_expand=True, ...):
        self.retriever = UnifiedRetriever(rerank=rerank, graph_expand=graph_expand)   # 🔴 自建一份

# api_server.py:43
def get_qa_service():
    global _qa_service
    if _qa_service is None:
        _qa_service = QAService()        # 🔴 于是 Flask 进程里出现第二套检索栈

# api_server.py:316  /api/agentic/search
    agentic = AgenticSearcher(max_hops=max_hops, min_coverage=min_coverage)   # 🔴 每次请求都 new
```

而 `AgenticSearcher.__init__`（`services/search/agentic_search.py:223`）**本来就支持注入**：

```python
def __init__(self, retriever: Optional[UnifiedRetriever] = None, ...):
    self.retriever = retriever or UnifiedRetriever(rerank=True, routing=True, expand=True, graph_expand=True)
```

→ 后果：
1. **每次 `/api/agentic/search` 都重建一次检索栈**（加载模型），71.5 s 里很大一块是这个。
2. `QAService` 让 Flask 进程**多养一套**检索栈（每个约 +1.5 GB 量级），
   而 `get_retriever()`（`api_server.py:99`）本来就有现成的共享单例。
3. 首次调用期间的模型加载会把**整个进程**的计算资源吃掉（C-2 已实测过同类现象：
   冷加载期间 `/api/health` 被饿到 20 s+）。

**所以本工单的第一件事不是加异步，而是先把这个重复加载修掉** ——
否则异步化只是把「慢」搬到后台，资源浪费照旧，而且后台任务会持续拖慢前台。

### 0.3 现有可复用设施（C-2 刚建好，别重造）

| 设施 | 位置 |
|---|---|
| `generate_review_async` 样板：`create_task` + 后台线程 + 立即返 `{task_id}`、私有实例、`_check_cancel` 阶段间取消 | `api_server.py` 的 `/api/review/generate_async` |
| 轮询 / 取消 / 查运行中 | `GET /api/review/task/<id>`、`POST /api/review/cancel/<id>`、`GET /api/review/running_task` |
| 任务存储 | `services/review/task_manager.py`（**进程内内存 dict**，重启即丢，不落库） |
| 共享检索器 | `api_server.py:99 get_retriever()` |
| `threaded=True` | `api_server.py` 末尾 `app.run(...)`（**不要改回去**） |

---

## 一、范围

### E-1（先做，业务代码）：停止重复加载检索栈

1. `QAService.__init__` 增加 `retriever: Optional[UnifiedRetriever] = None` 参数，
   内部改为 `self.retriever = retriever or UnifiedRetriever(...)`（默认行为不变，向后兼容）。
2. `get_qa_service()` 改为 `QAService(retriever=get_retriever())`。
3. `/api/agentic/search` 改为 `AgenticSearcher(retriever=get_retriever(), max_hops=..., min_coverage=...)`。
4. **不许改** `UnifiedRetriever.retrieve()` / `HybridRetriever.search_papers()` 的签名（`AI_CONTEXT.md` 冻结项）。

**验收硬指标**：修完之后同样参数再测一次，
`/api/agentic/search`（`max_hops=1, top_paragraphs=4`）耗时应显著低于修复前的 **71.5 s**
（预期降到个位数~十几秒量级，**具体以实测为准，别照抄我的估计**）。
如果耗时没有明显下降，说明还有别处在重建检索栈，**如实报告你的排查结论，不要硬编数字**。

### E-2：两个异步端点

在 E-1 完成后再做，照抄 C-2 的样板：

| 新端点 | 参数（与同步版一致） | 返回 |
|---|---|---|
| `POST /api/qa/ask_async` | `question`(必填) / `paper_id`(可选) / `diagnostics`=false | `{"task_id": ...}` |
| `POST /api/agentic/search_async` | `q`(必填) / `max_hops`=3(钳 1–5) / `min_coverage`=0.6 / `top_paragraphs`=6 / `paper_id`(可选) | `{"task_id": ...}` |

要求：
- 任务类型分别用 `"qa_ask"` / `"agentic_search"`（便于日志区分）。
- 结果字段与同步版一致（**直接放同步版返回的那个 dict**，不要改结构）。
- 进度：`update_progress` 至少各打 2 个点（如「检索证据…」「生成回答…」）。
- 取消：能中断的位置就查 `is_cancelled`；**不能中断就如实写进 docstring**
  （QA/agentic 内部是黑盒调用，很可能只能「提交前 / 完成后」生效 —— 照实写）。
- **同步版两条路由保持原样**，前端在用的契约不许动。

### E-3：MCP 工具

加到 `mcp_server/search_server.py`（**不要加到 generate**，平衡工具数）：

| 工具 | 路由 |
|---|---|
| `ask_question` | `POST /api/qa/ask_async` |
| `agentic_search` | `POST /api/agentic/search_async` |

→ `scipal-search` 6 → **8**，全局 16 → **18**。
轮询**复用已有的 `review_task_status`**（同一套 `task_manager`，端点 `/api/review/task/<id>`），
不要新造 status 工具。两个新工具的 description 必须写明：
「**立即返回 task_id，用 review_task_status 轮询，建议间隔 ≥5 s；任务在 Flask 进程内存里，重启即丢**」。

### E-4：selftest + 文档

- `scipal-search` 期望 **8** 个工具；两个新工具各加一条「< 10 s 返回且含 task_id」断言，
  拿到 id 后**立刻 `cancel_review_task`** 别让任务跑满。
- 文档工具数统一 **18**：`mcp_server/README.md`、`packages/dsh-scipal/README.md`、
  `INSTALL.md`、`cordis.patch.yml` 顶部注释。
- `mcp_server/README.md` §8.2 里「重型生成能力未挂载」那条要更新：qa/agentic 已挂（异步）。

> 自查命令（结果贴进交付报告）：
> `grep -rn "1[0-9] 个" mcp_server/README.md packages/dsh-scipal/`

---

## 二、硬要求（逐条自查）

1. **不许改** `UnifiedRetriever.retrieve()` / `HybridRetriever.search_papers()` 签名。
2. **不许改 `research.db` schema**。
3. **不许把 `app.run(..., threaded=True)` 改回 `False`**。
4. 同步路由 `/api/qa/ask`、`/api/agentic/search` 的响应字段一个都不能少（前端在用）。
5. MCP 三个 server 仍是纯 HTTP 客户端：不许 `from services...` / `import api_server` / 注入项目根到 sys.path；
   **绝不 `print(` 到 stdout**。
6. **不许 `git add -A`**（仓库里有别人的 `_test_v3317b.py`）。
7. 提交前缀 `V33.17: 阶段五C C-3 —— `，**不要自己 push**。

---

## 三、验收判据（WorkBuddy 会独立复跑）

| 判据 | 期望 |
|---|---|
| E-1 效果 | `/api/agentic/search`（`max_hops=1, top_paragraphs=4`）耗时**明显低于 71.5 s**，且 Flask 进程内存**不随调用次数增长**（连续调 3 次，RSS 基本持平） |
| 异步成立 | 两个 async 端点均 `{task_id}` 且**耗时 < 10 s** |
| 任务能完成 | 轮询到 `completed`，result 与同步版字段一致（`answer` / `hops` 等） |
| 前台不被拖死 | 任务运行期间连续 10 次 `/api/health` 均 200（首次冷加载允许慢，之后要 < 2 s） |
| 旧路由回归 | 同步版仍返回原字段（我会读 diff + 抽一次实调） |
| `precheck` / `selftest` | 退出码 0；selftest 全 PASS，`scipal-search` 期望 8 工具 |
| 文档 | 全仓库「18 个」一致 |
| 薄转发铁律 | 3 个 server 里 `from services` / `import api_server` / `print(` **0 命中** |

---

## 四、交付报告必须回答

1. E-1 修复前后 `/api/agentic/search` 的**实测耗时对比**（同参数、同机器），贴两次的 `time_total`。
2. 连续调 3 次后，Flask 进程的**内存**是多少（`tasklist` 或 `--status` 都能看）？有没有随次数增长？
3. 两个 async 端点的**返回耗时**实测值。
4. `QAService` 的 `retriever` 参数默认值你是怎么处理的？有没有破坏别处对 `QAService()` 的调用？（贴 `grep -rn "QAService(" --include=*.py`）
5. 取消在哪些位置生效？如实写限制。
6. `grep -rn "1[0-9] 个" mcp_server/README.md packages/dsh-scipal/` 的输出。
