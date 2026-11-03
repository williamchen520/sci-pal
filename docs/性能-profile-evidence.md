# 完整 evidence 请求耗时 Profile

> 日期：2026-11-04  
> 环境：生产容器 `deploy-app-1`，`SCIPAL_FTS_BACKEND=sqlite`  
> 方法：`UnifiedRetriever(diagnostics=True)` + `cProfile`

## 1. 结论

```text
完整请求不是 PG FTS 慢
主要耗时在 4 个 query variant 的向量编码/线程等待
```

## 2. 单次 retrieve（rerank=False）

```text
total_ms       114,680 ms（约 115s）
abstracts       2,791 ms
parent_contexts    0.01 ms
```

诊断只覆盖了 `abstracts` / `parent_contexts`；`searcher.search` 内部阶段没有进入 Unified diagnostics。

## 3. cProfile（rerank=False）

```text
total 122.4s

vector_search        4 calls   cum 469s（线程累计）
  threading.wait            109s
  chromadb query             7.9s
  sentence encode            4.0s/次
```

关键点：

```text
4 个 query variant
每个都做 vector_search
torch / threading 大量等待
CPU 被打满
```

## 4. 摘要 FTS 仍有一个错误

```text
摘要 FTS 搜索失败: fts5: syntax error near "?"
```

原因：

```text
AbstractSearch.fts_search 直接把带 ? 的原始 query 传给 FTS5 MATCH
```

已修：

```text
提取 alnum terms
拼接 OR 查询
不再把 ? 传给 FTS5
```

影响：

```text
摘要 FTS 通道回退
只靠摘要向量命中
```

## 5. rerank=True

尝试 profile 时进程运行 30+ 分钟未完成，CPU 99%，已停止。

说明：

```text
完整 rerank 路径在当前单机 CPU 上不可用于在线请求
```

## 6. 优化优先级

```text
1. 关闭/减少 multi-query variants（4 -> 1/2）
2. 串行或 batch encode，避免 4 个 encode 并发争抢
3. 摘要 FTS query 清洗（去掉 ? 等 FTS 语法字符）
4. 再 profile rerank=True
5. 最后才评估 PG FTS 是否接入
```

## 7. 结论

```text
PG FTS 4s 不是端到端瓶颈
端到端瓶颈是 query expansion + 向量编码 + rerank
在这些不收敛前，不应继续切 FTS 后端
```

## 8. 当前生产

```text
SCIPAL_FTS_BACKEND=sqlite
app healthy
摘要库已恢复
```
