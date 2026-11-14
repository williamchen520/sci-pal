# 实验记录：JATS Native 原生层

> 日期：2026-11-14  
> 状态：2,819 JATS / 69,407 sections 入库  
> 目标：保留 JATS 原生 `article-type`、license、`sec-type`，不写 canonical

---

## 1. 表

```text
jats_articles
  source_id
  paper_id
  article_type
  journal_title
  article_title
  license
  native_json

jats_sections
  source_id
  native_section_id
  sec_type
  title
  depth
  section_path
  section_order
```

迁移：

```text
deploy/sql/041_jats_native.sql
```

## 2. 回填

```text
scripts/backfill_jats_native.py --xml-dir D:\sciPal\documents_xml
```

结果：

```text
files    2,819
sections 69,407
skipped      1
```

article-type：

```text
research-article 550
review-article   273
editorial         52
空              1,634
```

sec-type 前端：

```text
空                  57,189
supplementary-material 1,290
COI-statement        1,106
data-availability      845
discussion             813
intro                  779
results                761
```

## 3. API

```text
GET /api/papers/<paper_id>/jats
```

MCP：

```text
paper_jats(paper_id)
```

示例：

```text
paper_PMC10360191
article_type=review-article
sections=23
```

## 4. 边界

```text
只解析本地 documents_xml 的 2,820 个文件
10,382 个 JATS source 没有本地 XML
不重新生成 sections/paragraphs
不把 sec_type 写进 canonical
```

## 5. 测试

```text
test_paper_jats    2 passed
test_paper_sources 1 passed
```

## 6. 路由

```text
json_routes=270
app_routes=270
OK
```

## 7. 下一步

```text
P3 HTML source store
P4 PDF source store
P5 federation scope
```
