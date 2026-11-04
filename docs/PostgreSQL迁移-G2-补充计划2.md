# G2 补充计划工作表：Anchor Evidence 与四层评估

> 日期：2026-11-04  
> 前置：G2 调查表 2、G2 分析表  
> 目标：把 evidence 从“parent context 堆叠”改成“anchor sentence + parent support”

---

## 1. 目标

```text
L1 raw paragraph recall        >= .95
L2 evidence paragraph recall   >= .95
L3 evidence sentence recall    >= .85
L4 evidence nDCG               >= .55
请求 P95                       <= 4s
```

当前：

```text
L1 .95
L2 .95
L3 .75
L4 .457
```

---

## 2. 任务总表

| ID | 任务 | 产出 | 验收 | 预估 |
|---|---|---|---|---|
| G2.6 | Anchor sentence 选择 | 每个 evidence 1–2 anchor | q002/q016/q017/q018 命中 | 1 天 |
| G2.7 | Evidence ordering | 按 anchor rerank 排序 | nDCG 提升 | 0.5 天 |
| G2.8 | Submodular evidence packing | 3–5 anchor + parent | 无 30+ highlight | 1 天 |
| G2.9 | Four-layer evaluation | 四层指标脚本 | 20/96 可复跑 | 0.5 天 |
| G2.10 | Highlight contract | anchor 只能来自候选 | 无全库补句 | 0.5 天 |
| G2.11 | 20 题验收 | 指标表 | L3≥.85/L4≥.55 | 0.5 天 |
| G2.12 | 96 题验收 | 指标表 | 不低于基线 | 0.5 天 |
| G2.13 | pgvector 决策 | 切流或保持 | 记录 | 0.5 天 |
| G2.14 | G4a | 删 paragraph Chroma | 仅通过后 | 1 天 |

总预估：**5–6 天**

---

## 3. G2.6 Anchor Sentence

### 输入

```text
evidence 的 paragraph_details
rerank 后的 paragraph 顺序
query
```

### 约束

```text
只从当前 evidence 的 paragraph 内选
不从全库 sentences_fts 补
每段最多 1–2 句
```

### 打分

```text
score = query-sentence 词面重合
      + 位置先验（段首/段中）
      + rerank paragraph 先验
```

### 输出

```json
{
  "sentence_id": "...",
  "para_id": "...",
  "text": "...",
  "anchor_score": 0.82
}
```

### 验收

```text
q002/q016/q017/q018 的 gold sentence 进入 highlight
highlight 数不超过 2/evidence
```

---

## 4. G2.7 Evidence Ordering

### 问题

```text
raw nDCG .6965 -> evidence nDCG .4571
```

### 规则

```text
evidence 按 anchor rerank_score 排序
不按 paper/section 重新分组
parent context 不改变主排序
```

### 验收

```text
20 题 evidence nDCG >= .55
```

---

## 5. G2.8 Submodular Evidence Packing

### 预算

```text
3–5 个 anchor
每个 anchor 最多 1 个 parent section
总 token <= 6000
```

### 目标函数

```text
relevance(anchor)
+ coverage(paper/section)
- redundancy(parent context)
- token cost
```

### 验收

```text
highlight/evidence 数稳定
不再出现 30+ 高亮
```

---

## 6. G2.9 Four-layer Evaluation

脚本输出：

```text
L1 raw paragraph recall
L2 evidence paragraph recall
L3 evidence sentence recall
L4 evidence nDCG
```

并逐题记录：

```text
gold paragraph 是否在 evidence
gold sentence 是否在 evidence.text
gold sentence 是否在 highlight
gold 在 evidence 中位置
```

---

## 7. G2.10 Highlight Contract

```text
highlight 只能来自 evidence 候选段落
禁止全局 sentence FTS 补句
禁止把 parent context 里任意句当 highlight
```

---

## 8. 测试矩阵

| 测试 | 数据 | 验收 |
|---|---|---|
| q002/q016/q017/q018 | 单题 | sentence 命中 |
| 20 题 | regression_20 | L3≥.85, L4≥.55 |
| 96 题 | seed_100 | 不低于 Chroma 基线 |
| 延迟 | 20 题 | P95≤4s |
| 回归 | 全量 unittest | 全绿 |

---

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| anchor 选错 | 引用错误 | 只从候选段选，保留 score |
| parent context 太长 | 延迟/稀释 | token budget + submodular |
| submodular 降 recall | L2 下降 | 保留 L1/L2 硬约束 |
| 评测口径再次漂移 | 误判 | 四层指标固定 |

---

## 10. 回退

```text
SCIPAL_EVIDENCE_MODE=legacy
SCIPAL_ANCHOR_SENTENCES=0
SCIPAL_EVIDENCE_PACKING=off
```

任一阶段不达标：

```text
保持 Chroma
G4 继续阻塞
```

---

## 11. 执行顺序

```text
Day 1  G2.6 + G2.10
Day 2  G2.7 + G2.9
Day 3  G2.8
Day 4  G2.11 20 题
Day 5  G2.12 96 题
Day 6  G2.13 决策 + G2.14
```

---

## 11b. G2.6 试验结果

```text
lexical anchor:
  q002 未命中，highlight 膨胀

cross-encoder anchor:
  q002 命中
  q016/q017/q018 未命中
  高亮 12–20 条
  延迟 4.5–10s
```

处理：

```text
默认关闭
SCIPAL_ANCHOR_SENTENCES=0
SCIPAL_ANCHOR_RERANK=0
```

结论：

```text
anchor 方向正确
但仅对 q002 有效
需要更强的 sentence matching / 训练/规则
```

## 12. 当前生产

```text
FTS       100% ParadeDB
Vector    Chroma
Boost     post-fusion
app       healthy
```

G4 继续阻塞。
