# 实验记录：Sentence Evidence 与 Caption 过滤

> 日期：2026-11-14  
> 状态：句级证据 API 可用；先做句级 FTS，段落向量召回下一步接  
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
sentences.search_vector
  @@ websearch_to_tsquery('english', query)
ts_rank_cd
paper_id scoped
```

当前是纯句级 FTS，不是段落向量链。

---

## 3. 真实数据

```text
paper_nature_hcc_lipid_macrophage_b3cb651d2d57
query: lycopene chiglitazar
hits: 3
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
没有段落向量召回
没有 sentence embedding
没有跨 RAG 合并
HTTP 路由尚未在新 app 进程验证
```

句子 FTS 只能解决“精确词命中”；

```text
“免疫抑制微环境”这类语义查询
仍需要 paragraph vector recall
```

---

## 6. 下一步

```text
1. paragraph vector recall -> sentence FTS
2. app 重启后验证 evidence HTTP
3. scipal-paper 接入
```
