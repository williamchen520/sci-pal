# 实验记录：RAG 控制面 R6.5 多 RAG Fanout

> 日期：2026-11-13  
> 状态：**multi_search 三路 fanout 通过；不跨库合并分数**  
> 代码：`services/rag_control/gateway.py`

---

## 1. 原则

```text
显式 rag_ids
分组返回
不把不同 RAG 的 score 硬合并
一个 RAG 失败 -> partial=true
```

## 2. API

```json
POST /api/rag/query
{
  "capability": "multi_search",
  "rag_ids": ["code", "literature", "docs"],
  "library_id": "lib_2c...",
  "query": "single cell normalization",
  "top_k": 1
}
```

返回：

```text
groups:
  code
  literature
  docs
partial: false
```

每个 group 保留自己的：

```text
rag_id
run_id
results
evidence_id
```

## 3. 实测

第一次 code 冷启动 30s 超时：

```text
partial true
code error: timed out
literature ok
docs ok
```

第二次 `timeout=90`：

```text
partial false
code       ok  run qry_b1dc8a07d0ba
literature ok  run qry_b109534e4aa2
docs       ok  run qry_4b1f4234838e
```

三组各 1 条结果。

## 4. DSH

`rag_query` 增加可选：

```text
rag_ids="code,literature,docs"
capability="multi_search"
```

## 5. 验证

```text
tests.test_rag_gateway 5 passed
```

## 6. 边界

```text
没有自动路由分类器
没有跨库去重
没有冲突裁决
没有统一分数
```

这是有意的：不同 RAG 的分数不可直接比较。

## 7. 下一步

```text
去重 / 冲突展示
证据合并的 presentation layer
```


## 证据裁决原则

```text
每个 RAG 分组保留原始证据与分数
不跨库归一化、不投票、不合成唯一结论
机器只能给初步信号：supported / conflicting / insufficient
冲突必须并排展示，不能折叠成一个分数
最终裁决由人完成
```

这不是能力缺失，而是科研平台的责任边界：

```text
机器负责检索、分组、初步判断
人负责证据取舍、冲突裁决、结论署名
```
