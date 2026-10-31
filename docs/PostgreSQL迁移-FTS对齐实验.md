# PostgreSQL FTS 对齐实验

> 日期：2026-11-01  
> 目的：判断 P3 发现的 SQLite / PostgreSQL FTS 差异，能否通过 tokenizer / stemmer 对齐解决。  
> 结论：**porter + PostgreSQL english 最好**；但排序仍不同，FTS 切流前需要重建 SQLite FTS。

---

## 1. 实验设计

只读 snapshot，不改生产 SQLite，不改 PostgreSQL schema。

对比四组：

```text
SQLite unicode61  vs PG english   （当前组合）
SQLite porter     vs PG english   （候选）
SQLite unicode61  vs PG simple
SQLite porter     vs PG simple
```

SQLite porter：

```sql
CREATE VIRTUAL TABLE paragraphs_fts_porter USING fts5(
  para_id UNINDEXED,
  paper_id UNINDEXED,
  text,
  tokenize='porter'
);
```

PostgreSQL：

```sql
-- english
search_vector @@ websearch_to_tsquery('english', :q)

-- simple
to_tsvector('simple', text) @@ websearch_to_tsquery('simple', :q)
```

查询：

```text
hepatocellular carcinoma
immune checkpoint inhibitor
tumor microenvironment
```

指标：

```text
match_jaccard：全量命中集合的 Jaccard
top_common：top-10 交集
sqlite_top_in_pg：SQLite top-10 有多少落在 PG 全量命中集
postgres_top_in_sqlite：PG top-10 有多少落在 SQLite 全量命中集
```

---

## 2. 结果

| query | SQLite | PG | match Jaccard | top-10 common | SQLite top in PG | PG top in SQLite |
|---|---|---|---:|---:|---:|---:|
| hepatocellular carcinoma | unicode61 | english | 0.757 | 0 | 10 | 10 |
| hepatocellular carcinoma | porter | english | **0.986** | 0 | 10 | 10 |
| hepatocellular carcinoma | unicode61 | simple | 0.761 | 0 | 10 | 10 |
| hepatocellular carcinoma | porter | simple | 0.979 | 0 | 10 | 10 |
| immune checkpoint inhibitor | unicode61 | english | 0.326 | 1 | 9 | 4 |
| immune checkpoint inhibitor | porter | english | **0.990** | 2 | 10 | 10 |
| immune checkpoint inhibitor | unicode61 | simple | 0.841 | 3 | 8 | 10 |
| immune checkpoint inhibitor | porter | simple | 0.340 | 3 | 6 | 10 |
| tumor microenvironment | unicode61 | english | 0.828 | 2 | 10 | 10 |
| tumor microenvironment | porter | english | **0.992** | 0 | 10 | 10 |
| tumor microenvironment | unicode61 | simple | 0.869 | 2 | 10 | 10 |
| tumor microenvironment | porter | simple | 0.929 | 0 | 10 | 10 |

平均 match Jaccard：

```text
unicode61 vs english   0.637
porter    vs english   0.989
unicode61 vs simple    0.824
porter    vs simple    0.749
```

---

## 3. 解读

### 3.1 porter + english 最接近

```text
porter vs english:
  match Jaccard 0.986 / 0.990 / 0.992
  SQLite top-10 全部落在 PG 全量命中集
```

说明：

```text
P3 的“命中集合差异”主要来自 stemming，不是数据丢失。
SQLite 改成 porter 后，和 PG english 的 match 语义基本一致。
```

### 3.2 simple 不是更好

```text
porter vs simple 在 immune checkpoint inhibitor 上只有 0.340
```

原因：

```text
simple 不做 stemming：
  inhibitor 与 inhibitors 不合并
  english 会合并
```

所以：

```text
不要为了“看起来简单”把 PG 改成 simple。
```

### 3.3 排序仍不同

即使 porter + english：

```text
top-10 common 仍只有 0–2
```

原因：

```text
SQLite: bm25
PG: ts_rank_cd
```

但：

```text
SQLite top-10 全在 PG 全量命中集
```

说明召回没坏，只是排序不同。

---

## 4. 建议

### 如果要做 FTS 切流

推荐顺序：

```text
1. 重建 SQLite FTS，tokenizer 改为 porter
2. 保持 PostgreSQL english
3. 用 20+ query 做 top-k / nDCG 对比
4. 排序差异单独评审，不混在 schema 迁移里
```

不要：

```text
直接把 SQLite unicode61 切到 PG english
直接把 PG 改成 simple
```

### 如果暂时不切 FTS

```text
P4 双写只写元数据表
FTS 继续走 SQLite
等 porter 重建 + 20+ query 验证后再切
```

---

## 5. 复现

```powershell
$env:SCIPAL_PG_DSN = "postgresql://..."

python scripts\fts_alignment.py `
  --source backups\research_20261031_210616.db `
  --out docs\PostgreSQL迁移-FTS对齐实验.json
```

输出：

```text
docs/PostgreSQL迁移-FTS对齐实验.json
```

---

## 6. 限制

```text
只测 3 个 query
只测 top-10
没有 nDCG / MRR
没有统计显著性
porter 与 english 都是 Porter/Snowball 家族，但不是完全同一个实现
```

下一步如果要切 FTS，应扩到 20+ query，并加 nDCG/MRR。
