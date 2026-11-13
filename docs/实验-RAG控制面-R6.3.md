# 实验记录：RAG 控制面 R6.3 多 RAG 路由

> 日期：2026-11-13  
> 状态：**code + literature 路由；docs 未接**  
> 代码：`services/rag_control/gateway.py`、`scripts/rag_worker.py`

---

## 1. 能力

```text
code_search      -> code RAG
evidence_search  -> literature RAG
docs             -> 未接（没有 HTTP 入口）
```

不把 docs 伪装成可用。

## 2. Literature 路由

```text
POST /api/rag/query
{
  "capability": "evidence_search",
  "query": "single cell normalization",
  "top_k": 2
}
```

内部调用：

```text
POST /api/evidence/search
X-SCIPAL-Internal-Token
```

真实结果：

```text
run       qry_46e6dc2f681a
rag_id    literature
results   2
first     paper_PMC13632004
evidence  ev_f3a1a8c9f043
evidence  2
```

Evidence 字段：

```text
source_path  literature/<paper_id>/<para_id>
paper_id / para_id
sentence_ids
content_hash
score
```

## 3. Worker

`rag_query` 按 `rag_id` 分流：

```text
code        -> code API search
literature  -> /api/evidence/search
```

两边都走 `complete(evidence=...)`，run/evidence 同事务。

## 4. DSH

`rag_query` 的 `library_id` 改为可选：

```text
code_search     需要 library_id
evidence_search 不需要
```

## 5. 验证

```text
tests.test_rag_query_worker 2 passed
tests.test_rag_gateway      3 passed
```

真实 literature gateway smoke 通过，随后删除测试 run。

## 6. 边界

```text
docs 没接
没有跨 RAG fanout
没有多 RAG 证据合并
没有路由分类器
```

## 7. 下一步

```text
docs RAG 暴露 HTTP 入口
capability 路由与 fanout
```
