# 实验记录：Federation 论文级视图

> 日期：2026-11-14  
> 状态：paper-level federation；不合并分数  
> 目标：同一 paper 下按来源分组，保留 native

---

## 1. 接口

```text
GET /api/papers/<paper_id>/federated
GET /api/papers/<paper_id>/federated?source_kind=pdf,html
```

MCP：

```text
paper_federated(paper_id, source_kind="")
```

## 2. 返回结构

```text
paper_id
title
doi
groups[]
  source_kind
  source_id
  source_uri
  is_primary
  common
    title
    doi
  native
    pdf:  page_count / paragraph_count
    html: section_count / paragraph_count
    jats: article_type / journal_title / section_count
policy
  scope=paper
  grouped=true
  merge_scores=false
```

## 3. 验证

第二篇：

```text
source_kinds = ["pdf", "html"]

pdf
  page_count 19
  paragraph_count 123

html
  section_count 17
  paragraph_count 323
```

## 4. 边界

```text
只做论文级分组
不做跨论文搜索
不合并跨来源分数
不把 native 字段写进 canonical
```

跨库检索仍是下一步，不属于本次 P5 论文级视图。

## 5. 测试

```text
test_paper_federation 3 passed
test_paper_pdf_native 2 passed
test_paper_html_native 2 passed
```

## 6. 路由

```text
json_routes=273
app_routes=273
OK
```

## 7. 总结

```text
P0 annotation
P1 paper_sources
P2 JATS native
P3 HTML native
P4 PDF native
P5 paper-level federation
```

主库 canonical 没有被新来源污染。
