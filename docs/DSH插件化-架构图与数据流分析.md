# 架构图 / 数据流图 × DSH 插件化 分析

> 分析对象：`sci-pal 系统完整架构图_00.tif`（8 层 / 60+ 模块）、`sci-pal 核心数据流图_00.tif`（6 阶段）。
> 两份 TIF 与 `docs/sci-pal-architecture.html`、`docs/sci-pal-dataflow.html` 内容一致，本文按这两份原文逐条核对。
> 关联：`docs/DSH插件化-路线图.md`（现状：3 server / 20 工具）、`docs/DSH契约要点.md`（硬约束）。
> 日期：2026-10-25

---

## 1. 两张图各自回答什么

| 图 | 回答的问题 | 对插件化的用途 |
|---|---|---|
| 系统完整架构图（8 层） | **东西放在哪、谁依赖谁** | 决定「哪些层进 DSH、哪些层留在 SciPal」 |
| 核心数据流图（6 阶段） | **一次综述是怎么跑出来的** | 决定「流程节点怎么切、在哪设闸门」 |

**关键判断：图里的「层」不是插件边界。** 8 层是代码/部署分层（前端 / API / 生成 / 证据 / 检索 / 模型 / 存储 / 数据源），
按层切插件会得到「前端插件」「模型插件」这种没法独立运行的东西。插件边界只能沿**用户意图 + 长任务边界**切，
也就是数据流图的 6 个阶段 —— 这和阶段五「按科研业务流拆 server」的结论是同一个道理，只是往下再走一层。

---

## 2. 8 层逐层判决

| 层 | 内容 | 在 DSH 的落法 | 判决 |
|---|---|---|---|
| 1 前端层 | review.html + 10 个 JS 模块，三栏布局 | **不移植**。DSH 的界面是会话 + 文件产物（md/docx/pdf） | ❌ 复刻三栏 = 重做一遍产品 |
| 2 API 层 | Flask，端口 5000，`/api/review/*` 等 | MCP 薄转发（已做） | ✅ 已落地 |
| 3 生成层 | review_generator + 7 个 review 模块 | 留 Flask；只暴露「开始 / 查状态 / 取结果」 | ✅ 部分落地 |
| 4 证据处理层 | evidence_extractor / relation / conflict | 留 Flask，作为检索与生成的内部步骤 | ⚠️ 不单独成工具，见 §6 |
| 5 检索层 | 20 个模块，统一检索流水线 | 留 Flask；对外只暴露 `unified_retriever` 的入口 | ✅ 已落地 |
| 6 AI 模型层 | 4 个本地模型（bge ×2、qwen ×2、scispacy） | **绝不进 MCP 子进程**（薄转发硬约束） | ✅ 已守住 |
| 7 存储层 | research.db / abstracts.db / chroma ×2 / FTS5 | 留 Flask，进程内独占写 | ✅ 不进 DSH |
| 8 数据源层 | 15 个下载/导入/建索引脚本 | 只把「单篇下载/解析」做成工具；批量建库留在命令行 | ⚠️ 见 §6 反模式 |

一句话：**DSH 侧真正需要的只有第 2、3、5 层的入口，其余六层都不该变成插件。**

---

## 3. 6 阶段 × 现有 20 工具（覆盖度盘点）

| 阶段 | 图里的核心动作 | 现有工具 | 覆盖 |
|---|---|---|---|
| 1 采集与入库 | 下载 PubMed/PMC/OpenAlex → XML → SQLite → 向量库 | `download_online_papers` `download_status` `parse_paper` `list_local_papers` | ✅ 单篇闭环；批量建库函数未暴露（合理） |
| 2 大纲加载/编辑 | 模板 → 编辑章节/关键词 → 保存 | `generate_outline` `list_saved_outlines` `get_saved_outline` | ⚠️ **缺保存**（`POST /api/review/outline/save` 无工具） |
| 3 按大纲搜索并分配 | 主题词注入 → 逐章节检索 → 证据卡片 → 分配 | **无** | ❌ **最大缺口**（`POST /api/review/search_and_assign` 无工具） |
| 4 综述生成 | 分章节 → 证据-声明矩阵 → 5 维评分 → 迭代 | `generate_review` `review_task_status` `cancel_review_task` | ✅ 异步闭环 |
| 5 格式化与存储 | 引用格式 → 校验 → 句子定位 → 存 review | `get_review` | ⚠️ 结果可读，但「校验报告 / 定位信息」没有独立出口 |
| 6 前端展示 | 三栏、引用跳 PDF、标注 | — | ❌ 不移植（换成 md/docx 产物） |

**这张表说明一件事：现在的 20 个工具是「检索 + 生成」两个孤岛，中间的阶段 3 是断的。**
而阶段 3 恰好是数据流图里标注的「核心检索流程」，也是「证据-声明矩阵」的证据来源。
只靠阶段 4 内部兜底检索，等于把「大纲引导检索」这条产品主线丢掉了 —— 每章的关键词、分配、top N 都不再受控。

---

## 4. 「插件式流程」怎么落：三种编排位置

这是本次分析的核心结论。**「流程」放哪一层，决定了它确不确定。**

| 方案 | 编排在哪 | 确定性 | 可见性 | 代价 | 适用 |
|---|---|---|---|---|---|
| A 技能串（skill） | 模型按 skill 步骤调工具 | ❌ 模型可能跳步/改序 | ✅ 每步都在会话里 | 半天写 skill | 探索、演示、人盯着跑 |
| B 工作流脚本（workflow） | JS 脚本固定阶段顺序 | ✅ 阶段级确定 | ⚠️ 只有阶段产物 | 1–2 天 | 批量跑多个主题 |
| C 服务端流水线 | SciPal 新增 `/api/pipeline/*`，返回 task_id | ✅ 完全确定 | ❌ DSH 只见开始/进度/结果 | 3–5 天 | 生产、可复现 |

**推荐 C 的骨架 + A 的交互**（混合）：

- **阶段内部**（检索 → 证据 → 撰写 → 校验）保持 Flask 里的确定性，不进模型；
- **阶段之间**用 skill 串，并设 **2 个人工闸门**：大纲确认（阶段 2 末）、成稿验收（阶段 5 末）；
- 需要批量复现时，再把这条 skill 固化成 workflow 脚本，阶段实现不变。

理由直接来自数据流图的原则 6：「不用多智能体架构，用确定性流程 + 评分标准更可控」。
如果流程只写在 skill 里，模型就成了编排器 —— 这恰好违反了这条原则。

### 4.1 流程骨架（skill 版，可直接照写）

```text
0  预检      health ×2（search / generate），不通就停，不要带着半挂的栈开跑
1  阶段 1    list_local_papers(only_unparsed) → parse_paper(每个) →
             download_online_papers(pmc_ids) → download_status 轮询
             产物：可检索论文数。批量建库（build_db/*）不在流程内，属离线运维
2  阶段 2    generate_outline(topic, review_type) → 展示大纲
             【闸门 1】用户改章节/关键词 → save_outline(name)
3  阶段 3    search_and_assign(outline_name, topic, max_papers) → 轮询
             只回统计（每章分到几篇、几条证据），evidence_cards 留在服务端
4  阶段 4    generate_review(outline_name) → review_task_status 轮询（≥5 s）
             → get_review
5  阶段 5    读校验摘要（引用通过率 / 警告）→ 导出 md/docx
             【闸门 2】用户验收
6  阶段 6    交付产物（DSH 侧渲染，不再需要三栏 UI）
异常        排队中 = 等待（不是失败）；失败 = 读 status.error 重试 1 次；
            超时 = cancel_review_task + 如实报错，不静默重跑
```

两个闸门是**必须停**的，不是可选：阶段 2 停，是因为「大纲先行」本身是产品设计；
阶段 5 停，是因为引用通过率不达标时重跑比重写便宜。

---

## 5. 缺口三个，按优先级

| # | 缺口 | 路由 | 形态 | 风险 |
|---|---|---|---|---|
| 1 | 按大纲搜索并分配 | `POST /api/review/search_and_assign` | **必须异步**（逐章节检索；冷启动要加载检索栈，首次实测 109 s —— 同一栈，见路线图 §2.2；热态 1–2 s/章） | 返回 `custom_outline` 含 evidence_cards，整包可能几十 KB，**不要塞进模型上下文** |
| 2 | 大纲保存 | `POST /api/review/outline/save` | 同步，秒级 | 名字冲突覆盖；建议带 `name` 幂等 |
| 3 | 当前运行任务 | `GET /api/review/running_task` | 同步 | 只用于观测，可并入 `review_task_status` 的空参形态 |

第 1 条建议**不要**走「同步工具 + 60 s 赌一把」：图里阶段 3 是 `for each section` 循环，
章节数由用户大纲决定，天然不可控。照 `generate_review` 的做法加一个 `_async` 端点 + 轮询，是唯一稳的路。

> ⚠️ 顺带一个图上的笔误：阶段 2 写的是 `POST /api/review/outline/saved`，
> 实际路由是 **`POST /api/review/outline/save`**（`/saved` 是 GET 列表/详情）。
> 做工具时按代码里的路由，别按图写。

**上下文预算才是隐藏约束**：阶段 3 的产物是「大纲 + 每段证据卡片」。7 章 × 5 条证据 × 每条带原文引用，
轻松 30–50 KB。这部分**应当留在服务端**（存进 outline store / tasks 表），工具只回 `outline_name` + 统计摘要，
否则一次流程就把上下文吃掉一半，后面的生成阶段没有余量。

---

## 6. 图里明确「不该做」的三件事

1. **60+ 模块 → 60+ 工具**：上下文必爆，且模型选不准（路线图 §2.3 已按 ≤8/ server 收敛）。
2. **`build_db/*` 建索引脚本做成工具**：批量、长事务、改库，且和 Flask 抢 SQLite 写锁。
   这类操作应该是「运维命令 + 一个只读的 `check_parse_status` 出口」，不是流程节点。
3. **用 TS 重写前端三栏**：等于把产品重做一遍，且 DSH 的产物形态（md/docx/pdf）已经够用。

---

## 7. 与现有硬约束的对齐检查

| 约束（来源） | 本方案是否触碰 |
|---|---|
| MCP `toolCallTimeoutMs` 60 s | 阶段 3 必须异步；阶段 4 已异步 ✅ |
| 薄转发禁止 import 业务模块 | 三个新工具都只打 HTTP ✅ |
| stdio 环境清洗（密钥/no_proxy） | 沿用现有 server 的 `env:` 写法 ✅ |
| `serverName` 唯一、工具名 `mcp__<server>__<tool>` | 新工具并进 `scipal-generate` 还是新开第 4 个 server，见下 |
| 单实例任务队列（同时只跑 1 个） | 阶段 3、4 会排队；流程里必须显示「排队中」而不是当失败 ⚠️ |
| 共享单例可写状态 | 阶段 3 只读检索栈，风险低；但冷加载会拖慢同进程的其它请求 ⚠️ |

**放哪个 server**：`generate` 现有 9 个，加 3 个到 12，超出 8 的基准较多。
更干净的是新开 `scipal-outline`（3 个工具：`generate_outline` 迁移 + `save_outline` + `search_and_assign`），
让 `generate` 回到 7 个、`outline` 3 个、`search` 10 个 —— 但这会动已验收的 server 结构，需要单独一轮，
不能顺手改。若只想先跑通流程，允许 `generate` 暂时到 12。

---

## 8. 下一步（按可交付排序）

| 步 | 动作 | 完成判据 | 估时 |
|---|---|---|---|
| 1 | 补 `save_outline`（薄转发 `POST /api/review/outline/save`） | 保存后 `list_saved_outlines` 能读到 | 0.5 h |
| 2 | 补 `search_and_assign` + `POST /api/review/search_and_assign_async` | 立即返 task_id；轮询拿到分配摘要 | 0.5–1 d |
| 3 | 写 skill：六阶段流程 + 2 个闸门 + 失败处理 | 一条主题从下载跑到成稿，全程不手动补步骤 | 0.5 d |
| 4 | 端到端实测（冷启动一次 + 热态一次） | 记录每阶段耗时、上下文占用、失败点 | 0.5 d |
| 5 | 决定是否拆第 4 个 server / 是否上 workflow 脚本 | 出结论即可，不急着写 | — |

第 1、2 步是业务代码改动（`api_server.py` 加异步端点），按协作约定属于 CodeBuddy 的活，需要单开工单；
第 3 步是 skill 文本，放 `docs/` 或 DSH skills 目录，不碰业务代码。

---

## 附：三句话总结

1. **能做**，但「插件式流程」的节点是 6 个阶段，不是 60 个模块；8 层图只用来看依赖，不用来切插件。
2. **现在缺的是阶段 3**：没有 `search_and_assign`，流程会在「大纲 → 生成」之间断层，图里最核心的「大纲引导检索」失效。
3. **流程别放模型里**：阶段内部确定性留在 Flask，阶段之间用 skill 串 + 两个人工闸门；要批量复现再升级成 workflow 脚本。
