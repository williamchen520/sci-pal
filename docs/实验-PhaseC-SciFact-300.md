# 实验 Phase C：SciFact F0 / B / C / S / C2

> 日期：2026-11-12  
> 状态：**Gate 2 未通过，暂停 A/D/E/GA**  
> 代码：`eval/scifact_phase_c.py`、`eval/scifact_units.py`、`eval/scifact_phase_c_stats.py`

---

## 1. 数据与 Gate 1

```text
papers       5,183
sentences   45,051
claims        505
```

前 300 claims：

```text
evidence 100% 映射到 sentence_id
Gate 1 通过
```

全量 505 审计：

```text
1,025 个 evidence
1,021 精确命中
4 条 claim 有缺失（624 / 751 / 815 / 816）
```

缺失来自 DB 句界与原始 SciFact gold 的最后一帧差异。  
全量实验采用严格映射：**只保留 evidence 全部可映射的 501 条**，不伪造缺失句。

---

## 2. 实验臂

| 臂 | 检索单元 | 上下文 | 说明 |
|---|---|---|---|
| F0 | 硬切 chunk | 无 | 500 / 200 / 120 词硬切 |
| B | 硬切 chunk | ±1 句 | context 不参与排序 |
| C | 句界 chunk | ±1 句 | 500 / 200 / 120 词，尽量不切句 |
| S | 单句 | ±1 句 | 纯句诊断 |
| C2 | 句子打分 → 父 chunk 聚合 | 父 chunk | 句子向量取 max，按父 chunk 排序 |
| F0+R / B+R / C+R | 同 F0/B/C | — | 小池 cross-encoder rerank，top20 |

模型：

```text
embedding  BAAI/bge-base-en-v1.5，768 维
reranker   BAAI/bge-reranker-base
query prefix: "Represent this sentence for searching relevant passages: "
```

评分：

```text
anchor sentence 命中才计主指标
context 只报 context_recall
```

---

## 3. 500 词：过粗

300 claims：

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.873 |
| B | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.873 |
| C | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.874 |

SciFact abstract 大多不足 500 词，三臂退化成“每篇一个 chunk”。  
**500 词不能用于比较 chunk 策略。**

---

## 4. 120 词 / 200 词

### 120 词，300 claims

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 11,475 | 0.600 | 0.893 | 0.950 | 0.914 | 0.914 | 0.737 |
| B | 11,475 | 0.600 | 0.893 | 0.950 | 0.914 | **0.955** | 0.737 |
| C | 11,933 | 0.573 | 0.893 | 0.943 | 0.896 | 0.934 | 0.720 |
| S | 45,051 | 0.450 | 0.773 | 0.833 | 0.698 | 0.810 | 0.584 |

### 200 词，300 claims

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 7,602 | 0.690 | 0.947 | 0.980 | 0.966 | 0.966 | 0.804 |
| B | 7,602 | 0.690 | 0.947 | 0.980 | 0.966 | **0.973** | 0.804 |
| C | 7,654 | 0.647 | 0.937 | 0.970 | 0.952 | 0.957 | 0.773 |

结论：

```text
200 词整体优于 120 词
B 仍然只提升 context
C 仍然低于 F0
```

---

## 5. 全量 501 claims（120 词）

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 11,475 | 0.605 | 0.904 | 0.948 | 0.916 | 0.916 | 0.741 |
| B | 11,475 | 0.605 | 0.904 | 0.948 | 0.916 | **0.946** | 0.741 |
| C | 11,933 | 0.579 | 0.900 | 0.942 | 0.899 | 0.931 | 0.725 |
| S | 45,051 | 0.453 | 0.784 | 0.838 | 0.703 | 0.819 | 0.588 |
| C2 | 11,933 | 0.585 | 0.876 | 0.916 | 0.854 | 0.890 | 0.709 |

### Paired bootstrap（Hit@10，5000 次，F0 基线）

| 对比 | 差值 | 95% CI | 单侧 p |
|---|---:|---|---:|
| B - F0 | 0.000 | [0.000, 0.000] | 1.000 |
| C - F0 | -0.006 | [-0.022, 0.010] | 0.814 |
| S - F0 | -0.110 | [-0.142, -0.082] | 1.000 |
| C2 - F0 | -0.032 | [-0.054, -0.012] | 0.999 |

结论：

```text
B 与 F0 的 Hit@10 完全相同
C 略低，CI 跨 0，但没有正收益
S / C2 显著更差
```

---

## 6. C2：句子锚点 + 父 chunk

设计：

```text
句子向量打分
  -> 同一父 chunk 内取 max
  -> 按父 chunk 排序
  -> 用父 chunk 的句子作为 anchors
```

结果：

```text
C2 Hit@10 0.916 < C 0.942 < F0 0.948
```

原因：

```text
max 聚合丢掉了 chunk 内其他句子的证据
父 chunk 变长后，排序被单个高分句主导
“句子锚点 + 父 chunk”没有解决首跳
```

---

## 7. 小池 rerank

300 claims，120 词，top20 cross-encoder：

| 臂 | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|
| F0+R | 0.573 | 0.887 | 0.947 | 0.919 | 0.919 | 0.701 |
| B+R | 0.573 | 0.887 | 0.947 | 0.919 | 0.950 | 0.701 |
| C+R | 0.540 | 0.873 | 0.950 | 0.892 | 0.927 | 0.680 |

Rerank 没有救回首跳：

```text
F0 无 rerank Hit@1 0.600
F0 + rerank Hit@1 0.573
```

说明主要问题不是“候选池排序不够好”，而是 **chunk 表示本身**。

---

## 8. 发现

### 8.1 B 的收益只在上下文

B 与 F0 的 anchor 指标完全一致，这是设计使然：

```text
context 不参与排序
B 只给命中 chunk 加 ±1 句
```

Context recall：

```text
120 词：0.914 -> 0.955
200 词：0.966 -> 0.973
全量：  0.916 -> 0.946
```

如果目标是“给生成器更完整的上下文”，B 有价值；如果目标是“把 gold sentence 排得更前”，B 不够。

### 8.2 C 的句界 chunk 没有优势

120 / 200 / 500 三档都低于 F0：

```text
C 不是“更自然的 chunk”就一定更好
句界 chunk 合并了更多句子，语义被稀释
```

### 8.3 纯句检索明显差

```text
S Hit@10 0.838
S Sentence Recall@10 0.703
```

SciFact claim 经常需要跨句证据。  
“句子作为证据单位”成立，但“句子作为唯一检索单元”不成立。

### 8.4 C2 的聚合方式不对

句子 max 聚合丢证据。  
如果继续做 C2，应该：

```text
sum top-k 句分 / 学习聚合
不是单句 max
```

但这是新方法，不应在 Gate 2 未过时直接堆。

### 8.5 Rerank 不是当前瓶颈

小池 cross-encoder 没有提升首跳，反而略降。  
说明候选表示/切分比 rerank 更关键。

---

## 9. Gate 2

计划要求：

```text
B/C 至少一个显著优于 F0
否则检查 chunk/窗口实现，不继续加方法
```

结果：

```text
B：anchor 与 F0 完全相同，只有 context 提升
C：低于 F0，CI 跨 0
S/C2：显著更差
Rerank：没有救回首跳
```

结论：

```text
Gate 2 未通过
暂停 A / D / E / GA
不把 AutoMerging / GA 叠在没有首跳收益的 chunk 上
```

---

## 10. 下一步

```text
1. 停掉 chunk 参数微调，避免过拟合 300/501
2. 重新定义 C：不是“句界大 chunk”，而是“句子锚点 + 多句证据聚合”
3. 若继续 C2：用 sum/top-k 聚合，不用单句 max
4. 先做 dev/test 按 claim 的 paired 比较，再决定是否加 rerank
5. 不再加 A/D/E/GA，除非 Gate 2 先过
```

当前判断：

```text
F0 仍是可靠基线
B 适合做“证据上下文”，不适合做“首跳召回”
C/S/C2/rerank 都没有证明优于 F0
```

---

## 11. 复现

```bash
# 300 claims, 120 words, sentence arm + C2
python -m eval.scifact_phase_c \
  --limit 300 --chunk-words 120 --include-sentence \
  --output eval/results/scifact_phase_c_300_120_S.json

# 全量严格映射（501）
python -m eval.scifact_phase_c \
  --limit 0 --chunk-words 120 --include-sentence \
  --output eval/results/scifact_phase_c_501_120_strict.json

# paired bootstrap
python -m eval.scifact_phase_c_stats \
  --input eval/results/scifact_phase_c_501_120_strict.json
```

结果：

```text
eval/results/scifact_phase_c_20.json
eval/results/scifact_phase_c_20_120.json
eval/results/scifact_phase_c_300_500.json
eval/results/scifact_phase_c_300_120.json
eval/results/scifact_phase_c_300_200.json
eval/results/scifact_phase_c_300_120_S.json
eval/results/scifact_phase_c_300_120_rerank.json
eval/results/scifact_phase_c_501_120_strict.json
```

---

## 12. 结论

```text
500 词：文档级，无法比较 chunk 策略
120/200 词：B 补上下文，C 不优于 F0
全量 501：B 与 F0 首跳相同，C/S/C2 更差
Rerank：没有救回首跳
Gate 2：未通过
```

下一步不是继续调 chunk 参数，而是重新定义“句子锚点 + 证据聚合”，或接受 F0 作为检索基线、把 B 只用于生成上下文。
