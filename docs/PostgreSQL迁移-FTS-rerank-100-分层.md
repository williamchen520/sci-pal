# PG FTS + Rerank 100 Query 分层分析

> 日期：2026-11-04  
> 数据：`docs/PostgreSQL迁移-FTS-rerank-100.json`  
> 样本：100 query，top-10，candidates=50

## 1. 总体

排除 4 条 refusal（无 gold paragraph）：

```text
n = 96
SQLite nDCG        0.486
PG + rerank nDCG   0.517
提升               +0.031
```

## 2. 按 category

| category | n | SQLite | PG raw | PG+rerank | Δ vs SQLite | W/L/T |
|---|---:|---:|---:|---:|---:|---:|
| factual | 11 | 0.615 | 0.358 | **0.756** | **+0.141** | 4/2/5 |
| qualifier | 3 | 0.438 | 0.310 | 0.544 | +0.105 | 1/0/2 |
| methods | 4 | 0.563 | 0.500 | 0.625 | +0.062 | 2/1/1 |
| multi_hop | 4 | 0.241 | 0.339 | 0.254 | +0.013 | 1/1/2 |
| auto | 69 | 0.479 | 0.319 | 0.493 | +0.014 | 11/9/49 |
| comparison | 5 | 0.447 | 0.326 | 0.418 | **-0.029** | 2/1/2 |
| refusal | 4 | 0.000 | 0.000 | 0.000 | 0 | 0/0/4 |

## 3. 解读

### 收益明确

```text
factual    +0.141
qualifier  +0.105（样本小）
methods    +0.062（样本小）
```

### 基本持平

```text
auto       +0.014
multi_hop  +0.013
```

`auto` 中：

```text
49/69 完全持平
11 胜
9 负
```

说明：

```text
大多数问题两者 rank 相同
收益集中在少数 harder factual
```

### 回退

```text
comparison -0.029
```

但只有 5 条，噪声大。

## 4. 回退案例归因

| case | SQLite | PG+rerank | gold 在 PG top50 | 归因 |
|---|---:|---:|---|---|
| q006 | 1.000 | 0.431 | 否 | 候选漏 |
| q008 | 0.631 | 0.387 | 否 | 候选漏 |
| q014 | 0.631 | 0.387 | 是（rank 33） | rerank 降权 |
| q020 | 0.289 | 0.000 | 否 | 候选漏 |
| q028 | 0.631 | 0.387 | 是（rank 10） | rerank 降权 |
| q059 | 0.315 | 0.000 | 否 | 候选漏 |
| q060 | 0.356 | 0.000 | 否 | 候选漏 |
| q063 | 0.356 | 0.000 | 否 | 候选漏 |
| q070 | 1.000 | 0.000 | 是（rank 41） | rerank 降权 |
| q083 | 0.333 | 0.000 | 是（rank 24） | rerank 降权 |

结论：

```text
一半回退是 PG 候选没召回
一半是 reranker 把正确段落压下去
```

## 5. 下一步

```text
1. candidates 50 -> 100，优先修候选漏
2. 对 comparison 单独看 query 形态
3. rerank 前先按 PG rank 截断/融合，避免把 rank 41 的正确项压掉
4. 按 factual / auto 分层决定是否先切
```

## 6. 建议

```text
可以先在 factual 通道做小流量
不要全量切
comparison 先保持 SQLite
```

当前生产仍走 SQLite FTS。
