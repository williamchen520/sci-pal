# P4 句子级 FTS

> 日期：2026-11-01  
> 目标库：`scipal_v2`  
> 原则：XML 返回 XPath；PDF 返回 page/bbox；metadata_only 不进入 FTS。

---

## 1. 实现

```text
services/search/sentence_fts.py
scripts/query_v2_fts.py
```

查询：

```sql
SELECT sentence, paragraph, section, paper, page, bbox, source_path,
       ts_rank(search_vector, websearch_to_tsquery('english', query))
FROM sentences
WHERE search_vector @@ query
  AND (source_type = 'xml' OR source_type = 'pdf')
ORDER BY rank DESC
```

不查 `paragraphs`，不把句子降级成段落。

---

## 2. 返回契约

### XML

```text
source_type = xml
source_path = /article/body/sec[1]/p[1]#sentence-1
page = NULL
bbox = NULL
```

### PDF

```text
source_type = pdf
page = 5
bbox = 323.87,719.31,532.99,730.15
source_path = /paragraphs/34
```

### metadata_only

```text
没有 sentence
不会出现在 FTS
```

---

## 3. 实测

### XML 查询

```text
query: diabetes
source_type: xml
返回：sentence → paragraph → section → paper
source_path: /article/body/sec[2]/sec[1]/p[1]#sentence-2
page/bbox: NULL
```

### PDF 查询

```text
query: hepatocellular carcinoma
source_type: pdf
返回：sentence → paragraph → section → paper
page: 5
bbox: 323.87,719.31,532.99,730.15
```

---

## 4. 聚合

```text
句子级检索
→ aggregate_by_paragraph
→ 每个段落保留最高 rank 句子
→ 保留该段所有命中 sentence_ids
```

论文级聚合后续在检索层做。

---

## 5. 当前边界

```text
P4 只实现 v2 句子级 FTS
还没有切生产 API
生产仍使用旧 HybridSearch
```

切换需要：

```text
SCIPAL_PG_V2_DSN
search backend = v2_sentence
20 query 对比
```

---

## 6. 验收

```text
XML 能回 XPath
PDF 能回 page/bbox
metadata_only 不出现
句子级 rank
段落聚合
```

## 7. 20-query evaluation

Full report: [P4 sentence-level FTS evaluation](数据重建-P4-句子级FTS评估.md)

| System | Recall@10 | MRR | nDCG@10 |
|---|---:|---:|---:|
| paragraph_fts | 1.0000 | 0.8806 | 0.9097 |
| sentence_fts | 0.9000 | 0.6250 | 0.6943 |

Decision: do not switch the production paper ranker to sentence FTS yet. Keep it for sentence traceability and evidence; keep paragraph FTS for paper-level ranking.
