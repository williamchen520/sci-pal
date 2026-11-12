# 生信代码 RAG 计划书

> 版本：v1（讨论稿）  
> 日期：2026-11-12  
> 状态：**暂缓实现，先完成实验 Phase C**  
> 范围：Python 生信可视化配方 + 版本/方法追踪  
> 边界：独立 `scipal_code`，挂靠 DSH，不进入主程序

---

## 1. 结论摘要

```text
通用代码 RAG：不建议做
Python 生信可视化 RAG：有必要，优先
版本/方法追踪 RAG：有必要，但必须配确定性版本检查
自动把别人代码加入项目：RAG 只给候选和出处，不自动写
```

建议拆成两个能力，共用一个独立库：

```text
A. BioViz Recipe RAG
   配方库 + 样式规范 + 渲染反馈

B. Method / Version Tracker
   版本快照 + changelog / API diff + 方法卡 + 兼容检查
```

先做 A，B 后置；两者都不进入 `scipal_core` / `scipal_rebuild` / `scipal_docs`。

---

## 2. 背景

### 2.1 目标一：Python 生信画图不好看

现状问题不是“不会写 matplotlib”，而是：

```text
图型选择不对
默认样式不适合论文
字体、尺寸、DPI、留白不稳定
配色不友好
多面板布局混乱
统计标注和图例经常出错
```

目标不是“生成能跑的图”，而是：

```text
生成符合目标期刊/场景的图
代码可复现
样式一致
渲染后能检查并迭代
```

### 2.2 目标二：生信代码更新快、版本标准各异

需要：

```text
跟踪别人的方法/仓库更新
对齐当前环境版本
找到兼容的 API 和写法
把特定代码安全加入自己的项目
```

这不是单纯“代码搜索”，而是：

```text
方法卡 + 版本快照 + 兼容矩阵 + 出处/license
```

---

## 3. 调研报告

> 检索时间：2026-11-12。部分 arXiv/ACL 全文受网络限制，以下结论来自摘要、检索片段和公开页面；引用链接保留，实现前应复核原文。

### 3.1 代码助手基线：agentic grep 很强

2026 年一篇对 Claude Code 源码的拆解文章指出：

```text
Claude Code 早期使用 RAG + 本地向量库
后来发现 agentic search 通常更好
最终主要靠 LLM 驱动 grep/glob/read
配合 LSP 的 definition/references
GrepTool 默认只返回文件路径并限制条数，控制上下文
```

来源：[别再迷信 RAG 了！Grep 回归，向量索引沦为备胎？](https://dbaplus.cn/news-141-7303-1.html)

启示：

```text
“无 RAG 的 DSH 代码助手”不是裸模型
而是 grep + read + LSP + 多轮工具调用
通用代码 RAG 的增量必须正面证明
```

### 3.2 CodeRAG-Bench：检索增强不等于生成变好

CodeRAG-Bench 系统评估检索增强代码生成，覆盖文档、代码仓库等来源。核心启示：

```text
检索质量、覆盖率和任务类型都影响生成
最好的 retriever 不一定带来最好的生成
naive RAG 不足以保证代码正确
```

来源：[CodeRAG-Bench](https://aclanthology.org/2025.findings-naacl.176/)

启示：

```text
代码 RAG 必须和“无 RAG 的 DSH 基线”做 head-to-head
不能只报检索 Recall
```

### 3.3 RepoBench：跨文件检索要单独评

RepoBench 把 repository-level 任务拆成检索、补全、pipeline，强调跨文件上下文和长上下文问题。

来源：[RepoBench](https://ar5iv.labs.arxiv.org/html/2306.03091)

启示：

```text
检索单元和生成单元要分开评估
文件/符号 Recall 不等于最终答案正确
```

### 3.4 RepoCoder：迭代检索有价值，但要控轮数

RepoCoder 用模型预测作为下一轮检索 query，迭代检索 + 生成，说明仓库级补全中“多轮检索”有效。

来源：[RepoCoder](https://ar5iv.labs.arxiv.org/html/2303.12570)

启示：

```text
多跳/迭代检索不是伪需求
但必须有停止条件和证据充分性判断
```

### 3.5 BioCoder：生信代码生成是独立问题

BioCoder 是生物信息代码生成 benchmark，强调领域上下文和实用知识；函数级生成本身仍难。

来源：[BioCoder](http://export.arxiv.org/abs/2308.16458)  
站点：[BioCoder benchmark](https://biocoder-benchmark.github.io/)

启示：

```text
生信代码不能只用通用 Python 语料
需要领域配方、API 版本和数据契约
```

### 3.6 Plot2Code / ChartMimic：图到代码可以评，但不评“生信合理性”

- Plot2Code：科学图表到代码生成 benchmark。  
  [Plot2Code](https://aclanthology.org/2025.findings-naacl.164.pdf)
- ChartMimic：chart-to-code 跨模态基准。  
  [ChartMimic](https://ar5iv.labs.arxiv.org/html/2406.09961)

启示：

```text
“图能否复现”可以自动评一部分
“图型是否适合生信数据、是否符合期刊规范”仍需人工 rubric
```

### 3.7 LocAgent / IRCoT / Agentless：多跳要图，不要乱逛

- LocAgent：图引导的代码定位 agent，说明代码图比纯文本相似更接近仓库级定位。  
  [LocAgent](https://aclanthology.org/2025.acl-long.426/)
- IRCoT：检索与思维链交替，适合多跳知识问答。  
  [IRCoT](https://aclanthology.org/2023.acl-long.557/)
- Agentless：简单的“定位 → 修复”两阶段可以很强，提醒不要过度 agentic。  
  [Agentless](https://dl.acm.org/doi/full/10.1145/3715754)

启示：

```text
多跳应由 DSH 编排
RAG 提供图邻居和证据
不要让 RAG 内部再养一个 agent
```

### 3.8 AST 图 vs LLM 知识图

有研究比较 AST 派生代码图与 LLM 抽取知识图，方向上更支持“确定性 AST 图”。

来源：[Reliable Graph-RAG for Codebases](https://export.arxiv.org/pdf/2601.08773)

启示：

```text
代码边优先来自 parser / import / call / config
不要依赖 LLM 猜边
```

### 3.9 调研总结

```text
1. 通用代码 RAG 的对手是 agentic grep + LSP，不是裸模型
2. 检索 Recall 不等于代码生成/回答正确
3. 跨文件、版本、工作流接线才是 RAG 的机会
4. 多跳有价值，但必须有界、可验证
5. 生信可视化需要领域配方和样式，不是通用代码语料
```

---

## 4. 必要性判断

| 场景 | DSH 无 RAG | 加 RAG | 判断 |
|---|---|---|---|
| 已知函数定位 | grep/LSP 很强 | 可能更慢 | 不需要 |
| 单文件 bug | read/edit 足够 | 无增量 | 不需要 |
| 冷启动大仓库 | 多轮 grep 慢 | 语义召回有帮助 | 有条件 |
| 多 repo / monorepo | 范围大 | 元数据过滤 + 召回 | 有价值 |
| 生信画图配方 | 通用模型易“能跑但难看” | 配方 + 样式 + 预览 | **高价值** |
| 期刊级图表规范 | 模型缺稳定规范 | 样式库 + rubric | **高价值** |
| 新版本 API 迁移 | 模型知识过期 | 版本快照 + changelog | **高价值** |
| 方法/仓库追踪 | 需要人工搜 | 方法卡 + 出处 | **有价值** |
| 自动加入别人代码 | 风险高 | 只能给候选 | 不自动做 |

最终：

```text
通用代码 RAG：不必要
生信可视化配方 RAG：有必要，优先
版本/方法追踪 RAG：有必要，后置
```

---

## 5. 产品定义

### 5.1 A. BioViz Recipe RAG

输入：

```text
自然语言意图
数据形状/列名/AnnData 结构
目标期刊或场景
配色/尺寸/字体约束
当前环境版本
```

输出：

```text
图型建议
完整可运行代码
数据契约
样式配置
渲染预览
版本/依赖
出处/license
```

不做什么：

```text
不做通用代码聊天
不自动改用户仓库
不替代测试/渲染
```

### 5.2 B. Method / Version Tracker

输入：

```text
论文 DOI / GitHub repo / package
当前环境 lockfile 或版本列表
目标版本
```

输出：

```text
方法卡：论文、repo、commit、license
版本链：release / changelog / breaking changes
兼容性：API 是否存在、依赖是否可解
迁移配方：替代写法 + 测试
```

不做什么：

```text
不把 embedding 当版本解析器
不自动 merge 别人的代码
不跳过 license
```

---

## 6. 架构

### 6.1 独立库

```text
数据库     scipal_code
schema     code_rag
角色       code_owner / code_reader
边界       独立于 scipal_core / scipal_rebuild / scipal_docs
```

不共用：

```text
paragraph_embeddings
docs_rag chunks
corpus_connection()
```

### 6.2 数据模型

```text
recipes            配方：图型、意图、代码、数据契约
recipe_versions    配方与包版本兼容范围
styles             期刊/场景样式：尺寸、DPI、字体、配色、面板规则
figures            预览图、输入 schema、渲染检查
packages           包、来源、license
package_versions   版本、发布日期、Python 约束
symbols            API 符号、签名、deprecated
changelog          版本变更、breaking change
methods            论文/仓库/commit/license/方法卡
edges              recipe→package、method→repo、symbol→symbol
embeddings         recipe / method / changelog 向量
ingest_runs        索引批次、来源、新鲜度
```

### 6.3 DSH 工具面

```text
bioviz_search
bioviz_render
code_version_check
code_method_trace
code_patch_propose
```

原则：

```text
RAG 不跑自己的 agent loop
RAG 不做最终答案
RAG 返回证据 + 文件/行号 + commit + license
DSH 读实际文件验证
```

### 6.4 运行形态

```text
DSH
  -> code RAG MCP tool
  -> scipal_code (read-only)
  -> 索引 worker (独立写入)
  -> 渲染沙箱 (bioviz_render)
```

索引 worker 可以定时抓取 GitHub/PyPI/Bioconda/changelog；DSH 查询只读。

---

## 7. 切分与滑窗

### 7.1 配方

```text
一个 recipe = 一个 chunk
200–600 tokens
包含 imports + 数据准备 + plot + style + save
不切碎
```

### 7.2 长脚本 / notebook

```text
按分析步骤切
数据准备 / 统计 / 绘图 / 样式导出
命中后补 imports、数据契约、style
```

### 7.3 版本化代码

```text
按 AST 符号切：module/class/function
保留 signature、docstring、parent
config / changelog 按 section 切
不同版本不混在一个 chunk
```

### 7.4 滑窗

```text
只对超长函数
按控制流/语句块切
10–15% overlap
保留 parent_symbol_id
命中 window 回填父函数和相邻块
```

不要：

```text
固定 500 词硬切
每个窗口独立建向量
把 imports/style 切掉
```

---

## 8. 多跳设计

### 8.1 谁来做

```text
DSH 决定是否多跳、往哪跳
RAG 提供 search + graph neighbors + version check
DSH 每跳后读实际文件验证
```

### 8.2 图边

```text
imports
calls
references
config_key
process_input / process_output
container
reference
test
```

### 8.3 限制

```text
最多 2–3 跳
最多 20–30 个节点
没有新证据就停
返回完整路径，不只返回终点
```

### 8.4 典型链路

画图：

```text
意图 -> 图型 -> recipe -> 版本/API -> style -> render -> critique
```

版本：

```text
method -> repo/commit -> package version -> changelog/API diff -> migration recipe
```

---

## 9. 版本、出处与安全

```text
每个 recipe 带 package + version_range + tested
每个 method 带 DOI/repo/commit/license
每个索引带 last_verified_at + source_commit + stale
```

查询时：

```text
先做确定性版本检查
再看语义相似度
不兼容的 recipe 不返回为“可直接用”
```

安全：

```text
代码只读
渲染在沙箱
不执行任意仓库脚本
secret / license / 私有 repo 过滤
不自动写入用户项目
```

---

## 10. 评测

### 10.1 画图

20–30 个任务：

```text
UMAP / PCA / 火山图 / MA / 热图 / dotplot
survival / forest / UpSet / spatial / 多面板
```

rubric：

```text
代码可运行
图型正确
尺寸/DPI/字体符合目标
色盲友好
标签/图例不重叠
统计标注正确
人工偏好 A/B
```

### 10.2 版本

15–20 个任务：

```text
API 是否存在
breaking change
替代写法
依赖可解
license 允许
```

指标：

```text
版本判断准确率
迁移代码可运行率
引用/出处正确率
stale 错误率
```

### 10.3 基线

```text
DSH 无 RAG：grep + read + LSP + 多轮
通用 LLM
RAG recipe
RAG + render feedback
```

### 10.4 Go 条件

```text
画图：代码可运行 >= 90%，人工偏好 >= 70%
版本：准确率 >= 90%，stale 错误率 < 5%
p95 检索 < 8s，渲染 < 30s
```

不达标就停。

---

## 11. 分阶段计划

### Phase 0：需求与 gold（2–3 天）

```text
20 个绘图配方
10 个版本案例
2–3 个真实 repo
确定 license 和评测 rubric
```

### Phase 1：独立库与配方（3–5 天）

```text
scipal_code + code_rag
recipe/style/package 表
手工策展 20 个配方
渲染预览
```

### Phase 2：DSH 工具（3–5 天）

```text
bioviz_search
bioviz_render
code_version_check
code_method_trace
code_patch_propose（只提案）
```

### Phase 3：评测（3 天）

```text
DSH 基线 vs RAG
A/B 人工偏好
版本准确性
```

### Phase 4：Go / No-Go

```text
达标 -> 增量索引 / 更多配方 / 版本追踪
不达标 -> 停，保留评测和配方库
```

总计约 2–3 周；**在实验 Phase C 之后启动**。

---

## 12. 风险

| 风险 | 应对 |
|---|---|
| 索引陈旧 | commit + last_verified + stale 标记 |
| 版本混用 | 版本快照 + lockfile + 兼容范围 |
| 配方“能跑但难看” | style + render + 视觉 rubric |
| 代码 license | 出处、license、allowlist |
| 自动改坏项目 | 只提案，不自动写 |
| 过度 agentic | DSH 编排，RAG 只给图工具 |
| 评测自嗨 | 与 DSH 基线 A/B，公开集仅参考 |
| 维护成本 | 先 20 个配方，不先建大平台 |

---

## 13. 当前决策

```text
现在不做实现
先完成实验 Phase C
之后按本计划做 2–3 周 spike
先 BioViz，后版本追踪
```

明确不采纳：

```text
通用代码 RAG 平台
在 scipal_rebuild 里建 code 表
RAG 内部自治 agent
500 词硬切
自动 merge 别人代码
```

---

## 14. 参考资料

- [Claude Code agentic grep 拆解](https://dbaplus.cn/news-141-7303-1.html)
- [CodeRAG-Bench](https://aclanthology.org/2025.findings-naacl.176/)
- [RepoBench](https://ar5iv.labs.arxiv.org/html/2306.03091)
- [RepoCoder](https://ar5iv.labs.arxiv.org/html/2303.12570)
- [BioCoder](http://export.arxiv.org/abs/2308.16458)
- [BioCoder benchmark](https://biocoder-benchmark.github.io/)
- [Plot2Code](https://aclanthology.org/2025.findings-naacl.164.pdf)
- [ChartMimic](https://ar5iv.labs.arxiv.org/html/2406.09961)
- [LocAgent](https://aclanthology.org/2025.acl-long.426/)
- [IRCoT](https://aclanthology.org/2023.acl-long.557/)
- [Agentless](https://dl.acm.org/doi/full/10.1145/3715754)
- [Reliable Graph-RAG for Codebases](https://export.arxiv.org/pdf/2601.08773)
- [FlowPilot](https://dlnext.acm.org/doi/pdf/10.1145/3786653)
