# 实验记录：code-rag P2 AST/结构入库

> 日期：2026-11-12  
> 状态：**两 repo 已入库；无 embedding/search**  
> 模块：`code_rag/`

---

## 1. 目标

验证：

```text
Python AST 能否稳定切出 function/class/imports/calls
Nextflow 能否切出 process/workflow/include
两个外部 repo 能否重复入库
所有 unit 是否带 library_id + snapshot_id
```

## 2. 固定版本

```text
scanpy         1.12.5   BSD-3-Clause
nf-core/rnaseq 3.28.0   MIT
```

`snapshot_id` 由 repo + commit 生成。

## 3. 入库结果

### scanpy

```text
files       208
units      1,819
  file       208
  function 1,527
  class       84
edges     11,437
```

### nf-core/rnaseq

```text
files       254
units        759
  file       254
  process    476
  workflow    29
edges        143
```

### 总体

```text
libraries 2
snapshots 2
units    2,578
```

health：

```text
ok=true
schema_version=1
```

## 4. Parser 行为

### Python

```text
tree-sitter-python
file unit
function/class unit
imports 边
calls 边（未解析目标，unresolved:）
父子关系
```

### Nextflow

```text
process / workflow block scanner
file unit
process/workflow unit
include 边
```

限制：

```text
Nextflow 还没有正式 grammar
parser 是保守 block scanner
不解析 dynamic include / channel 数据流
```

## 5. 已知缺口

```text
没有 embedding
没有 code_search / code_trace
没有 rerank
没有 version/API diff
Python calls 目标是文本，不是符号绑定
Nextflow config override 还没建边
```

## 6. 结论

```text
P2 结构入库可用
unit/edge 可复现
两 repo 均可按 library_id 隔离
```

下一步 P3：

```text
code_units embedding
code_search 混合检索
code_trace
按 library_id 过滤
```
