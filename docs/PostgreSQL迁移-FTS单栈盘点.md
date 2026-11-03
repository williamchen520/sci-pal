# PostgreSQL FTS 单栈盘点

> 日期：2026-11-03  
> 范围：SQLite FTS5 与 PostgreSQL tsvector 的现状、覆盖、差异、切换条件  
> 结论：**PG FTS 数据面基本完整，查询/排序/覆盖仍有阻塞，暂不能切单栈**

---

## 1. 当前 FTS 全景

### SQLite FTS5

| 表 | 行数 | 基表行数 | 缺失 | tokenizer |
|---|---:|---:|---:|---|
| `papers_fts` | 3,313 | 3,313 | 0 | unicode61 remove_diacritics 2 |
| `paragraphs_fts` | 167,388 | 167,388 | 0 | unicode61 remove_diacritics 2 |
| `sentences_fts` | 862,677 | 862,677 | 0 | 默认 unicode61 |
| `summaries_fts` | 69,128 | 69,128 | 0 | 默认 unicode61 |

### PostgreSQL

| 表 | `search_vector` 覆盖 | 索引 |
|---|---:|---|
| `papers` | 3,313 / 3,313 | GIN `papers_search_idx` |
| `paragraphs` | 167,388 / 167,388 | GIN `paragraphs_search_idx` |
| `sentences` | 862,677 / 862,677 | GIN `sentences_search_idx` |
| `summaries` | 69,128 / 69,128 | GIN `summaries_search_idx` |

生成方式：

```sql
to_tsvector('english', ...)
```

`papers` 使用 `title + abstract`；`paragraphs` / `sentences` 使用 `text`；`summaries` 使用 `title + text`。

---

## 2. 生产查询路径

### 仍走 SQLite FTS

```text
services/search/hybrid_search.py
  paragraphs_fts MATCH ?
  ORDER BY bm25(paragraphs_fts)

services/search/summary_search.py
  summaries_fts MATCH ?
  ORDER BY bm25(summaries_fts)

services/claims/service.py
  sentences_fts MATCH ?

services/quality/guard.py
  paragraphs_fts MATCH ?

services/search/abstract_search.py
  papers_fts MATCH ?（摘要库）
```

### PG FTS 现状

```text
services/search/sentence_fts.py
  SentenceFTS
  sentences.search_vector @@ websearch_to_tsquery('english', ?)
```

但 `SentenceFTS` 目前只被实验脚本和测试使用：

```text
scripts/fts_*.py
scripts/sentence_20_query.py
tests/test_sentence_fts.py
```

**生产检索没有使用 PG FTS。**

---

## 3. 已做过的一致性实验

`docs/PostgreSQL迁移-FTS对齐实验.md`：

| 组合 | match Jaccard |
|---|---:|
| SQLite unicode61 vs PG english | 0.637 |
| SQLite porter vs PG english | **0.989** |
| SQLite unicode61 vs PG simple | 0.824 |
| SQLite porter vs PG simple | 0.749 |

结论：

```text
SQLite 当前 unicode61 与 PG english 的词项匹配差异主要来自 stemming
改成 porter 后，匹配集合基本对齐
但 top-10 排序仍不同
```

排序差异：

```text
SQLite: bm25
PG:     ts_rank_cd
```

即使 porter + english：

```text
top-10 common 只有 0–2
但 SQLite top-10 全部落在 PG 全量命中集
```

说明：

```text
召回没坏
排序不同
```

---

## 4. 阻塞单栈的五个问题

### 4.1 覆盖率缺口（已修复）

修复前：

```text
paragraphs_fts 缺 923 条
summaries_fts 缺 7,196 条
```

2026-11-03 已补齐：

```text
paragraphs_fts 167,388 = paragraphs 167,388
summaries_fts  69,128 = summaries  69,128
```

并新增 `summaries_ai/ad/au` trigger，防止后续再漏。

### 4.2 Tokenizer 不对齐

```text
SQLite: unicode61
PG:     english
```

差异：

```text
inhibitor / inhibitors
tumor / tumours
```

Porter + english 才能接近。

### 4.3 排序函数不同

```text
SQLite bm25
PG ts_rank_cd
```

同一个命中集，top-k 顺序不同。

### 4.4 Query 语法不同

SQLite 侧有：

```text
FTSQueryBuilder
AND / OR / NEAR / 短语 / 实体加权
```

PG 侧目前：

```text
websearch_to_tsquery
```

不支持同样的 NEAR/短语/权重表达。

需要一层 **FTS query translator**。

### 4.5 中文 / CJK

```text
PG english 不适合中文
SQLite unicode61 也不是中文分词器
```

如果产品有中文检索，需要：

```text
PG simple + pg_trgm
或 zhparser / pg_jieba
或应用层分词
```

这需要单独决策，不能直接用 english 配置。

---

## 5. 单栈目标架构

```text
PG:
  papers.search_vector
  paragraphs.search_vector
  sentences.search_vector
  summaries.search_vector
  GIN 索引

应用:
  PGParagraphFTS
  PGSummaryFTS
  PGSentenceFTS
  FTSQueryTranslator

SQLite:
  只保留迁移/导入
  不再承担运行时 FTS
```

---

## 6. 推荐迁移顺序

### 阶段 1：补数据覆盖

```text
重建 SQLite FTS，确认 923 paragraphs / 7,196 summaries
或确认这些缺失是否预期
```

### 阶段 2：PG FTS 适配器

```text
PGParagraphFTS
PGSummaryFTS
PGSentenceFTS
统一 query translator
```

### 阶段 3：影子对比

```text
同一 query
SQLite top-k vs PG top-k
记录 recall / nDCG / overlap / latency
```

### 阶段 4：逐通道切换

```text
summaries -> paragraphs -> sentences
每次只切一个通道
保留 SQLite fallback
```

### 阶段 5：删除 SQLite FTS

```text
确认 30 天无回退
删除 FTS5 表/trigger
P6 归档
```

---

## 7. 验收指标

```text
Recall@10 不低于当前 0.6615
nDCG@10 不低于当前 0.5034
top-10 overlap 可解释
P95 延迟不高于当前
无 SQLite FTS 依赖
```

---

## 8. 结论

```text
PG FTS 数据面：基本完整
PG FTS 查询面：未接入生产
tokenizer：需 porter 对齐或接受差异
ranking：bm25 vs ts_rank_cd 必须单独评审
coverage：已补齐 0 / 0
中文：未解决
```

最终判断：

```text
可以继续做 PG FTS 单栈
但现在不能直接切
先做 PGParagraphFTS / PGSummaryFTS + 影子对比
再做通道级切换
```

---

## 9. 2026-11-03 影子对比结果

20 query，top-10：

```text
paragraph avg Jaccard 0.020
summary   avg Jaccard 0.242
```

典型：

```text
q001 / q002 paragraph common 0/10
q004 paragraph common 3/10
q002 summary common 7/10
```

PG paragraph 查询耗时：

```text
约 5–22 秒 / query（12 个 OR term）
SQLite 约 0.1–0.2 秒
```

结论：

```text
PG FTS 能返回结果
但 ranking 差异过大
且延迟不可接受
不能切
```

### 9.1 v2：限制 term + match recall

参数：

```text
term_limit=6
ranker=ts_rank
```

结果：

```text
paragraph Jaccard     0.109
paragraph match recall 0.975
summary   Jaccard     0.313
summary   match recall 1.000
```

解读：

```text
SQLite top-10 有 97.5% 落在 PG 命中集
PG 召回基本没问题
差距主要在 ranking
```

延迟仍高：

```text
PG paragraph 3.5–16 秒/query
```

根因：

```text
EXPLAIN ANALYZE:
  Parallel Seq Scan on paragraphs
  Filter: search_vector @@ tsquery

宽泛 OR term 命中约 55% 行
规划器放弃 GIN，改全表扫描
```

候选召回实验：

```text
PG recall LIMIT 200 无 ORDER BY
paragraph recall 0.08
summary   recall 0.31
```

结论：

```text
无排序 LIMIT 不是 top 200 召回
需要 term frequency / rare-term 选择
```

### 9.2 v4：term frequency / rare-term

统计表：

```text
paragraphs 394,025 terms
summaries   84,059 terms
sentences  393,781 terms
```

结果：

```text
paragraph Jaccard      0.200
paragraph match recall 0.975
summary Jaccard        0.411
summary match recall   0.985
```

延迟：

```text
2.5–5.2 秒/query
```

结论：

```text
rare-term 选词明显改善 Jaccard
match recall 保持 0.975/0.985
ranking 仍是主要差距
```

### 9.3 v5：PG 候选 + cross-encoder rerank

20 query：

```text
SQLite nDCG        0.532
PG raw nDCG        0.343
PG + rerank nDCG   0.633
```

延迟：

```text
PG 候选 3.14s + rerank 1.53s
```

解读：

```text
PG raw 排序差
cross-encoder 能纠正大部分排序
PG 候选召回足够（v4 recall 0.975）
```

### 9.4 v6：100 query 扩样

```text
SQLite nDCG        0.466
PG raw nDCG        0.319
PG + rerank nDCG   0.496
```

提升：

```text
+0.030 vs SQLite
```

延迟：

```text
PG 3.79s + rerank 1.32s
```

解读：

```text
20 query 的 +0.101 有样本偶然性
100 query 仍有正收益，但缩小到 +0.030
PG raw 明显低，reranker 必要
```

### 9.5 v7：candidates 100 + RRF

```text
SQLite       0.466
PG+rerank    0.501
PG+RRF       0.470
```

分层：

```text
factual / auto   -> rerank only
comparison       -> SQLite
qualifier/methods/multi_hop -> RRF
```

RRF 全局启用会拉低总体，不能一刀切。

### 9.6 延迟目标 2s 实验

```text
term4 / cand100   5.79s   nDCG .501
term3 / cand50    4.16s   nDCG .623
term2 / cand50    2.74s   nDCG .513
SQLite            0.2s    nDCG .532
```

结论：

```text
2s 与质量不可兼得
term2 达到 2.7s，但低于 SQLite
term3 质量好，但 4.2s
```

可选路线：

```text
接受 3–4s
SQLite 候选 + PG rerank（非单栈）
ParadeDB / OpenSearch 专用 FTS
```

## 10. 下一步

```text
1. 补 SQLite FTS 覆盖缺口
2. 实现 PGParagraphFTS + PGSummaryFTS
3. 用现有 96 题做 SQLite/PG 影子对比
4. 先切 summaries，再切 paragraphs
5. 最后处理 sentences / 中文
```
