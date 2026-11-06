# GraphRAG 插件预设计计划书

> 日期：2026-11-07  
> 状态：预设计，不进入实现  
> 前置原则：SciPal 主架构不变；插件即插即用、用完可去

---

## 1. 背景

SciPal 已有：

```text
citation graph
paper similarity
graph traversal
section / paragraph / sentence tree
figure / table / citation links
communities 基础
```

缺少的是：

```text
实体级语义图
实体关系
社区摘要
global search
```

GraphRAG 补的是后一层，不是替代现有检索。

---

## 2. 核心判断

```text
不把完整 GraphRAG 放进主架构
作为离线索引插件做实验
baseline 永远默认
插件失败回退 baseline
```

原因：

```text
索引成本高
更新困难
实体错误会传播
全局摘要难追溯
可能伤害精确引用问答
```

---

## 3. 目标

验证三个问题：

```text
H1：GraphRAG 是否提升全局/跨论文问题
H2：是否伤害 factoid QA / citation precision
H3：成本与更新延迟是否可接受
```

非目标：

```text
不替换 hybrid retrieval
不替换 citation graph
不进入生产主链路
不自动更新 10k 全量
```

---

## 4. 实验范围

第一阶段：

```text
1,000 篇
5 年分层子集
英文
有全文/摘要
```

第二阶段（仅 H1 通过）：

```text
3,000–5,000 篇
```

不做：

```text
10k 全量首跑
每日增量
多模态图表理解
```

---

## 5. 架构边界

```text
查询
  -> baseline（默认）
  -> query router
       -> global / multi-hop -> graphrag 插件
       -> 其他 -> baseline
```

插件：

```text
plugins/graphrag/
  manifest.json
  indexer.py
  retriever.py
  router.py
  tables: plugin_graphrag_*
```

不修改：

```text
papers / paragraphs / sentences
核心检索路由
核心问答链路
```

---

## 6. 数据模型

插件自有表：

```sql
plugin_graphrag_entities (
  id, name, type, aliases, paper_ids, provenance
)

plugin_graphrag_relations (
  id, source_id, target_id, relation, confidence, provenance
)

plugin_graphrag_communities (
  id, level, member_entity_ids, paper_ids
)

plugin_graphrag_reports (
  id, community_id, summary, model, prompt_version,
  source_paper_ids, source_paragraph_ids
)

plugin_graphrag_runs (
  id, corpus_hash, status, stats, started_at, finished_at
)
```

要求：

```text
每条摘要可追溯 paper/paragraph
每次索引记录 model/prompt/commit
```

---

## 7. 索引管线

```text
1. 选子集
2. 实体抽取
3. 实体归一化
4. 关系抽取
5. 社区检测（Leiden）
6. 社区摘要
7. 写入插件表
8. 建检索索引
```

分阶段：

```text
Phase A：标题 + 摘要实体
Phase B：全文实体
Phase C：关系 + 社区
Phase D：社区摘要
```

先做 Phase A/B，控制成本。

---

## 8. 查询路由

路由信号：

```text
问题是否跨论文
是否问主题/流派/趋势
是否多跳关系
是否要求引用精确
```

策略：

```text
global/multi-hop -> graphrag
factoid/citation  -> baseline
不确定           -> baseline
```

插件失败：

```text
超时/异常 -> baseline
```

---

## 9. 对照

```text
B0  baseline hybrid + citation graph
B1  baseline + RAPTOR（可选）
P1  GraphRAG local
P2  GraphRAG global
```

同 corpus、同 gold、同 generator、同参数。

---

## 10. 评测

全局问题 gold：

```text
优先公开数据
否则 100–300 题人工/半自动候选 + 复核
```

指标：

```text
global answer coverage
citation support
unsupported claim rate
factoid Recall@10 / nDCG
P95 latency
token cost
index build time
```

门槛：

```text
global 指标显著提升
factoid 退化 < 2%
citation support 不下降
成本可接受
```

统计：

```text
paired bootstrap 95% CI
```

---

## 11. 成本估算

需要实测，不先承诺。

记录：

```text
每篇 token
实体数
关系数
社区数
摘要 token
索引小时
存储 GB
```

如果 1k 篇成本已不可接受：

```text
停止，不扩 5k
```

---

## 12. 安全与许可

```text
只用 OA 全文
不把全文发给未授权云端
实体/摘要记录来源
模型/prompt 版本固定
插件表可整体删除
```

---

## 13. 里程碑

### M0 预研（2–3 天）

```text
选 100 篇
跑实体抽取
估算成本
```

### M1 轻量索引（3–5 天）

```text
标题/摘要实体
基础社区
```

### M2 查询原型（3–5 天）

```text
local/global 两种查询
路由开关
```

### M3 评测（3–5 天）

```text
100–300 全局题
baseline 对照
报告
```

### M4 决策

```text
继续扩 5k
或停止
```

---

## 14. 风险

```text
实体抽取质量差
社区摘要幻觉
全局 gold 不足
索引成本超预期
更新延迟高
查询路由误判
```

缓解：

```text
先 100 篇
先摘要级
固定 provenance
baseline 回退
```

---

## 15. 交付物

```text
GraphRAG 插件原型
索引报告
成本报告
评测报告
是否继续的决策建议
```

---

## 16. 决策标准

继续：

```text
global 显著提升
factoid 不退化
成本可接受
```

停止：

```text
成本过高
global 无提升
citation 明显下降
```

---

## 17. 结论

```text
GraphRAG 值得验证
但不值得直接进主架构
先 100 篇预研
再 1k 篇插件实验
最后决定是否扩 5k
```
