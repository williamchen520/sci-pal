# 实验记录：code-rag P6 30 问题评测

> 日期：2026-11-12  
> 状态：**30 题内部评测完成；baseline 是 grep-like 代理，不是完整 DSH 基线**  
> 数据：`eval/code_rag_30.json`

---

## 1. 数据集

```text
30 题
  symbol       10（scanpy）
  api           3（scanpy）
  dataflow      2（scanpy）
  workflow     15（nf-core/rnaseq）
```

每题的 gold：

```text
expected_symbol
expected_path
```

所有 expected 都先在 `scipal_code` 里确认存在。

## 2. 两条路线

### code arm

```text
code_rag.search
  exact symbol
  symbol token boost
  trigram
  vector
  RRF
  path penalty（tests/benchmarks）
```

### baseline

```text
按 file unit 做 grep-like 词法扫描
  query token 出现次数
  path 命中加权
  tests/benchmarks 不特殊处理
```

baseline 不包含：

```text
LSP
实际 read 工具
多轮
```

所以它是 **DSH grep 的代理**，不是完整 DSH 基线。

## 3. 指标

| 指标 | code | baseline |
|---|---:|---:|
| File Hit@1 | **0.700** | 0.300 |
| File Hit@3 | **0.967** | 0.600 |
| File Hit@5 | **1.000** | 0.800 |
| Symbol Hit@1 | **0.767** | — |
| Symbol Hit@5 | **1.000** | — |

代码侧：

```text
30 题
File@1 21/30
File@3 29/30
File@5 30/30
```

baseline：

```text
File@1 9/30
File@5 24/30
```

## 4. 失败/靠后项

| 题 | code 文件 rank | baseline |
|---|---:|---:|
| highly variable genes | 3 | 2 |
| neighbor graph construction | 3 | 2 |
| compute UMAP embedding | 3 | 2 |
| PCA principal component analysis | 3 | 1 |
| rank genes between groups | 3 | 1 |
| read 10x mtx directory | 4 | 2 |
| read visium spatial data | 2 | 4 |
| rseqc bam statistics | 2 | 12 |
| qualimap rnaseq qc | 2 | 4 |

解释：

```text
同 symbol 多文件（pca/umap/neighbors）造成 path 不唯一
测试/benchmark 已降权，但仍会进入候选
baseline 在这些词法强的题上会赢
```

## 5. 与 P3 10 题的关系

P3 10 题：

```text
Hit@1 0.80
Hit@5 1.00
```

P6 30 题：

```text
File@1 0.70
File@5 1.00
```

30 题更难，且包含 workflow/api，不是退步。

## 6. 不能声称什么

```text
不能声称真实用户查询 70%
不能声称优于完整 DSH 基线
不能声称代码理解正确
```

能声称：

```text
在这 30 条内部问题上
按文件/符号召回优于 grep-like 基线
且在 @5 达到 100%
```

## 7. 结论

```text
P6 通过“可用性”门槛
但没有通过“强泛化”证明
```

下一步：

```text
1. 用真实 DSH 会话记录做 30 题
2. 补 baseline 的 read/LSP
3. 再做版本/API 问题
```
