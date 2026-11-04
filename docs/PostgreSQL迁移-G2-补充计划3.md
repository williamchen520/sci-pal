# G2 补充计划表 3：Anchor Ranking + Context Window 分离

> 日期：2026-11-04  
> 目标：让 window 不参与排序，只做上下文；anchor 参与排序和主引用

---

## 1. 核心原则

```text
Ranking Set   = paragraph + anchor
Context Set   = anchor ± window
Citation Set  = anchor only
```

禁止：

```text
window 进入 highlight
window 改变 evidence 顺序
window 改变 MMR/reRank 结果
```

---

## 2. 组合架构

```text
paper
  -> section
    -> paragraph candidates
      -> one anchor per paragraph
        -> anchor ± window (context only)
          -> evidence cards
```

---

## 3. Evidence 结构

```json
{
  "evidence_id": "P1",
  "paper_id": "...",
  "section_path": ["Introduction"],
  "para_id": "...",
  "para_score": 0.82,
  "anchor": {
    "sentence_id": "...",
    "text": "...",
    "anchor_score": 0.91
  },
  "window": [
    {"sentence_id": "...", "text": "...", "role": "context"}
  ],
  "highlight": ["anchor_sentence_id"],
  "context_only": ["window_sentence_ids"]
}
```

排序只看：

```text
para_score
anchor_score
```

不看：

```text
window 数量
window 长度
```

---

## 4. 任务表

| ID | 任务 | 产出 | 验收 |
|---|---|---|---|
| G2.7a | anchor / context 字段分离 | evidence schema | highlight 只含 anchor |
| G2.7b | one anchor per paragraph | 每段 1 主句 | 高亮不膨胀 |
| G2.7c | evidence 顺序 = paragraph score | 排序稳定 | nDCG 不降 |
| G2.7d | context window 独立 | window 不参与排序 | 20 题 nDCG 保持 |
| G2.7e | anchor_hit / context_hit | 两套指标 | 可区分 |
| G2.7f | 20 题验收 | 指标表 | 不低于 .6875/.5116 |
| G2.7g | 96 题验收 | 指标表 | 不低于基线 |

---

## 5. 评估指标

| 指标 | 含义 | 当前 | 目标 |
|---|---|---:|---:|
| raw paragraph recall | 检索硬实力 | .95 | ≥.95 |
| evidence paragraph recall | 组装 | .95 | ≥.95 |
| anchor_hit | 主引用命中 | .75 | ≥.85 |
| context_hit | window 命中 | 未测 | ≥.95 |
| evidence nDCG | 排序 | .457 | ≥.55 |
| citation_hit | 最终引用 | 未测 | ≥.90 |

---

## 6. 验收门槛

```text
G2.7f 20 题：
  recall >= .70
  nDCG   >= .496
  anchor_hit >= .75

G2.7g 96 题：
  recall >= .6875
  nDCG   >= .5116
```

不达标：

```text
保持 Chroma
G4 继续阻塞
```

---

## 7. 实施步骤

```text
Day 1  G2.7a + G2.7b
Day 2  G2.7c + G2.7d
Day 3  G2.7e
Day 4  G2.7f
Day 5  G2.7g
```

---

## 8. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| anchor 选错 | anchor_hit 低 | context window 兜底 |
| window 太大 | token/注意力 | 每段最多 3 句 |
| evidence 顺序变 | nDCG 降 | 只按 para_score |
| 评测混用 | 误判 | anchor/context 分开算 |

---

## 8b. 首次验证（2026-11-04）

配置：

```text
SCIPAL_CONTEXT_WINDOW=2
SCIPAL_CONTEXT_LIMIT=8
highlight 只含 matched sentences
```

20 题：

```text
recall .75 / nDCG .4961
与基线一致
```

96 题：

```text
recall .6875 / nDCG .5130
与基线一致
```

样本：

| 题 | anchor | context |
|---|---|---|
| q002 | ❌ | ✅ |
| q016 | ❌ | ✅ |
| q017 | ❌ | ✅ |
| q018 | ❌ | ✅ |

结论：

```text
context window 不再污染排序
但当前 anchor 仍不是 gold
```

context_only：

```text
17–30 条/20 题
```

## 9. 当前生产

```text
FTS       100% ParadeDB
Vector    Chroma
Anchor    关闭
app       healthy
G4        阻塞
```
