# 实验记录：RAG 控制面 R6.4 Docs 路由

> 日期：2026-11-13  
> 状态：**docs provider/API/gateway/worker/DSH live 通过**  
> 代码：`docs_rag/api.py`、`services/rag_control/gateway.py`

---

## 1. 之前缺什么

```text
scipal_docs 有 438 docs / 5885 chunks
docs_rag 有 search.py
但只有 CLI，没有 HTTP provider
```

## 2. 新增

```text
docs_rag/api.py
  GET  /health
  POST /search
```

provider：

```text
docs endpoint http://127.0.0.1:5011
capability doc_search
```

## 3. Gateway

```text
capability=doc_search -> docs API /search
  -> run (rag_id=docs)
  -> evidence (source_path/doc_id/title/heading)
```

## 4. Worker

`rag_query` 增加 docs 分支；evidence 随 complete 写同一 run。

## 5. DSH live

```text
rag_query
  capability=doc_search
  query="MCP tool"
  top_k=2
```

结果：

```text
run       qry_a46954943e15
rag_id    docs
results   2
evidence  ev_29093c2ab042
          ev_d421f77aefe4
```

provider health：

```text
docs active
latency 316 ms
```

## 6. 持久化

docs API 也由 Task Scheduler 管理：

```text
SciPalDocsApiCmd
G:\runs\start_docs_api.cmd
```

Startup：

```text
SciPalDocsApi.vbs
```

端口守卫：

```text
5011 LISTENING -> 不再起第二份
```

## 7. 验证

```text
tests.test_rag_query_worker 3 passed
tests.test_rag_gateway      3 passed
docs search live            2 hits
provider health             active
```

## 8. 当前能力

```text
code_search       PASS
evidence_search   PASS
doc_search        PASS
```

## 9. 仍未做

```text
跨 RAG fanout
证据合并/冲突展示
路由分类器
```
