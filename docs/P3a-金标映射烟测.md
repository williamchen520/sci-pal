# P3a 金标映射烟测

> 日期：2026-11-08  
> 状态：**通过（结构层，不是独立语料 bench）**  
> 语料：`eval/gold/regression_20.jsonl`

---

## 1. 目的

在导入外部全文语料之前，先验证：

```text
金标 paper_id 能否找到 document
金标 evidence sentence 能否找到 paragraph/paper
paper 是否都有 work/document 映射
```

---

## 2. 结果

```text
questions             20
questions fully ok    20
paper refs            20
evidence sentences    25
mapped evidence       25
missing                0
```

含义：

```text
20/20 题的全部 paper_id 都有 library_main.paper_documents
25/25 evidence sentence 都能回到 paper/paragraph
0 个映射缺口
```

---

## 3. 结论

```text
P1/P2 的 work/document 身份层可以承接现有金标
paper_id -> document_id -> work_id 链路成立
```

---

## 4. 这不是完整 P3

尚未做：

```text
独立 library_bench
20-30 篇公开全文导入
10 题金标重新映射
bench-only 检索
```

原因：

```text
公开全文语料存在许可与下载限制
不能把主库论文直接当独立 bench
```

---

## 5. 下一步

P3b 需要选一个公开全文语料：

```text
QASPER
PMC OA 20-30 篇
其他允许再分发的全文集
```

选型标准：

```text
明确许可
有全文
有 evidence 标注或可人工标注
能固定 parser_version
```

在语料选定前，不把主库论文复制成 bench，避免污染。
