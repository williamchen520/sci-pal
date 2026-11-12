# PaperQA2 适配烟测

> 日期：2026-11-12  
> 状态：**集成烟测完成；不是 PaperQA2 原生能力评测**  
> 环境：独立 venv `G:\venvs\paperqa`，Python 3.12

---

## 1. 安装问题与解决

### 现象

```text
paper-qa==2026.8.12 安装长时间无输出
import paperqa 卡住
```

### 根因

```text
1. 第一次隔离 venv 用了 Python 3.15
2. LiteLLM 导入时联网拉 model cost map
```

### 解决

```text
用 Python 3.12 重建 venv
LITELLM_LOCAL_MODEL_COST_MAP=true
```

结果：

```text
paper-qa 2026.8.12 安装成功
import paperqa 成功
主 venv 未污染
```

已安装关键包：

```text
paper-qa==2026.8.12
fhlmi==1.11.0
fhaviary==0.37.0
tantivy==0.27.0
pydantic==2.14.3
numpy==2.5.4
```

---

## 2. 为什么用 sparse

PaperQA 的本地 dense embedding 需要：

```text
lmi[local]
sentence-transformers
torch
```

隔离 venv 已经装了 torch，但 `sentence-transformers` 安装耗时过长，已停止。  
因此本轮使用 **PaperQA 自带 SparseEmbeddingModel**：

```text
PaperQA Docs
+ SparseEmbeddingModel
+ retrieve_texts
```

不启用：

```text
LLM
PDF 解析
agentic answer
dense embedding
```

这是**检索适配烟测**，不是 PaperQA2 原生端到端评测。

---

## 3. 适配方式

数据：

```text
data/benchmark_scifact.db
5,183 papers
45,051 sentences
```

构造：

```text
每个 paper 一个 PaperQA Doc
每个 sentence 一个 PaperQA Text
Text.name = sentence_id
Docs.aadd_texts(...)
```

检索：

```text
Docs.retrieve_texts(claim, k=10)
命中 Text.name 与 gold sentence_id 比较
```

代码：

```text
eval/paperqa_smoke.py
```

运行：

```powershell
$env:LITELLM_LOCAL_MODEL_COST_MAP = "true"
G:\venvs\paperqa\Scripts\python.exe eval\paperqa_smoke.py --limit 50
```

---

## 4. 结果

### 5 claims 烟测

```text
docs 5,183
Hit@1  0.20
Hit@5  0.20
Hit@10 0.20
MRR    0.20
```

### 50 claims 烟测

```text
docs            5,183
Hit@1           0.080
Hit@5           0.180
Hit@10          0.220
Sentence Recall 0.144
MRR             0.132
```

结果文件：

```text
eval/results/paperqa_smoke_5.json
eval/results/paperqa_smoke_50.json
```

---

## 5. 解释

### 这不是 PaperQA2 原生成绩

PaperQA2 原生依赖：

```text
dense embedding
LLM 证据筛选/摘要
agentic QA
PDF/full-text
```

本轮只用了：

```text
sparse retrieval
无 LLM
摘要/句子级文本
```

所以 0.22 不能说明 PaperQA2 不行，也不能与 F0/Dense 的 0.948 直接比较。

### 为什么仍值得记录

```text
验证了 PaperQA Docs/Text/retrieve_texts 适配路径
验证了 45k sentence 文档能进入 PaperQA 索引
暴露了 sparse-only 在 SciFact claim 上明显不足
```

### 潜在原因

```text
sparse 查询与 claim 语义不匹配
MMR 选择多样性，降低精确命中
sentence 级 Text 没有 chunk 上下文
没有 LLM/agentic evidence selection
```

---

## 6. 决策

```text
PaperQA2 原生评测：未完成
本轮结论：只完成 adapted sparse 集成烟测
不把 0.22 写成 PaperQA2 的方法结论
不在主 venv 安装 PaperQA
```

如果继续：

```text
1. 在隔离 venv 完成 sentence-transformers/dense
2. 或使用 OpenAI-compatible embedding
3. 用 PaperQA 原生 PDF/agent 路径
4. 再和 F0/Dense 做同任务对比
```

---

## 7. 当前边界

```text
已解决：PaperQA2 安装、导入、Docs/Text 适配
未解决：dense embedding、LLM provider、原生 PDF/agent
已记录：50 claims sparse smoke
```

Phase C 结论不变：

```text
F0 / Dense 是当前可靠检索基线
B 是上下文层
PaperQA2 尚无可用原生结果
```
