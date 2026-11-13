# 实验记录：RAG 控制面 R2 模型与索引绑定

> 日期：2026-11-13  
> 状态：**模型注册 + index binding 可用；无执行 worker**  
> 代码：`services/rag_control/models.py`

---

## 1. 目标

```text
模型注册
embedding 维度记录
index binding
换模型必须新 index
```

## 2. 模型

```text
BAAI/bge-small-zh-v1.5   embedding 512
BAAI/bge-base-en-v1.5    embedding 768
BAAI/bge-reranker-base   rerank
```

种子：

```bash
python scripts/seed_rag_models.py
```

## 3. Binding

表：

```text
rag_index_bindings
  rag_id
  library_id
  index_name
  embedding_model
  dimension
  snapshot
  status
```

API：

```text
GET  /api/rag/models
GET  /api/rag/models/<id>
GET  /api/rag/index-bindings
POST /api/rag/index-bindings   worker token
```

## 4. 验证

建立：

```text
code / lib_2c... / code_units
BAAI/bge-small-zh-v1.5
dimension 512
```

换模型：

```text
BAAI/bge-base-en-v1.5
-> blocked: model change requires a new index; reindex instead
```

测试：

```text
tests.test_rag_models 4 passed
tests.test_rag_plans  5 passed
tests.test_rag_control 5 passed
validate_arch 228/228 OK
```

## 5. 当前缺口

```text
binding 需要 worker 注册
没有自动 reindex
没有 evidence/artifact
没有真正查询路由
```

## 6. 下一步 R3

```text
local worker
  lease -> execute code_ingest -> complete
  register binding
```

R2 只保证“模型和索引不能静默错配”。
