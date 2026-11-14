# 实验记录：R Parser v1

> 日期：2026-11-14  
> 状态：R 文件级/函数级保守解析 + code RAG ingest + paper binding 可用  
> 边界：不是完整 R AST；Rmd/S4 深度解析后续补

---

## 1. 解析能力

```text
file unit
function <- function(...)
R6Class
setClass / setGeneric / setMethod
library() / require()
source()
```

实现：

```text
code_rag/parsers.py::parse_r
```

## 2. code RAG 接入

```text
--language r
files: **/*.R, **/*.r
```

ingest：

```text
scipal_code
  code_sources
  code_snapshots
  code_files
  code_units
  code_edges
```

## 3. HCC 实测

repo：

```text
https://github.com/Macr0phage/scRNA-seq-of-HCC-immunotherapy
```

result：

```text
language=r
files=7
units=9
edges=122
snapshot=snap_0e56caa7d3fe57a8
```

unit 少的原因：

```text
这 7 个 Figure 脚本几乎没有 function 定义
主要是顶层脚本
所以 7 个 file unit + 少量 class unit
```

这符合实际，不是解析失败。

## 4. Binding

```text
paper: paper_nature_hcc_lipid_macrophage_b3cb651d2d57
link:  link_787d1466865b23d4
library: lib_paper_hcc_r
snapshot: snap_0e56caa7d3fe57a8
parser_supported: true
reason: R parser v1: file/function units
```

## 5. Code Search

```text
POST /libraries/lib_paper_hcc_r/search
query: Figure 1 Harmony
```

返回：

```text
Figure.1.R
lines 1-91
snapshot snap_0e56...
```

## 6. 测试

```text
function
R6Class / setClass
library / source edges
comment braces
```

```text
test_code_rag_r_parser 3 passed
test_paper_bindings    3 passed
```

## 7. 限制

```text
不是 tree-sitter-r AST
复杂参数默认值可能漏 function
S4/R6 目前是文件级/粗略 span
Rmd/Quarto 未支持
混合 R/Python 只按文件识别
```

## 8. 下一步

```text
1. tree-sitter-r 或 R parse fallback
2. Rmd/Quarto chunk
3. mixed repo auto detect
4. module map
```
