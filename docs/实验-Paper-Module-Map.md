# 实验记录：Paper Module Map

> 日期：2026-11-14  
> 状态：从已绑定 code library 汇总模块；不生成 LLM 说明  
> 目标：给 `scipal-paper` 提供 file/module 级视图

---

## 1. 服务

```text
services/papers/modules.py
GET /api/papers/<paper_id>/modules
```

返回：

```text
path
language
unit_count
symbols
imports[]
purpose
purpose_evidence[]
purpose_source=inferred
purpose_confidence=low
edges {imports, calls}
```

`imports` 已去掉 `unresolved:library:` 前缀，直接是包名。

## 2. HCC 实测

```text
status   ok
modules  7
```

| module | units | symbols | imports |
|---|---:|---|---:|
| Figure.1.R | 1 | Figure.1.R | 12 |
| Figure.2.R | 3 | Figure.2.R, new_function1, new_function2 | 23 |
| Figure.3.R | 1 | Figure.3.R | 12 |
| Figure.4.R | 1 | Figure.4.R | 17 |
| Figure.5.R | 1 | Figure.5.R | 19 |
| Figure.6.R | 1 | Figure.6.R | 17 |
| Figure.7.R | 1 | Figure.7.R | 17 |

## 3. 实际 imports

```text
Figure.1.R
  clusterProfiler, data.table, dplyr, ggalluvial,
  ggplot2, ggsci, harmony, NMF ...

Figure.2.R
  AUCell, clusterProfiler, ComplexHeatmap,
  data.table, dplyr, ...
```

## 4. Purpose（推断）

改用代码里的真实调用推断，不调用 LLM：

```text
Figure.1.R
  Figure 1 analysis; cell-cell communication;
  batch integration; clustering; NMF programs

Figure.2.R
  Figure 2 analysis; CNV inference; regulon scoring;
  metabolism; batch integration; clustering;
  NMF programs; pathway scoring

Figure.3.R
  Figure 3 analysis; batch integration;
  clustering; NMF programs
  evidence: runharmony, findneighbors, nmf

Figure.6.R
  Figure 6 analysis; cell-cell communication;
  regulon / SCENIC; regulon scoring; cell annotation;
  batch integration; clustering
  evidence: callcall/scenic/aucell/singler/runharmony/findneighbors
```

## 5. 解释

这 7 个脚本主要是顶层分析脚本：

```text
file unit
```

Figure.2 有两个函数单元，所以是 3 个 unit。

`unit_count` 不等于“业务模块数”；它反映 parser 看到的单元。

## 6. 不做什么

```text
不生成 LLM 模块说明
不猜 purpose
不把 file unit 当函数
```

`purpose` 留给 scipal-paper/LLM 基于代码与论文生成，并必须标 inferred。

## 7. 测试

```text
unbound -> status unbound
bound -> modules 1, imports 12
```

```text
test_paper_modules 2 passed
```

## 8. 路由

```text
json_routes=265
app_routes=265
OK
```

## 9. 下一步

```text
1. purpose 生成（标 inferred）
2. data flow edges
3. Rmd/mixed parser
```
