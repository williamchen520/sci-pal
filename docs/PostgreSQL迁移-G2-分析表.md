# G2 分析表：0.95 → 0.65/0.75 的损耗分解

> 日期：2026-11-04  
> 目标：把“召回地基”和“evidence 交付”拆开，不留未确认项

---

## 1. 四层指标

| 层级 | 指标 | 当前值 | 说明 |
|---|---|---:|---|
| L1 | raw paragraph recall@10 | **0.9500** | pgvector/检索硬实力 |
| L2 | evidence paragraph recall@10 | **0.9500** | 组装不丢 paragraph |
| L3 | evidence sentence recall@10 | **0.7500** | highlight/引用准确率 |
| L4 | evidence nDCG@10 | **0.4571** | 交付排序质量 |

raw nDCG：

```text
0.6965
```

对照：

```text
L1 .95 -> L2 .95   无损耗
L2 .95 -> L3 .75   20 点损耗
L4 .4571 vs raw .6965  排序大幅下降
```

---

## 2. 五层检查结果

| 检查 | 结果 | 结论 |
|---|---|---|
| ef_search | 已设置 200，并 ALTER DATABASE 持久化 | 排除 |
| GPU reranker | cuda，显存 3.3GB，日志 rerank top 40 | 排除 |
| 流水线顺序 | rerank 在 MMR 之前 | 确认 |
| RRF 权重 | dynamic/equal 均未提升 | 排除 |
| 候选池 | candidate 50，rerank 40，无 Top-5 截断 | 排除 |
| entity boost | boost 与 append 96 题持平 | 排除 |
| MMR | 离线加 MMR 反而 .7708 | 排除 |
| parent-context | evidence paragraph 仍 .95 | 排除 |
| sentence highlight | **.75，4 题 para 在但 sentence 不在** | **主因** |

---

## 3. 20 题逐题定位

```text
para_cov  .95
sent_cov  .75
```

PARA_ONLY：

```text
q002  gold para 0008 在 evidence，gold sent 004 未 highlight
q016  gold para 0000 在 evidence，gold sent 002 未 highlight
q017  gold para 0000 在 evidence，gold sent 002 未 highlight
q018  gold para 0000 在 evidence，gold sent 003 未 highlight
```

结论：

```text
4/20 不是召回失败
是 highlight sentence 选择失败
```

---

## 4. 损耗归因

### 4.1 不是 pgvector

```text
vector top50 已 trace 确认
raw paragraph .95
```

### 4.2 不是 entity / MMR / RRF

```text
boost/append 96 持平
MMR 离线提升
dynamic/equal 无差异
```

### 4.3 是 evidence 组装层

```text
paragraph 保留 .95
sentence highlight 掉到 .75
nDCG 掉到 .457
```

---

## 5. 0.65/0.75 是否可接受

### 可以接受

```text
产品按 paragraph/evidence 引用
sentence 只是辅助定位
0.75 作为当前 sentence 基线
```

### 不可以接受

```text
产品要求精确 sentence 引用
4 题 gold sentence 明明在 evidence 里却没 highlight
```

这不是“上下文稀释”，是：

```text
highlight 选择 bug
或评测 sentence 映射 bug
```

---

## 6. 新 SLO 建议

| 指标 | 当前 | 目标 |
|---|---:|---:|
| raw paragraph recall | .95 | ≥.95 |
| evidence paragraph recall | .95 | ≥.95 |
| evidence sentence recall | .75 | ≥.85 |
| evidence nDCG | .457 | ≥.55 |

原则：

```text
0.95 是召回底线
0.95 是组装底线
0.75 是引用基线，不是健康终点
0.457 是排序基线，必须优化
```

---

## 7. 修复顺序

```text
1. 修 highlight sentence 选择（q002/q016/q017/q018）
2. 修 evidence 顺序，保留 raw rerank 顺序
3. 复跑 20
4. 复跑 96
5. 再决定 pgvector 切流
6. 最后 G4
```

---

## 8. 当前生产

```text
FTS       100% ParadeDB
Vector    Chroma
Boost     post-fusion
app       healthy
```

G4 继续阻塞。
