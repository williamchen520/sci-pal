# G2.5 pgvector 切流验收

> 日期：2026-11-05  
> 结论：**不通过，生产回滚 Chroma**

## 1. 测试条件

```text
SCIPAL_VECTOR_BACKEND=pgvector
SCIPAL_CONTEXT_WINDOW=2
SCIPAL_ANCHOR_MODE=off
SCIPAL_FTS_PARADEDB_PERCENT=100
GPU reranker
```

## 2. 20 题结果

| Vector | recall@10 | nDCG@10 | MRR |
|---|---:|---:|---:|
| Chroma | 0.75 | 0.4961 | 0.4392 |
| pgvector | **0.70** | **0.4747** | 0.4422 |

结论：

```text
pgvector 仍低于 Chroma
recall -0.05
nDCG   -0.0214
```

## 3. 处理

```text
SCIPAL_VECTOR_BACKEND=chroma
生产回滚
G2.5 不通过
G4 阻塞
```

## 4. 说明

此前离线 pgvector 混合链路 `.7604/.6203` 与生产 API `.70/.4747` 仍存在口径差异：

```text
离线：raw paragraphs
生产：evidence bundle
```

即使 context split 后，生产 pgvector 仍低于 Chroma。

## 5. 当前可选路线

### A. 继续 PG-only，但暂不切向量

```text
G3 写入单栈先做
Chroma 暂时保留
```

### B. PG-only 去向量化

```text
BM25 + GPU rerank
放弃向量通道
```

G0 实测：

```text
BM25 + GPU rerank 96 题
recall .75 / nDCG .6203
```

### C. 继续修 pgvector 生产集成

```text
保留 Chroma
继续 stage trace
```

## 6. 建议

```text
先做 G3 写入单栈
它不依赖向量引擎
可以继续降低 SQLite 技术债
```

向量引擎选择留到 G3 后。

## 7. 当前生产

```text
FTS       100% ParadeDB
Vector    Chroma
Anchor    关闭
Context   window=2
app       healthy
```
