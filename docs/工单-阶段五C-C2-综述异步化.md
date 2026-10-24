# 工单 · 阶段五-C 的 C-2：综述生成异步化（业务代码改动）

> 派单方：WorkBuddy ｜ 执行方：CodeBuddy ｜ 生成时间：2026-10-25 05:10
> 前置：C-1 已验收通过并入远端（`dev` `91535ba`，15 个工具在线）
> **本工单允许改业务代码**（`api_server.py`），这是它与 C-1 的根本区别。
> 用户已授权执行。

---

## 零、背景事实（我已在本仓库现查 + 实测量得，**直接采信，不要重复查**）

### 0.1 先消歧：之前记录的「21.8 s 饿死」其实是**冷加载**，不是异步本身的问题

2026-10-24 21:15 记录：大纲任务运行期间 `/api/health` 慢到 21.4 / 21.8 s，进程内存 1.47 GB → 2.94 GB。

**05:02 复测（模型已热）推翻了这个归因**：重跑一次 `POST /api/review/outline`
（`max_papers=3`，同一次会话、模型已驻留），连续 100 s 采样：

```text
+1s   health=0.039s  status=running
+4s   health=0.015s  status=running
+7s   health=0.017s  status=completed      ← 任务 5~7 秒就跑完了
……之后 33 次采样全部 0.006 ~ 0.039 s……
```

→ **模型热的时候，异步大纲任务对请求循环几乎零影响**（任务本身也只要 5–7 s）。
那 21.8 s 是 **embedding / reranker 首次加载**（约 1.5 GB）把解释器饿住，属**冷启动一次性**，
改 `threaded` 也救不了。

**所以 C-2 不要为了「解决 21.8 s」去重构 —— 那不是异步化的问题。**
真正要解决的问题在下面两条。

### 0.2 真问题 ①：单线程服务器会把「一次重请求」放大成「全站不可用」

`api_server.py:2057` → `app.run(host, port, debug, threaded=False)`。
werkzeug 此时是**非线程** server：**同一时刻只能处理一个请求**。

后果（这是设计事实，不是推测）：任何人/任何工具调用一次同步重路由
—— 现成的就有 `POST /api/review/generate`（分钟级）、`POST /api/agentic/search`、
`POST /api/qa/ask` —— 在此期间**所有其它请求排队**，包括 MCP 的轮询和哨兵探测。
这就是「异步了也不可轮询」的真正来源，与 GIL 冷启动是两回事。

### 0.3 真问题 ②：ReviewGenerator 是**共享单例且有可读写状态**，并发会串台

```python
# api_server.py:61
def get_review_generator():
    global _review_generator
    if _review_generator is None:
        _review_generator = ReviewGenerator(llm_client=get_llm_client(), retriever=get_retriever(), ...)
    return _review_generator
```

而调用方在请求里**改它的配置、读它的中间结果**：

```python
generator = get_review_generator()
generator.use_llm_verification = use_llm_verify     # 写
output = generator.generate(...)
review_id = store.store(review_id_draft=generator._last_draft,  # 读中间状态
                        evidence_cards=generator._last_evidence_cards)
```

→ 两个任务同时用这个单例，**参数与结果会互相覆盖**。注意：**这个坑今天就已经存在**
（`/api/review/outline` 的后台线程与后续请求会交错），只是 `threaded=False` 降低了撞上的概率。

好消息：`ReviewGenerator.__init__(llm_client, retriever, max_evidence_per_paper, use_llm_verification, db_path)`
**依赖是注入的**，`get_llm_client()` / `get_retriever()` 本身也是单例（模型不重复加载）。
→ **每个任务 new 一个新实例**即可隔离，成本很低。

### 0.4 其余相关事实

| 事实 | 出处 |
|---|---|
| `POST /api/review/generate` 完全同步，返回整篇 `markdown`，无 task_id | `api_server.py:791` |
| review 异步模式已有样板可抄：`create_task` + 后台线程 + 立即返 `{task_id}` | `api_server.py:559-592`（outline） |
| 配套轮询/取消：`GET /api/review/task/<id>`(`:612`)、`GET /api/review/running_task`(`:599`)、`POST /api/review/cancel/<id>`(`:628`) | 已存在 |
| review 任务是**进程内内存 dict**，Flask 重启即丢 | `services/review/task_manager.py` |
| `services/unified_task_manager.py` + SQLite `tasks` 表是**另一套**（持久，在线下载在用） | 注意别混用端点 |
| `ReviewGenerator.generate_outline` 内部已有 `task_manager.is_cancelled(task_id)` 检查 | `review_generator.py:470/493/515` |
| `ReviewGenerator.generate()` 是整条流水线（检索→证据→大纲→撰写→引用校验） | `review_generator.py:257` |

---

## 一、范围

### D-1 Flask 侧（允许改 `api_server.py`）

**D-1.1 新增 `POST /api/review/generate_async`**

- 参数与同步版**完全一致**：`topic`(必填) / `max_papers`=20 / `use_llm_verify`=false /
  `citation_style`="apa" / `review_type`="narrative" / `language`="en" /
  `custom_outline`(JSON object，可选)。
- 流程照抄 outline 的样板：`task_manager.create_task("generate_review")` → 后台线程 → 立即返回
  `{"task_id": ...}`（`return jsonify({"task_id": task_id})`）。
- **线程里必须 new 自己的 ReviewGenerator**，不要用 `get_review_generator()` 单例：

  ```python
  gen = ReviewGenerator(llm_client=get_llm_client(), retriever=get_retriever(),
                        use_llm_verification=use_llm_verify)
  ```
- 结果里带上 review 暂存 id（与同步版一致用 `get_review_store().store(...)` 拿 `review_id`），
  并写进 `task_manager.complete_task(task_id, {...})` 的 result。
- 进度：`update_progress()` 至少打 3 个点（如「检索文献…」「生成大纲…」「撰写中…」）。
  **如果 `ReviewGenerator` 里已有可复用的分步方法（像 `generate_outline` 那样），直接调用；没有就打粗粒度进度，不许重构算法本身。**
- 取消：`task_manager.is_cancelled()` 在**可中断的位置**检查（参考 `generate_outline` 的写法）。
  `generate()` 是整条流水线、无法中途打断 —— **这点要在 docstring 里如实写明**
  （「取消只在阶段间生效，正在撰写时不可中断」），不许嘴硬说支持。

**D-1.2 给同步路由加串行锁**

`threaded=True` 之后，同步的 `POST /api/review/generate` 可能被并发调用，
而它用的仍是共享单例。加一个模块级 `threading.Lock()` 把它串行化
（**不要**给 async 版本加锁，async 用私有实例本来就隔离）。

```python
_review_generate_lock = threading.Lock()
...
with _review_generate_lock:
    generator = get_review_generator()
    ...
```

**D-1.3 `threaded=False` → `threaded=True`**

`api_server.py:2057` 改一个参数。理由见 §0.2：不让一次重请求把全站堵死。

**改之前必须先补好两道安全阀**，顺序不能反：
先 **D-1.1**（异步任务走私有实例）+ **D-1.2**（同步路由加锁），**最后**才动 `threaded`。
理由：`threaded=True` 会让之前「被单线程排队意外挡住的并发」真的并发起来，
在没有 D-1.1 / D-1.2 的情况下先把 `threaded` 打开 = 把 §0.3 的串台风险直接放大。

### D-2 MCP 侧

`mcp_server/generate_server.py` 加 1 个工具：

| 工具 | 路由 | 说明 |
|---|---|---|
| `generate_review` | `POST /api/review/generate_async` | 参数与 C-1 的 `generate_outline` 风格一致；description 必须写「立即返回 task_id，用 `review_task_status` 轮询，建议间隔 ≥5 s；整条流水线分钟级；取消只在阶段间生效」 |

→ `scipal-generate` 变成 **9** 个工具，全局 **16** 个。
这是我给的 ≤8 上限的第 2 次破例，**理由必须写进 README**：这两个 submit 类工具与同 server 的
review 结果读取（`get_review` / `get_saved_outline`）是同一个工作流闭环，拆到第四个 server
要多 1 个常驻进程（实测 ≈68 MB）换不来收益。

**不许**把 `custom_outline` 做成 MCP 工具参数（它是嵌套 dict，MCP 参数只吃标量）——
不支持就是不支持，description 里明说。

### D-3 selftest

- `scipal-generate` 期望 **9** 个工具。
- 新增断言：**`generate_review` 必须在 `< 10 s` 内返回且含非空 `task_id`**（同 C-1 的异步判据）。
- 因为会真的起一条分钟级任务，**测试里用最小参数**（`max_papers=1`），
  拿到 task_id 后**立刻 `cancel_review_task`**，别让它跑满。
- 断言总数会变（预期 ≥23），**具体数字以你实际的为准，别照抄我的估计**。

### D-4 文档

- `mcp_server/README.md` §5.1/§5.2 工具表加 `generate_review`，§5 标题与 §7 记录的工具数更新为 **16**
- `packages/dsh-scipal/README.md` / `INSTALL.md` / `cordis.patch.yml` 顶部注释同步为 16
- **§8.2 那条「异步任务也会拖慢请求循环」必须改写**：补充冷/热的区分
  （冷加载首次会把 health 饿到 ~21 s，模型热之后全程 0.006–0.039 s；见 §0.1 实测数据）
- 记录 ≤8 工具上限的第 2 次破例与理由

> 数字核对命令（必跑，结果贴进交付报告）：
> `grep -rn "1[0-9] 个" mcp_server/README.md packages/dsh-scipal/`

---

## 二、硬要求（逐条自查）

1. **不许改 `UnifiedRetriever.retrieve()` / `HybridRetriever.search_papers()` 的签名**
   （`AI_CONTEXT.md` 冻结项）。本工单不需要动检索层。
2. **不许改 `research.db` 的既有 schema**（不建 Migrations、不加索引）。
   本次的任务状态走现成的 review `task_manager`，不碰 `tasks` 表。
3. 绝不 `print()` 到 stderr 之外的敏感信息；MCP 侧三个 server **仍然不许 `print(` 到 stdout**。
4. MCP 侧仍是纯 HTTP 客户端（不许 `from services...`、不许 `import api_server`、不许注入项目根到 sys.path）。
5. **不许 `git add -A`**（仓库里有别人的 `_test_v3317b.py`，未跟踪，别碰）。
6. 提交信息前缀 `V33.17: 阶段五C C-2 —— `，**不要自己 push**。
7. **同步路由的对外契约不许变**：`POST /api/review/generate` 的响应字段一个都不能少
   （前端在用），新增 async 端点，不要改造旧的。

---

## 三、验收判据（WorkBuddy 会独立复跑，不看你的报告）

| 判据 | 期望 |
|---|---|
| `POST /api/review/generate_async` | 返回 `{task_id}` 且**耗时 < 10 s**（实测我会记秒） |
| 任务真能跑完 | 轮询 `/api/review/task/<id>` 最终到 `completed` 且 result 含 `markdown` 非空 |
| **并发不串台**（关键） | 同时提交 2 个 async 任务：`topic` 与 `use_llm_verify` 不同 → 两个 result 各自对得上自己的参数，`use_llm_verify` 不互相污染 |
| `threaded=True` 生效且没把服务跑挂 | 任务运行期间连续 10 次 `/api/health` 均 200 且延迟 < 2 s |
| 旧同步路由回归 | `POST /api/review/generate` 仍能跑（我会用极小 `max_papers` 验字段完整，或直接读 diff 确认未删字段） |
| `precheck_dsh_bundle.py` | 退出码 0 |
| `selftest.py` | 全 PASS / exit 0，`scipal-generate` 期望 9 个工具 |
| 薄转发铁律 | 3 个 server 里 `from services` / `import api_server` / `print(` **0 命中** |
| 文档数字 | 全仓库「16 个」一致，无「15 个」残留 |

---

## 四、交付报告必须明确回答（我会抽验）

1. `generate_async` 两次实测的**返回耗时**分别是多少？贴返回体原文。
2. 你有没有让 async 任务复用全局 `get_review_generator()` 单例？如果没有，你在线程里 `new` 的实例
   用的是哪两个注入依赖？
3. `threaded=True` 之后，同步 `generate` 的串行走位加在哪一行？贴代码。
4. 并发实验（两个不同 `use_llm_verify` 的任务）的结果是什么？两个 result 会不会串？
5. `generate()` 的**取消**到底在哪些位置生效？你如实写出来的限制是什么？
6. `grep -rn "1[0-9] 个" mcp_server/README.md packages/dsh-scipal/` 的输出是什么？
