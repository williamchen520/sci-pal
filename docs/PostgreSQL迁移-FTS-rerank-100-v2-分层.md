# PG FTS + Rerank 100 Query v2：候选 100 + RRF

> 日期：2026-11-04  
> 数据：`docs/PostgreSQL迁移-FTS-rerank-100-v2.json`  
> 变更：candidates 50 -> 100；加入 PG rank + rerank RRF

## 1. 总体

```text
n = 100
SQLite nDCG        0.466
PG raw nDCG        0.319
PG+rerank nDCG     0.501
PG+rerank+RRF      0.470
```

延迟：

```text
PG 候选 3.72s + rerank 2.07s
```

## 2. candidates 50 -> 100

| 指标 | 50 | 100 |
|---|---:|---:|
| PG+rerank nDCG | 0.496 | **0.501** |
| factual | 0.756 | 0.751 |
| auto | 0.493 | **0.508** |
| methods | 0.625 | 0.533 |
| comparison | 0.418 | 0.418 |

结论：

```text
候选 100 对 auto 有收益
factual 基本持平
methods 小样本回退
```

## 3. RRF 分层

排除 refusal 后：

| category | n | SQLite | rerank | RRF | 更优 |
|---|---:|---:|---:|---:|---|
| factual | 11 | 0.615 | **0.751** | 0.656 | rerank |
| comparison | 5 | **0.447** | 0.418 | 0.393 | SQLite |
| qualifier | 3 | 0.438 | 0.544 | **0.667** | RRF |
| methods | 4 | 0.563 | 0.533 | **0.750** | RRF |
| multi_hop | 4 | 0.241 | 0.247 | **0.408** | RRF |
| auto | 69 | 0.479 | **0.508** | 0.452 | rerank |

结论：

```text
RRF 总体低于纯 rerank（0.470 vs 0.501）
但不是所有类别都差
```

## 4. 策略

```text
factual / auto       -> rerank only
comparison           -> SQLite
qualifier/methods/multi_hop -> RRF
```

注意：

```text
qualifier/methods/multi_hop 样本只有 3–4 条
结论是方向性的，不是统计显著
```

## 5. 回退归因

```text
候选漏：q006/q008/q020/q059/q060/q063
rerank 降权：q014/q028/q070/q083
```

候选 100 改善了部分漏召回，但没有完全消除。

## 6. 下一步

```text
1. 按 category 路由打分策略
2. comparison 保持 SQLite
3. 延迟从 5.8s 压到 1s 级
4. 再扩大 factual/auto 样本
```

## 7. 结论

```text
统一策略不如分类策略
RRF 不应全局启用
rerank 仍是 factual/auto 的最佳单项
```

生产仍走 SQLite FTS。
