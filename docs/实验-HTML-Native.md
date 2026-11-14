# 实验记录：HTML Native 来源层

> 日期：2026-11-14  
> 状态：1 个 HTML source / 17 sections / 323 paragraphs  
> 目标：HTML 独立入库，不塞进 canonical

---

## 1. 表

```text
html_articles
  source_id
  paper_id
  source_url
  content_hash
  title
  doi
  journal
  published
  license
  native_json

html_sections
  source_id
  native_section_id
  title
  section_order

html_paragraphs
  source_id
  native_para_id
  section_id
  text
  para_order
```

迁移：

```text
deploy/sql/042_html_native.sql
```

## 2. 导入

```text
scripts/import_html_source.py
```

示例：

```powershell
python scripts/import_html_source.py `
  --paper-id paper_hcc_genomic_4492073cf016 `
  --file G:\runs\nature2.html `
  --source-url https://www.nature.com/articles/s41467-026-73212-y
```

结果：

```text
source     src_6f2826d4fb2cdc71
sections   17
paragraphs 323
hash       efbd6d3c50d7
```

同一论文现在有：

```text
jats? no
html  yes
pdf   yes
```

## 3. API

```text
GET /api/papers/<paper_id>/html
GET /api/papers/<paper_id>/html?include_paragraphs=1
```

MCP：

```text
paper_html(paper_id, include_paragraphs=False)
```

## 4. 边界

```text
HTML 不进入 sections/paragraphs/sentences
不覆盖 PDF 的 page/bbox
不覆盖 JATS 的 sec-type
只保留 HTML 自己的 DOM/标题/段落
```

## 5. 测试

```text
test_paper_html_native 2 passed
test_paper_jats        2 passed
test_paper_sources     1 passed
```

## 6. 路由

```text
json_routes=271
app_routes=271
OK
```

## 7. 下一步

```text
P4 PDF source store
P5 federation scope
```
