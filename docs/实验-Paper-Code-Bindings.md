# 实验记录：Paper ↔ Code Library 绑定

> 日期：2026-11-14  
> 状态：绑定表/API 可用；只绑定已有 code library，不自动 ingest  
> 目标：把论文代码链接落到 code RAG library/snapshot

---

## 1. 表

```text
paper_code_libraries
  binding_id
  paper_id
  link_id
  library_id
  snapshot_id
  status bound
  parser_supported
  reason
```

迁移：

```text
deploy/sql/037_paper_code_libraries.sql
```

## 2. API

```text
GET  /api/papers/<paper_id>/code-libraries
POST /api/papers/<paper_id>/code-links/<link_id>/bind
```

请求：

```json
{"library_id": "lib_...", "snapshot_id": "snap_..."}
```

`snapshot_id` 为空时取该 library 最新 snapshot。

## 3. 约束

```text
library_id 必须已存在
不自动下载 repo
不自动执行代码
不创建假 library
parser 支持状态未记录 -> parser_supported=false
```

## 4. HCC 当前情况

已有 code RAG library：

```text
lib_12473817b941  nf-core/rnaseq
lib_2c5709b07c77  scverse/scanpy
```

HCC repo：

```text
https://github.com/Macr0phage/scRNA-seq-of-HCC-immunotherapy
```

没有对应 library；且 R parser 未实现。

所以：

```text
不能绑定
analysis code.status=candidate
```

不把 HCC 错误绑到 scanpy/rnaseq。

## 5. 测试

```text
binding id stable
bind link + snapshot
bad library rejected
```

```text
test_paper_bindings 3 passed
```

## 6. 路由

```text
json_routes=264
app_routes=264
OK
```

## 7. 下一步

```text
1. R parser
2. 创建 paper-private R library
3. 再绑定 snapshot
4. module map
```
