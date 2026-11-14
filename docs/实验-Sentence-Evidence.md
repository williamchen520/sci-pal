# 实验记录：Sentence Evidence 与 Caption 过滤

> 日期：2026-11-14  
> 状态：段落向量召回 + 句级 FTS 已接；句向量未做  
> 目标：补上 `paper → paragraph → sentence → evidence`

---

## 1. Caption 过滤

问题：

```text
section=Results
第一段返回 Fig. 2 caption
```

修复：

```text
paper_paragraphs(..., include_captions=False)
paper_first_paragraph(..., include_captions=False)
```

默认排除：

```text
figure_caption
table_caption
```

需要图注时显式：

```text
include_captions=1
```

---

## 2. Sentence Evidence

新增：

```text
services/papers/evidence.py
```

接口：

```text
POST /api/papers/<paper_id>/evidence
```

请求：

```json
{"query": "lycopene chiglitazar", "top_k": 8}
```

返回：

```text
sentence_id
para_id
section_level1/2/path
text
page / bbox
char_start / char_end
score
```

实现：

```text
paragraph_embeddings
  -> 段落向量召回候选段
  -> sentences.search_vector
       @@ websearch_to_tsquery('english', query)
  -> ts_rank_cd
  -> paper_id scoped
```

返回字段增加：

```text
match_type
  paragraph_vector+sentence_fts
  sentence_fts（模型不可用 fallback）
```

---

## 3. 真实数据

```text
paper_nature_hcc_lipid_macrophage_b3cb651d2d57

query: lycopene chiglitazar
hits: 3
match_type: paragraph_vector+sentence_fts

query: immunosuppressive lipid macrophages
hits: 2
match_type: paragraph_vector+sentence_fts
```

命中：

```text
para_0008_sent_005
para_0039_sent_003
para_0050_sent_012
```

---

## 4. 路由/测试

```text
json_routes=257
app_routes=257
OK
```

```text
test_paper_reader   4 passed
test_paper_evidence 2 passed
```

---

## 5. 边界

```text
已有段落向量召回
没有 sentence embedding
没有跨 RAG 合并
HTTP 路由尚未在新 app 进程验证
```

段落向量负责语义召回，句级 FTS 负责精确证据。

```text
figure_caption / table_caption 已排除
```

---

## 6. 下一步

```text
1. app 重启后验证 evidence HTTP
2. sentence embedding（可选）
3. scipal-paper 接入
```
