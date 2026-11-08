# P3b Bench 结构 Smoke 结果

> 日期：2026-11-08  
> 语料：25 篇 Europe PMC / NCBI PMC CC BY 全文 XML  
> 状态：**结构 smoke 通过，不是质量评测**

---

## 1. 入库结果

```text
documents        25
source_nodes  1,651
sections        543
paragraphs    1,083
sentences     5,096
FTS vectors   5,096
```

---

## 2. 金标

`eval/bench/p3b_questions.jsonl`：

```text
10 题
10 个不同 document
每题 1 个 gold paragraph
每题 1 个 gold sentence
```

说明：

```text
题目由标题引导生成，用于结构 smoke
不是自然语言质量金标
不能用于最终 Recall/nDCG 结论
```

---

## 3. 检索 smoke

使用 bench-only FTS：

```text
library_bench.sentences.search_vector
to_tsquery OR 关键词
top 10
```

结果：

```text
gold_in_top10  10 / 10
```

逐题：

```text
p3b_q001 hit
p3b_q002 hit
p3b_q003 hit
p3b_q004 hit
p3b_q005 hit
p3b_q006 hit
p3b_q007 hit
p3b_q008 hit
p3b_q009 hit
p3b_q010 hit
```

---

## 4. 这验证了什么

```text
library_bench schema 可用
25 篇 XML 可解析入库
work/document/node 可建立
FTS 可检索
10 题金标可映射
```

---

## 5. 没有验证

```text
向量召回
HNSW
真实自然语言问题
bench-only API
与 main 的联邦检索
```

---

## 6. 结论

```text
P3b 结构 smoke 通过
可以作为独立 benchmark library 继续扩展
不能把 10/10 当作检索质量结论
```

下一步：

```text
P4 租户隔离
或 P5 联邦检索
```
