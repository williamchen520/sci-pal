# 实验 Phase C：SciFact F0 / B / C 烟测

> 日期：2026-11-12  
> 状态：**Gate 2 未通过，暂停 A/D/E/GA**  
> 范围：SciFact abstracts，sentence-level evidence retrieval  
> 代码：`eval/scifact_phase_c.py`

---

## 1. 数据与 Gate 1

```text
papers       5,183
sentences   45,051
claims        505
使用 claims   300（gold 文件前 300 条）
```

Gate 1：

```text
前 300 条 claims 的 evidence 100% 落到 sentence_id
```

全量 505 条审计：

```text
1,025 个 evidence
1,021 个精确命中
4 个缺失（0.4%）
```

缺失原因是 DB 的句子切分与原 SciFact gold 的句界不完全一致，集中在 4 条 claim 的最后一帧。  
Phase C 使用的 300 条不包含这 4 条，因此本轮 Gate 1 通过；**全量 505 复现前必须修句界映射**。

---

## 2. 实验臂

| 臂 | 检索单元 | 上下文 | 说明 |
|---|---|---|---|
| F0 | 硬切 chunk | 无 | 500/120 词硬切 |
| B | 硬切 chunk | ±1 句 | 只扩展上下文，上下文不计分 |
| C | 句界 chunk | ±1 句 | 500/120 词，尽量不切断句子 |
| S | 单句 | ±1 句 | 诊断臂，检验纯句检索 |

评分口径：

```text
anchor sentence 命中才计分
context sentence 只报 context_recall，不计入主指标
```

模型：

```text
BAAI/bge-base-en-v1.5
768 维
query prefix: "Represent this sentence for searching relevant passages: "
```

---

## 3. 500 词：过粗，三臂退化

300 claims：

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.873 |
| B | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.873 |
| C | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.874 |

结论：

```text
SciFact abstract 大多不足 500 词
F0 / B / C 基本退化成“每篇一个 chunk”
500 词不能用来比较 chunk 策略
```

20 条烟测同样是三臂完全一致：

```text
Hit@1 0.75 / Hit@5 0.95 / Hit@10 1.00
```

---

## 4. 120 词：B 只提升上下文，C 下降

300 claims：

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 11,475 | 0.600 | 0.893 | 0.950 | 0.914 | 0.914 | 0.737 |
| B | 11,475 | 0.600 | 0.893 | 0.950 | 0.914 | **0.955** | 0.737 |
| C | 11,933 | 0.573 | 0.893 | 0.943 | 0.896 | 0.934 | 0.720 |
| S | 45,051 | 0.450 | 0.773 | 0.833 | 0.698 | 0.810 | 0.584 |

20 条烟测：

| 臂 | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|
| F0 | 0.500 | 0.850 | 0.950 | 0.887 | 0.887 | 0.677 |
| B | 0.500 | 0.850 | 0.950 | 0.887 | **0.912** | 0.677 |
| C | 0.400 | 0.850 | 0.900 | 0.863 | 0.875 | 0.615 |

---

## 5. 发现

### 5.1 500 词不适合 SciFact

SciFact abstract 太短，500 词 chunk 等于文档级检索。  
这解释了为什么三臂完全相同，也说明**不能拿 500 词结果证明 chunk 策略优劣**。

### 5.2 B 的收益只在上下文

B 与 F0 的 anchor 指标完全一致，这是设计使然：

```text
context 不参与排序
B 只是给命中 chunk 增加 ±1 句
```

B 的 context recall：

```text
0.914 -> 0.955（+4.1 个百分点）
```

这说明窗口确实补到了证据句，但**没有提升首跳召回**。  
如果目标是“给生成器更完整的上下文”，B 有价值；如果目标是“把 gold sentence 排得更前”，B 不够。

### 5.3 C 没有优于 F0

120 词句界 chunk：

```text
C Hit@1      0.573 < F0 0.600
C Recall@10  0.896 < F0 0.914
C MRR@10     0.720 < F0 0.737
```

句界 chunk 没有自动带来收益，反而因为 chunk 内句子更多、语义被稀释，首跳更差。

### 5.4 纯句检索明显更差

S：

```text
Hit@1 0.450
Sentence Recall@10 0.698
```

SciFact claim 往往需要跨句证据；单句太细，缺少上下文。  
这支持“chunk 作为检索单元，句子作为证据单位”的方向，但不支持“纯句索引”。

### 5.5 实现正确性信号

B 的 anchor 指标与 F0 完全一致、context 指标上升，说明：

```text
anchor / context 分离正确
context 没有被误计入主指标
```

---

## 6. Gate 2

计划要求：

```text
B/C 至少一个显著优于 F0
否则检查 chunk/窗口实现，不继续加方法
```

当前：

```text
B：anchor 不优于 F0，只有 context 提升
C：anchor 低于 F0
S：明显低于 F0
```

结论：

```text
Gate 2 未通过
暂停 A / D / E / GA
不把 AutoMerging 或 GA 叠在一个没有首跳收益的 chunk 上
```

---

## 7. 下一步

按“先修实现，再堆方法”的顺序：

```text
1. 修全量 505 的 4 个句界缺失
2. 补 200 词档（本轮 200 词运行超时，未纳入）
3. 把 C 改成“句子锚点 + 父 chunk”而不是整块句界 chunk
4. 加 rerank 小池，看首跳是否恢复
5. 全量 505 + paired bootstrap
6. Gate 2 重跑；仍不过就停在 F0/B
```

不建议现在做：

```text
A 父文档
D AutoMerging
E 叠加
GA 调参
```

---

## 8. 复现

```bash
python -m eval.scifact_phase_c \
  --limit 300 \
  --chunk-words 120 \
  --include-sentence \
  --output eval/results/scifact_phase_c_300_120_S.json
```

模型：

```text
G:/models/bge-base-en-v1.5
```

结果：

```text
eval/results/scifact_phase_c_20.json
eval/results/scifact_phase_c_20_120.json
eval/results/scifact_phase_c_300_500.json
eval/results/scifact_phase_c_300_120.json
eval/results/scifact_phase_c_300_120_S.json
```

---

## 9. 结论

```text
500 词：文档级，无法比较 chunk 策略
120 词：B 补上下文，C 不优于 F0，S 明显差
Gate 2：未通过
决策：不进入 A/D/E/GA，先修句界与 C 的实现
```
