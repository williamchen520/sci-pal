# 实验记录：Paper Code Links

> 日期：2026-11-14  
> 状态：代码链接抽取/人工补录/只读 API 可用；尚未自动校验 license/commit  
> 目标：给 `scipal-paper` 提供论文 → 代码入口

---

## 1. 表

```text
paper_code_links
  link_id
  paper_id
  url
  repo_type
  license
  commit_sha
  confidence
  evidence_para_id
  status candidate/validated/rejected
```

迁移：

```text
deploy/sql/036_paper_code_links.sql
```

已授权：

```text
scipal_corpus_writer  SELECT/INSERT/UPDATE/DELETE
scipal_corpus_reader  SELECT
```

## 2. API

```text
GET  /api/papers/<paper_id>/code-links
POST /api/papers/<paper_id>/code-links
POST /api/papers/<paper_id>/code-links/extract
```

## 3. 抽取

从 paragraphs 正则提取：

```text
github.com
gitlab.com
bitbucket.org
zenodo.org
doi.org/10.5281
```

只入库，不下载、不执行。

## 4. HCC 实测

```text
extracted 2
```

结果：

```text
https://github.com/Macr0phage/scRNA-seq-of-HCCimmunotherapy   # PDF 断行导致
https://doi.org/10.5281/zenodo.20664347
```

人工补录正确 repo：

```text
https://github.com/Macr0phage/scRNA-seq-of-HCC-immunotherapy
```

analysis 入口：

```text
status ok
sections 43
code candidate
links 3
```

## 5. 为什么保留坏链接

```text
抽取只是候选
不静默修正
人工确认
```

正确 repo 目前已作为 candidate 入库，等待验证。

## 6. 测试

```text
extract + dedupe
manual host allowlist
manual link
```

```text
test_paper_code_links 3 passed
```

## 7. 路由

```text
json_routes=261
app_routes=261
OK
```

## 8. 下一步

```text
1. 人工标记坏链接 rejected
2. license / commit 校验
3. code RAG library 绑定
4. module map
```
