# 实验报告：Phase C — SciFact 句级检索与 chunk 策略

> 日期：2026-11-12  
> 数据集：SciFact abstracts  
> 任务：claim → sentence evidence retrieval  
> 状态：**Gate 2 未通过；F0/Dense 作为检索基线，B 只作为上下文层**

---

## 摘要

本实验在 SciFact abstracts 上比较了六类检索单元/上下文策略：

```text
F0  硬切 chunk，无上下文
B   硬切 chunk + ±1 句窗
C   500/200/120 词句界 chunk + ±1 句窗
S   单句 + ±1 句窗
C2  句子打分 → 父 chunk 内 max 聚合
C3  句子打分 → 父 chunk 内 top-k 求和
```

并补充了：

```text
小池 cross-encoder rerank
BM25 / Dense / Hybrid RRF 系统级 baseline
```

核心结论：

```text
500 词 chunk 对 SciFact 摘要过粗，三臂退化
120/200 词下，B 只提升 context recall，不提升首跳
C 的句界 chunk 不优于 F0
S 纯句检索显著更差
C2/C3 的聚合没有救回首跳
Rerank 没有提升
BM25 弱于 Dense；等权 Hybrid RRF 也低于 Dense
Gate 2 未通过
```

因此：

```text
F0/Dense 保留为检索基线
B 只作为生成上下文
暂停 A/D/E/GA
不再调 chunk 参数
```

---

## 1. 研究问题

### RQ1

在 SciFact 摘要上，句级证据检索应该用什么单元？

```text
固定 chunk
句子窗口
句界 chunk
单句
句子→父 chunk 聚合
```

### RQ2

句子窗口是否提升证据召回，还是只提升上下文完整性？

### RQ3

句界对齐是否比硬切更优？

### RQ4

小池 rerank、BM25、Hybrid RRF 是否能弥补首跳召回？

---

## 2. 数据

### 2.1 来源

```text
SciFact abstracts
papers       5,183
sentences   45,051
claims        505
```

存储：

```text
data/benchmark_scifact.db
eval/gold/scifact_300.jsonl
```

### 2.2 Gold 映射与 Gate 1

前 300 claims：

```text
evidence 100% 映射到 sentence_id
Gate 1 通过
```

全量 505 审计：

```text
evidence          1,025
精确命中          1,021
缺失              4（0.4%）
```

缺失 claim：

```text
624
751
815
816
```

原因：

```text
DB 的句子切分与原 SciFact gold 的最后一帧不一致
```

处理：

```text
不伪造、不强行映射
全量实验只保留 evidence 全部可映射的 501 条
```

### 2.3 重要限制

```text
300 条是 gold 文件前 300 条，不是独立 dev/test split
本轮没有按 claim 做训练/验证隔离
```

因此结果应视为**方法烟测/方向判断**，不是最终论文级评测。

---

## 3. 方法

### 3.1 实验臂

| 臂 | 检索单元 | 上下文 | 说明 |
|---|---|---|---|
| F0 | 硬切 chunk | 无 | 按词数硬切 |
| B | 硬切 chunk | ±1 句 | context 不参与排序 |
| C | 句界 chunk | ±1 句 | 尽量在句子边界切 |
| S | 单句 | ±1 句 | 纯句诊断 |
| C2 | 句子打分 → 父 chunk max | 父 chunk | 句子向量取 max |
| C3 | 句子打分 → 父 chunk top-k sum | 父 chunk | top-2 / top-3 |
| F0+R / B+R / C+R | 同 F0/B/C | — | top20 cross-encoder rerank |

### 3.2 模型

```text
embedding   BAAI/bge-base-en-v1.5
维度        768
query prefix "Represent this sentence for searching relevant passages: "
reranker    BAAI/bge-reranker-base
```

### 3.3 切分

硬切：

```text
按空白词计数
500 / 200 / 120 词
可能切断句子
```

句界：

```text
按句子累积到接近目标词数
不切断句子
```

### 3.4 评分口径

```text
unit 的 anchor sentence 命中才计主指标
context sentence 只报 context_recall
context 不计入 Recall / MRR / nDCG
```

指标：

```text
Hit@1 / Hit@5 / Hit@10
Sentence Recall@10
Context Recall@10
MRR@10
nDCG@10
```

### 3.5 统计

```text
paired bootstrap
按 claim 重采样
5000 次
95% percentile CI
单侧 p = 重采样差值 <= 0 的比例
```

---

## 4. 结果

### 4.1 500 词：过粗

300 claims：

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.873 |
| B | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.873 |
| C | 5,226 | 0.807 | 0.963 | 0.977 | 0.974 | 0.974 | 0.874 |

解释：

```text
SciFact abstract 大多不足 500 词
F0/B/C 基本退化成“每篇一个 chunk”
500 词不能比较 chunk 策略
```

### 4.2 120 词

300 claims：

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 11,475 | 0.600 | 0.893 | 0.950 | 0.914 | 0.914 | 0.737 |
| B | 11,475 | 0.600 | 0.893 | 0.950 | 0.914 | **0.955** | 0.737 |
| C | 11,933 | 0.573 | 0.893 | 0.943 | 0.896 | 0.934 | 0.720 |
| S | 45,051 | 0.450 | 0.773 | 0.833 | 0.698 | 0.810 | 0.584 |

### 4.3 200 词

300 claims：

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 7,602 | 0.690 | 0.947 | 0.980 | 0.966 | 0.966 | 0.804 |
| B | 7,602 | 0.690 | 0.947 | 0.980 | 0.966 | **0.973** | 0.804 |
| C | 7,654 | 0.647 | 0.937 | 0.970 | 0.952 | 0.957 | 0.773 |

200 词整体优于 120 词，但 B/C 的相对结论不变：

```text
B 只提升 context
C 低于 F0
```

### 4.4 全量 501 claims（120 词）

| 臂 | units | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 11,475 | 0.605 | 0.904 | 0.948 | 0.916 | 0.916 | 0.741 |
| B | 11,475 | 0.605 | 0.904 | 0.948 | 0.916 | **0.946** | 0.741 |
| C | 11,933 | 0.579 | 0.900 | 0.942 | 0.899 | 0.931 | 0.725 |
| S | 45,051 | 0.453 | 0.784 | 0.838 | 0.703 | 0.819 | 0.588 |
| C2 | 11,933 | 0.585 | 0.876 | 0.916 | 0.854 | 0.890 | 0.709 |

### 4.5 Paired bootstrap（Hit@10，F0 基线）

| 对比 | 差值 | 95% CI | 单侧 p |
|---|---:|---|---:|
| B - F0 | 0.000 | [0.000, 0.000] | 1.000 |
| C - F0 | -0.006 | [-0.022, 0.010] | 0.814 |
| S - F0 | -0.110 | [-0.142, -0.082] | 1.000 |
| C2 - F0 | -0.032 | [-0.054, -0.012] | 0.999 |

解释：

```text
B 与 F0 的首跳完全相同，这是设计使然
C 略低，CI 跨 0，没有正收益证据
S/C2 显著更差
```

### 4.6 C3：top-k 证据聚合

20 条烟测：

| 臂 | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | Context Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|
| C2 max | 0.250 | 0.750 | 0.850 | 0.825 | 0.838 | 0.498 |
| C3 top-2 | 0.350 | 0.850 | 0.900 | 0.825 | 0.875 | 0.553 |
| C3 top-3 | 0.350 | 0.700 | 0.750 | 0.675 | 0.787 | 0.517 |

C3 top-2 比 C2 好，但仍低于 F0 的 Hit@10 0.950。  
全量 C3 运行超时，未纳入结论。

### 4.7 小池 rerank（300 claims，120 词）

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

### 4.8 系统级 baseline（501 claims，120 词 F0 单元）

| 系统 | Hit@1 | Hit@5 | Hit@10 | Sentence Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.549 | 0.794 | 0.852 | 0.800 | 0.653 |
| Dense (F0) | **0.605** | **0.904** | **0.948** | **0.916** | **0.741** |
| Hybrid RRF | 0.591 | 0.872 | 0.922 | 0.889 | 0.714 |

结论：

```text
BM25 明显弱于 dense
等权 RRF hybrid 低于 dense
当前数据上“加 BM25”不是收益来源
```

---

## 5. 分析

### 5.1 B 的收益只在上下文

B 与 F0 的 anchor 指标完全一致：

```text
context 不参与排序
B 只给命中 chunk 加 ±1 句
```

Context recall 提升：

```text
120 词：0.914 -> 0.955
200 词：0.966 -> 0.973
全量：  0.916 -> 0.946
```

结论：

```text
B 适合做“给生成器更完整的证据上下文”
B 不适合做“把 gold sentence 排得更前”
```

### 5.2 句界 chunk 不自动更好

C 在 120/200/500 三档都低于 F0。

原因假设：

```text
句界 chunk 合并了更多完整句子
chunk 语义被更多句子稀释
硬切虽然不优雅，但 chunk 更短、更聚焦
```

这不是“句界错误”，而是“检索单元大小/聚合方式不匹配”。

### 5.3 纯句太细

S：

```text
Hit@10 0.838
Sentence Recall@10 0.703
```

SciFact claim 经常需要多句证据。  
句子是好的**证据单位**，但不是好的**唯一检索单元**。

### 5.4 C2/C3 聚合没有解决首跳

C2 max：

```text
单个高分句主导父 chunk 排序
同一 chunk 内其他证据被丢掉
```

C3 top-2 sum：

```text
比 max 好，但仍低于 F0
```

结论：

```text
问题不是“聚合公式”单独能修的
要么重新定义证据聚合目标，要么接受 chunk 检索
```

### 5.5 Rerank 不是瓶颈

```text
小池 cross-encoder 没有提升首跳
```

说明候选表示/切分比排序器更关键。

### 5.6 Hybrid 不是默认收益

```text
BM25 弱
等权 RRF 低于 dense
```

在当前 SciFact 摘要 + BGE dense 上，lexical 信号没有补足语义召回。

---

## 6. Gate 2

计划要求：

```text
B/C 至少一个显著优于 F0
否则检查 chunk/窗口实现，不继续加方法
```

结果：

```text
B：首跳与 F0 相同，只提升 context
C：低于 F0，CI 跨 0
S/C2/C3：显著更差
Rerank：无收益
BM25/Hybrid：弱于 Dense
```

结论：

```text
Gate 2 未通过
暂停 A / D / E / GA
不把 AutoMerging / GA 叠在没有首跳收益的 chunk 上
```

---

## 7. 决策

```text
1. F0 / Dense 保留为检索基线
2. B 只作为生成上下文层
3. 停止 C 变体与 chunk 参数微调
4. 不再做等权 hybrid 作为默认
5. 暂不进入 A/D/E/GA
```

下一步只有两种合理方向：

```text
A. 接受当前结论，转系统层方法（PaperQA2 / GraphRAG）
B. 重新定义 C 的“证据聚合目标”，而不是继续调 chunk
```

在重新定义前，不再堆方法。

---

## 8. 有效性与限制

### 内部效度

```text
300 条不是独立 dev/test split
4 条全量 claim 因句界缺失被排除
单模型、单数据集、单次运行
C3 仅 20 条，全量超时
Rerank 仅 300 条
```

### 外部效度

```text
SciFact 是摘要级
不能直接外推到全文、生信 workflow、长文档
```

### 构念效度

```text
anchor-only 评分会低估“上下文帮助生成”的价值
所以 B 的价值应单独在 answer/citation 评估中验证
```

### 统计

```text
paired bootstrap 只覆盖 Hit@10
没有做多指标多重比较校正
```

---

## 9. 复现

```bash
# 300 claims, 120 words, S/C2/C3
python -m eval.scifact_phase_c \
  --limit 300 --chunk-words 120 --include-sentence \
  --output eval/results/scifact_phase_c_300_120_S.json

# 全量严格映射 501
python -m eval.scifact_phase_c \
  --limit 0 --chunk-words 120 --include-sentence \
  --output eval/results/scifact_phase_c_501_120_strict.json

# paired bootstrap
python -m eval.scifact_phase_c_stats \
  --input eval/results/scifact_phase_c_501_120_strict.json

# system baselines
python -m eval.scifact_systems \
  --limit 0 --chunk-words 120 \
  --output eval/results/scifact_systems_501.json
```

结果文件：

```text
eval/results/scifact_phase_c_20.json
eval/results/scifact_phase_c_20_120.json
eval/results/scifact_phase_c_300_500.json
eval/results/scifact_phase_c_300_120.json
eval/results/scifact_phase_c_300_200.json
eval/results/scifact_phase_c_300_120_S.json
eval/results/scifact_phase_c_300_120_rerank.json
eval/results/scifact_phase_c_501_120_strict.json
eval/results/scifact_phase_c_20_C3.json
eval/results/scifact_systems_300.json
eval/results/scifact_systems_501.json
```

---

## 10. 结论

```text
500 词：文档级，无法比较 chunk 策略
120/200 词：B 只补上下文，C 不优于 F0
全量 501：B 与 F0 首跳相同，C/S/C2/C3 更差
Rerank：没有救回首跳
BM25/Hybrid：弱于 Dense
Gate 2：未通过
```

最终判断：

```text
F0/Dense 是当前可靠基线
B 是上下文层，不是召回层
Phase C 的方法堆叠到此为止
```
