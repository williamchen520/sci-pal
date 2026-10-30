# 阶段五：MCP 服务器按业务流拆分 + 配置 bundle 化

> 决策时间：2026-10-24 ｜ 提出：用户（按科研业务流拆）｜ 评估与落盘：WorkBuddy
> CodeBuddy 看不到我们的对话，开工前必读本文。

---

## 0. 前提修正（重要）

阶段三定的「单进程」当时基于一条推理：**拆多个 server = 多份模型，8GB 显存装不下**。

**这条推理在薄转发架构下不成立。** 2026-10-24 实测：

| 进程 | 内存 | 说明 |
|---|---|---|
| 单个 MCP server | **~68 MB** | 只是 urllib 转发器，**不加载任何模型** |
| Flask（SciPal 本体） | **1123 MB** | 模型 + ChromaDB 全在这儿，被所有 server 共享 |

→ 按域拆 server 在资源上完全可行。真正限制因素换成了**模型上下文**（工具越多，模型选工具越差）。

---

## 1. 用户提出的拆分方案（按科研业务流，不按功能模块）

- `scipal-search` —— 文献下载、解析、入库、检索
- `scipal-generate` —— 多轮渐进式提问、综述生成、引用追踪
- `scipal-guard` —— 防幻觉约束、领域词表校验

**这个拆法比按功能模块拆更好**，因为边界对齐的是「用户意图」而非「代码结构」，
模型选工具时语义更清楚。采纳。

---

## 2. 逐项能力核对（不凭印象，全部 grep 过源码）

### Server 1 · `scipal-search` ✅ 完全可行，零新增路由

| 能力 | 现有路由 |
|---|---|
| 混合检索 | `/api/search/hybrid` |
| 在线检索 | `/api/search/online` |
| 下载 / 队列 / 状态 / 历史 / 重试 | `/api/search/download_online`、`download_status`、`download_queue`、`download_history`、`retry_download` |
| PDF 解析 | `/api/papers/parse` |
| 导入入库 | `/api/papers/import` |
| 本地论文 / 摘要 | `/api/papers/local`、`/api/abstracts/list`、`/api/abstracts/<id>` |

### Server 2 · `scipal-generate` ⚠️ 可行，但有一条硬约束

| 能力 | 现有路由 |
|---|---|
| 多轮渐进式提问 | `/api/agentic/search`、`/api/qa/ask` |
| 综述生成 | `/api/review/generate`、`/api/review/outline` |
| 任务轮询 | `/api/review/task/<task_id>`、`/api/review/running_task`、`/api/tasks/<task_id>` |
| 引用追踪 | `/api/papers/<paper_id>/graph`（引用/被引/相似）、`/api/graph/stats` |

🔴 **硬约束**：综述生成与大纲生成**远超 MCP 的 60 秒上限**。
所有长任务工具必须「**立即返回 job 句柄 + 独立 status 工具轮询**」，严禁同步等待。
（依据：`toolCallTimeoutMs` 默认 60000；且 MCP 明确不支持 task-based execution。）

引用追踪目前只有论文级引用图（引用/被引/相似），**没有全库引文链路追踪**。够用但不算强。

### Server 3 · `scipal-guard` ⚠️ 一半可行

| 能力 | 结论 | 证据 |
|---|---|---|
| 防幻觉约束 | ✅ **有，且已能直接拿到** | `services/ai/rag_validator.py:9 class RAGValidator`；`services/qa/qa_service.py:264` Step 3.5 调用；结果写入 `result["validation"]`（`qa_service.py:324`），字段含 `coverage`/`passed`/`missing`/`retried`/`message`。**/api/qa/ask 的响应里就有，零新增路由。** |
| 领域词表校验 | ❌ **不存在** | 全仓 grep 只有 `services/search/mmr_diversifier.py:29` 的停用词表（MMR 用）和 `build_db/build_xml_db.py:50` 建库脚本里的关键词表。**没有任何领域词表校验服务。** |

---

## 3. 结论与建议

**Server 1、Server 2 立即做。Server 3 暂缓独立成 server**，理由：

1. 现阶段 guard 可用的工具只有 1–2 个（本质是「问一个问题 → 拿校验结论」），
   独立成一个 server 会让工具列表出现一个「只有一两个工具、还依赖 generate」的孤岛。
2. 防幻觉校验在代码里本来就是 **QA 流程的 Step 3.5**（`qa_service.py:264`），
   它天然属于 generate 的一环，不是独立能力。
3. 领域词表校验完全不存在 —— 要做就得新增路由 + 建词表服务，**属业务代码改动**，
   需要单独开工单并由用户点头，不混在本轮里。

**建议排布：**

| 阶段 | 内容 |
|---|---|
| 本轮 | 做 `scipal-search` + `scipal-generate` 两个 server；防幻觉结论作为 `generate` 的一个工具暴露（读 `/api/qa/ask` 的 `validation` 字段） |
| 后续 | 若决定建领域词表服务 → 新增 `/api/validate` 端点 → 再把 guard 拆成独立 server |

---

## 4. 配置 bundle 化（把手改 YAML 变成正经插件）

按官方 `templates/mcp` 结构做一个**配置型 bundle**（零代码），目录建议 `packages/dsh-scipal/`：

```
packages/dsh-scipal/
├── package.json        # 必须有 dsh.bundle.patch 指向 patch 文件
├── cordis.patch.yml    # 内容就是现在的 insert 条目
├── locale/en.json      # { meta: { title, description } }
└── icon.svg
```

官方模板原文（已解包在 `docs/DSH官方参考/dsh-agent-preset/skills/cordis-plugin-development/templates/mcp/`）：

```json
{
  "name": "@local/demo-mcp",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "exports": { "./locale/*.json": "./locale/*.json", "./icon": "./icon.svg" },
  "files": ["cordis.patch.yml", "locale/*.json", "icon.svg"],
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
}
```

🔴 **一条会导致启动报错的坑（官方 README 原文）**：

> 两条配置项使用相同的服务器名称时，**后加载的一条会在加载时以明确错误失败**。

→ 装了 bundle 之后，**必须把 `~/.dsh/profiles/desktop/cordis.patch.yml` 里我们手写的那两条
`insert` 条目删掉**，否则 `scipalhello` / `scipal` 重名冲突。

---

## 5. 安装方式与现实约束

官方路径：`plugin_manager` `action: install_bundle`，`target` = bundle 目录的**绝对路径**。

⚠️ **`plugin_manager` 是 DSH 运行时内部工具，CodeBuddy 没有。**
→ 安装这一步只能由用户执行（在 DSH 会话里让 agent 装，或走 UI）。
这与现在手改 YAML 一样都要人做，区别在于装完之后它是个可单独卸载的正经插件。
