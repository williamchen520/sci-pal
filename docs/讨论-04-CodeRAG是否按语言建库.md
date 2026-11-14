# 讨论记录：CodeRAG 是否按编程语言单独建库

> 日期：2026-11-14  
> 编号：讨论 04  
> 状态：已形成结论  
> 关联：CodeRAG、混合语言仓库、租户建库管线

---

## 1. 问题

CodeRAG 是否有必要按编程语言单独建库？

例如：

```text
R 库
Python 库
Rmd 库
Shell 库
```

---

## 2. 结论

```text
不按语言分库。
按 租户 / library / repo / snapshot 分库。
语言是字段和解析器维度，不是物理库边界。
```

---

## 3. 理由

### 3.1 一个仓库经常混合语言

```text
analysis.R
run.py
figure.Rmd
preprocess.sh
```

按语言分库会把同一个 repo 拆开，破坏 snapshot 一致性。

### 3.2 跨语言边会丢

现有 CodeRAG 支持：

```text
source()
reticulate
rpy2
subprocess
CLI 调用
```

这些边天然跨语言。

按语言分库后：

```text
R unit -> Python unit
```

要么变成跨库边，要么丢失。

### 3.3 查询需要一次看全仓库

用户问：

```text
“这个项目的预处理和画图分别在哪”
```

答案可能在 Python + R 两个文件。

按语言分库会变成：

```text
R group
Python group
```

然后要求上层合并，违反“不跨库合并分数”。

### 3.4 共同 schema 足够

```text
code_library
  snapshot
  files
  units
    language
    parser
    parser_version
  edges
  embeddings / FTS
```

语言只影响：

```text
parser adapter
native payload
可选 language filter
```

不需要影响物理库边界。

### 3.5 运维成本

按语言分库意味着：

```text
N 个 DB
N 套迁移
N 套备份
N 套索引
N 套连接池
```

收益很小。

---

## 4. 推荐结构

```text
tenant_acme
  code_library: hcc_project
    snapshot_001
      files
      units(language=r/python/rmd)
      edges
      index
```

查询：

```text
library_id
snapshot_id
language=optional filter
```

不是：

```text
library_id = r_library
library_id = python_library
```

### 语言特有字段

```text
code_units.language
code_units.parser
code_units.parser_version
native_json
```

或者：

```text
code_unit_r
code_unit_python
code_unit_rmd
```

作为 side table，但仍在同一个 library/snapshot 下。

---

## 5. 什么情况下才按语言分开

只有这些情况：

```text
1. 某语言需要完全不同的索引后端
2. 某语言需要独立的安全/合规边界
3. 某语言数据量极大，单独扩缩容
4. 某语言需要独立保留/删除策略
```

即使这样，也应该是：

```text
同一个逻辑 library
不同物理 index
联邦分组返回
```

而不是默认按语言建库。

---

## 6. 当前代码判断

当前 `code_rag` 已有：

```text
library_id
snapshot_id
file_language
unit_type
```

R / Python / Rmd 混合仓库已经可以入同一个 library。

因此不需要为了语言新增数据库。

需要补的是：

```text
parser plugin registry
language-specific native payload
language filter
```

不是：

```text
language-specific database
```

---

## 7. 一句话

```text
按仓库和快照分库，
按语言分解析器和索引分区，
不按语言分数据库。
```
