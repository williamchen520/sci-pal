# 实验记录：Paper Sources 来源层

> 日期：2026-11-14  
> 状态：13,201 JATS + 2 PDF 来源记录；主库树未改  
> 目标：来源差异先落 source 层，不强迫 canonical 对齐

---

## 1. 表

```text
paper_sources
  source_id
  paper_id
  source_kind      jats / html / pdf
  source_uri
  content_hash
  parser
  parser_version
  is_primary
  retrieved_at
  metadata
```

迁移：

```text
deploy/sql/040_paper_sources.sql
```

## 2. 回填

```text
scripts/backfill_paper_sources.py
```

结果：

```text
jats 13,201
pdf       2
total 13,203
```

JATS：

```text
source_uri = documents_xml/<PMC>.xml
parser = jats
metadata.pmcid
```

PDF：

```text
HCC LAM     documents/nature_hcc_lipid_macrophage.pdf
HCC Genomic documents/hcc_genomic.pdf
```

## 3. API

```text
GET /api/papers/<paper_id>/sources
```

MCP：

```text
paper_sources(paper_id)
```

## 4. 边界

```text
只记录来源
不重新解析
不改变 sections/paragraphs/sentences
不把 JATS 特有字段塞进 canonical
```

## 5. 测试

```text
test_paper_sources 1 passed
```

## 6. 路由

```text
json_routes=269
app_routes=269
OK
```

## 7. 下一步

```text
P2 JATS native fields
P3 HTML source store
P4 PDF source store
P5 federation scope
```
