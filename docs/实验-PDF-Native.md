# 实验记录：PDF Native 来源层

> 日期：2026-11-14  
> 状态：2 PDF / 235 paragraphs；page/bbox 独立存储  
> 目标：PDF 页面特征不进 canonical

---

## 1. 表

```text
pdf_documents
  source_id
  paper_id
  source_uri
  content_hash
  parser
  page_count
  native_json

pdf_paragraphs
  source_id
  native_para_id
  para_id
  page
  bbox
  text
  para_order
```

迁移：

```text
deploy/sql/043_pdf_native.sql
```

## 2. 回填

```text
scripts/backfill_pdf_native.py
```

结果：

```text
sources     2
paragraphs 235

HCC LAM     23 pages
HCC Genomic 19 pages
```

## 3. API

```text
GET /api/papers/<paper_id>/pdf-native
GET /api/papers/<paper_id>/pdf-native?include_paragraphs=1
```

MCP：

```text
paper_pdf(paper_id, include_paragraphs=False)
```

## 4. 为什么不复用 `/pdf`

```text
/api/papers/<id>/pdf          已有 PDF 文件下载
/api/papers/<id>/pdf-native   PDF 原生字段
```

两个语义不同，不能合并。

## 5. 边界

```text
不重新解析 PDF
不覆盖 canonical page/bbox
不生成新的 sentences
只把 page/bbox 复制到 pdf_paragraphs
```

## 6. 测试

```text
test_paper_pdf_native 2 passed
test_paper_html_native 2 passed
test_paper_jats 2 passed
test_paper_sources 1 passed
```

## 7. 路由

```text
json_routes=272
app_routes=272
OK
```

## 8. 下一步

```text
P5 federation scope
```
