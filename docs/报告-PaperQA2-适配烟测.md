# 实验报告：PaperQA2 适配烟测

> 日期：2026-11-12  
> 数据集：SciFact abstracts  
> 任务：PaperQA2 检索路径适配，不是原生端到端问答  
> 状态：**集成烟测完成；无原生可比结论；系统层停止**

---

## 摘要

本实验回答两个问题：

```text
PaperQA2 能否在当前隔离环境中安装并接入 SciFact？
接入后能否与 F0/Dense 做公平比较？
```

结果：

```text
安装：可以，但需要 Python 3.12 + 本地 LiteLLM cost map
sparse：sentence-level 全量 50 claims，Hit@10 0.22
dense：abstract-level 采样 500 docs，Hit@10 1.00
```

但 dense 结果是：

```text
paper-level
采样语料
包含全部 gold papers
无 LLM / PDF / agent
```

所以：

```text
不能写成 PaperQA2 优于 F0/Dense
只证明 Docs/Text/retrieve_texts 适配路径可用
```

最终决定：

```text
系统层停止
F0/Dense 仍是 Phase C 的可靠基线
PaperQA2 原生全量需要 GPU/LLM，当前不划算
```

---

## 1. 研究问题

### RQ1

PaperQA2 能否在隔离 venv 中安装并导入？

### RQ2

PaperQA2 的 `Docs/Text/retrieve_texts` 能否接入 SciFact 的 paper/sentence 结构？

### RQ3

适配后的检索能否与 F0/Dense 比较？

---

## 2. 环境与安装

### 初始失败

```text
第一次隔离 venv 使用 Python 3.15
paper-qa 安装长时间无输出
import paperqa 卡住
```

### 根因

```text
1. Python 3.15 与依赖栈不匹配
2. LiteLLM 导入时联网拉 model cost map
   请求被代理挂住
```

### 解决

```text
Python 3.12 重建隔离 venv
LITELLM_LOCAL_MODEL_COST_MAP=true
```

### 最终环境

```text
venv          G:\venvs\paperqa
python        3.12.10
paper-qa      2026.8.12
torch         2.15.0 (CPU)
transformers  5.22.2
sentence-transformers 6.3.0
fhlmi         1.11.0
fhaviary      0.37.0
tantivy       0.27.0
```

主 venv 未安装 PaperQA。

---

## 3. 数据与适配

### 数据

```text
SciFact papers       5,183
sentences            45,051
claims                 505
本轮使用前 50 claims
```

### Sparse 适配：sentence-level

```text
每个 paper -> 一个 Doc
每个 sentence -> 一个 Text
Text.name = sentence_id
Docs.aadd_texts(...)
Docs.retrieve_texts(claim, k=10)
```

语料：

```text
5,183 docs
45,051 texts
```

### Dense 适配：abstract-level

```text
每个 paper -> 一个 Doc
整个 abstract -> 一个 Text
Text.name = paper_id
```

语料：

```text
500 docs
= 50 claims 的 gold papers + distractor
```

dense 模型：

```text
BAAI/bge-small-en-v1.5
device = cpu
```

### 为什么 dense 用采样

```text
隔离 venv 的 torch 是 CPU 版
45k sentence dense 在 CPU 上超时
abstract 级 5k 仍慢
因此退到 500 docs 采样
```

---

## 4. 结果

### Sparse，sentence-level，全量 50 claims

| 指标 | 值 |
|---|---:|
| Hit@1 | 0.080 |
| Hit@5 | 0.180 |
| Hit@10 | 0.220 |
| Sentence Recall@10 | 0.144 |
| MRR@10 | 0.132 |

5 claims 烟测：

```text
Hit@10 0.20
```

### Dense，abstract-level，500 docs

| 指标 | 值 |
|---|---:|
| Hit@1 | 0.960 |
| Hit@5 | 1.000 |
| Hit@10 | 1.000 |
| Evidence paper Recall@10 | 1.000 |
| MRR@10 | 0.980 |

5 claims，300 docs：

```text
Hit@1/5/10 1.000
MRR        1.000
```

---

## 5. 分析

### 5.1 Sparse 全量句级很差

```text
Hit@10 0.22
```

可能原因：

```text
sparse 查询与 claim 语义不匹配
MMR 选择多样性，降低精确命中
sentence 级 Text 没有 chunk 上下文
没有 LLM evidence selection
```

### 5.2 Dense 采样结果不能当方法结论

dense 结果高的原因：

```text
paper-level，粒度更粗
500 docs 包含全部 gold papers
distractor 只有 135 篇
没有 5,183 全量竞争
```

这不公平：

```text
论文级命中比句级容易
采样语料比全量容易
gold 泄漏在语料中
```

### 5.3 这不是 PaperQA2 原生

原生 PaperQA2 还需要：

```text
PDF/full-text 解析
dense embedding
LLM 证据筛选/摘要
agentic QA
```

本轮只验证：

```text
PaperQA Docs/Text/retrieve_texts 适配
sparse 全量 sentence 检索
dense 采样 paper 检索
```

### 5.4 与 Phase C 的关系

```text
Phase C F0/Dense 是 sentence-level、全量 501、固定评测
PaperQA2 本轮是 50 claims、paper-level 采样
两者不可直接比较
```

---

## 6. 有效性威胁

### 内部效度

```text
dense 采样包含 gold papers
paper-level 粒度
仅 50 claims
单模型、单次运行
CPU 小模型
```

### 外部效度

```text
SciFact abstracts
不是全文、不是生信 workflow
```

### 构念效度

```text
PaperQA2 的价值可能在 agentic QA，不在纯检索
用 retrieval-only 评它，天然低估
```

### 结论效度

```text
不能从 0.22 推出 PaperQA2 不行
也不能从 1.00 推出 PaperQA2 很强
```

---

## 7. 决策

```text
系统层停止
不继续 PaperQA2 采样堆结论
不做 GraphRAG
保持 Phase C 结论：F0/Dense 基线，B 上下文层
```

如果未来重启：

```text
1. 隔离 GPU 环境
2. 全量 5,183 docs
3. dense + LLM 原生
4. 固定 budget/模型
5. 与 F0/Dense 同任务比较
```

---

## 8. 复现

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP = "true"

# sparse sentence-level 50
G:\venvs\paperqa\Scripts\python.exe eval\paperqa_smoke.py `
  --limit 50 --embedding sparse `
  --output eval/results/paperqa_smoke_50.json

# dense abstract-level 50
G:\venvs\paperqa\Scripts\python.exe eval\paperqa_abstract_smoke.py `
  --limit 50 --max-docs 500 `
  --output eval/results/paperqa_abstract_50_500.json
```

产物：

```text
eval/paperqa_smoke.py
eval/paperqa_abstract_smoke.py
eval/results/paperqa_smoke_5.json
eval/results/paperqa_smoke_50.json
eval/results/paperqa_abstract_5_300.json
eval/results/paperqa_abstract_50_500.json
docs/实验-PaperQA2-适配烟测.md
```

---

## 9. 结论

```text
PaperQA2 安装问题已解决
Docs/Text/retrieve_texts 适配可用
sparse 全量句级不足
dense 采样结果不可比较
PaperQA2 原生未完成
系统层停止
```

最终：

```text
Phase C 的 F0/Dense 仍是可靠基线
PaperQA2 没有可用原生结果
不能写成优于或劣于 F0/Dense
```
