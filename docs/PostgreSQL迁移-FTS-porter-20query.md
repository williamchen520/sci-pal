# SQLite FTS porter 重建与 20 Query 对比

> 日期：2026-11-01  
> 目的：验证 porter 重建是否能在真实 query 上改善 SQLite / PG FTS 对齐。  
> 结论：**porter 改善了 match 集合对齐，但没有改善 paper-level 检索；暂不切换生产 FTS。**

---

## 1. 重建

脚本：

```text
scripts/rebuild_fts_porter.py
```

只重建副本：

```text
source: backups/research_20261031_210616.db
target: backups/research_porter.db
```

结果：

```text
paragraphs_indexed   166,347
papers_indexed         3,310
paragraphs_fts_rows  166,347
papers_fts_rows        3,310
integrity             ok
```

重建内容：

```text
paragraphs_fts  tokenize='porter'
papers_fts      tokenize='porter'
```

触发器：

```text
paragraphs_ai/ad/au
papers_ai/ad/au
```

已按 `section_l1 / section_l2` 重建。

源库未修改。

---

## 2. 20 Query 设计

从：

```text
eval/plugins/retriever_queries.json
```

按来源各取 5 条：

```text
seed_100          5
cross_topic       5
claim_qualifiers  5
paper_title       5
= 20 queries
```

查询构造：

```text
FTSQueryBuilder._extract_keywords
去掉停用词
最多 8 个 term
SQLite: term1 OR term2 ...
PG:     term1 | term2 ...
```

评估：

```text
paper-level
gold_paper_ids
Recall@10
MRR
nDCG@10
```

每个 query 都是单 gold paper。

---

## 3. 结果

| system | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|
| SQLite unicode61 | **1.000** | 0.881 | **0.910** |
| SQLite porter | 0.950 | **0.892** | 0.907 |
| PostgreSQL english | 0.600 | 0.319 | 0.386 |

按来源 Recall@10：

| source | unicode61 | porter | PG english |
|---|---:|---:|---:|
| seed_100 | 1.00 | 1.00 | 1.00 |
| cross_topic | 1.00 | 0.80 | 0.20 |
| claim_qualifiers | 1.00 | 1.00 | 0.60 |
| paper_title | 1.00 | 1.00 | 0.60 |

---

## 4. 解读

### 4.1 porter 的匹配集合更好，但检索没更好

前一轮 FTS 对齐实验：

```text
porter vs english match Jaccard 0.989
unicode61 vs english       0.637
```

但 20 query paper-level：

```text
unicode61 Recall@10 1.000
porter    Recall@10 0.950
```

说明：

```text
match 集合对齐 ≠ 检索质量提升。
porter 可能过度词干化，改变了 term 权重与排序。
```

### 4.2 PG 的主要问题不是 stemming，是 ranking

即使匹配集合对齐，PG：

```text
Recall@10 0.600
MRR      0.319
nDCG@10  0.386
```

明显低于 SQLite bm25。

原因：

```text
SQLite: bm25
PG:     ts_rank_cd
```

`ts_rank_cd` 不是 BM25；在 OR 查询下，长段落/覆盖度会改变排序。

### 4.3 目前不能切 FTS

证据：

```text
1. porter 让 Recall@10 从 1.000 降到 0.950
2. PG english 只有 0.600
3. 20 query 都是单 gold，已是最宽松设置
```

结论：

```text
FTS 继续走 SQLite unicode61。
P4 双写只覆盖元数据表，不切 FTS。
```

---

## 5. 建议

### 短期

```text
保持 SQLite unicode61
不重建生产 FTS
P4 只双写 papers / paragraphs / sentences / claims 等元数据
```

### 中期如果要切 FTS

至少要做：

```text
1. PG 侧使用 BM25 类排序，或实现自定义 rank
2. 20+ query / 多 gold 的 nDCG 评测
3. 对比 ts_rank / ts_rank_cd / 归一化参数
4. 人工检查 cross_topic 查询
```

不要只用：

```text
match Jaccard
top-10 交集
```

就判断 FTS 可切换。

---

## 6. 产物

```text
scripts/rebuild_fts_porter.py
scripts/fts_porter_compare.py
docs/PostgreSQL迁移-FTS-porter-rebuild.json
docs/PostgreSQL迁移-FTS-porter-20query.json
```

复现：

```powershell
python scripts\rebuild_fts_porter.py `
  --source backups\research_20261031_210616.db `
  --target backups\research_porter.db

$env:SCIPAL_PG_DSN = "postgresql://..."

python scripts\fts_porter_compare.py `
  --unicode-source backups\research_20261031_210616.db `
  --porter-source backups\research_porter.db `
  --out docs\PostgreSQL迁移-FTS-porter-20query.json
```

---

## 7. 限制

```text
20 query，每个 1 个 gold paper
query 是 OR 关键词构造，不是线上完整 FTS query
没有人工相关性标注
只比较 paper-level，不比较段落级
没有统计显著性
```

这是“是否值得继续投入 FTS 切流”的止损实验，不是最终 benchmark。
