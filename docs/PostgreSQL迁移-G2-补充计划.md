# G2 补充工作计划：Entity Boost 与融合稳定性

> 日期：2026-11-04  
> 目标：修复“单通道差 1%，生产差 6%”的融合放大问题  
> 原则：不删除 Chroma，直到生产 96 题达标

---

## 1. 问题定义

```text
离线 BM25 + pgvector + rerank : .7604 / .6134
生产 BM25 + pgvector + rerank : .6250 / .4960
```

已排除：

```text
GPU reranker 未生效
候选池被截到 Top-5
多 query variants（生产不走）
```

主要嫌疑：

```text
entity boost 在 RRF 后 append
rerank 窗口被额外 lane 挤占
MMR 在 rerank 后做二次截断
```

---

## 2. 任务表

| ID | 任务 | 产出 | 验收 |
|---|---|---|---|
| G2.5a | entity boost 去重按 para_id | 已修 | 20 题 .65 -> .75 |
| G2.5b | entity 改为 post-fusion score boost | 不扩候选池 | 候选数不变 |
| G2.5c | 固定 rerank 窗口 40 | 不被 entity 挤占 | rerank 输入稳定 |
| G2.5d | A/B：append / boost / off | 20 题对比 | boost 最优 |
| G2.5e | 96 题确认 | recall/nDCG | ≥ Chroma .6875 / .5116 |
| G2.5f | 决定是否切 pgvector | 切流或回滚 | 记录 |
| G2.5g | 通过后 G4a 删 paragraph Chroma | 单轨段落 | 无 import |

---

## 3. 实现方案

### 3.1 Entity Boost 模式

```text
SCIPAL_ENTITY_BOOST_MODE=append  旧行为，保留对照
SCIPAL_ENTITY_BOOST_MODE=boost   只给已存在候选加权
SCIPAL_ENTITY_BOOST_MODE=off     关闭
```

boost 公式：

```text
rrf_score += weight / (60 + entity_rank)
```

默认：

```text
weight = 0.05
```

### 3.2 不扩候选池

```text
entity hit 不在 fused 中 -> 丢弃
不再 append
```

### 3.3 固定 rerank 窗口

```text
candidate_k = 50
rerank_k = 40
entity 不改变两者
```

---

## 4. A/B 设计

| 组 | 模式 | 候选数 | 预期 |
|---|---|---:|---|
| A | append | 50 + 30 | 现状 |
| B | boost | 50 | 推荐 |
| C | off | 50 | 下限 |
| D | boost + MMR off | 50 | 对照 |

先 20 题，B 组优于 A 再跑 96。

---

## 5. 验收门槛

```text
20 题 recall >= .70
96 题 recall >= .6875
96 题 nDCG >= .5116
```

不达标：

```text
保持 Chroma
G4 继续阻塞
```

---

## 6. 风险

```text
boost 权重过大 -> 关键词候选压过语义
entity 命中不在 RRF 50 内 -> 无收益
MMR 仍可能二次丢召回
```

---

## 6b. 实施结果

```text
SCIPAL_ENTITY_BOOST_MODE=boost
SCIPAL_ENTITY_BOOST_WEIGHT=0.05
```

20 题：

| 模式 | recall | nDCG |
|---|---:|---:|
| append（修复去重） | .75 | .4961 |
| boost | .75 | .4961 |
| off | 未跑 | — |

结论：

```text
20 题上 boost 与 append 等价
还需 96 题确认，暂不切 pgvector
```

## 7. 当前生产

```text
FTS       ParadeDB 100%
Vector    Chroma
Reranker  GPU
G4        阻塞
```
