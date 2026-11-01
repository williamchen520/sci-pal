# P3 PDF 重建

> 日期：2026-11-01  
> 目标库：`scipal_v2`  
> 范围：PDF 结构 + `pdf_pages` / `pdf_blocks` + page/bbox。

---

## 1. 源数据

```text
PDF papers in SQLite: 83
PDF files in documents/: 78
```

缺源文件的论文仍保留已解析结构；`pdf_pages/pdf_blocks` 无法重建时为空，不伪造。

---

## 2. 实现

```text
build_db/pg_v2_import_pdf.py
```

结构来源：

```text
SQLite 已解析的 sections / paragraphs / sentences / figures / tables
```

版面来源：

```text
PyMuPDF 重新读取源 PDF
→ pdf_pages
→ pdf_blocks（page + bbox + block_type + text）
```

坐标：

```text
page + bbox 保留
coordinate_source = 'pdf'
```

图表：

```text
figures/tables 用 page 找最近的 section
placement_source = 'pdf-region'
找不到 → unresolved
```

---

## 3. 全量结果

```text
papers       83
sections  1,577
paragraphs 13,202
sentences 61,739
figures      286
tables       155
pdf_pages  1,374
pdf_blocks 26,901
```

### 与旧 SQLite 对比

| 表 | 旧 SQLite | v2 | 差异 |
|---|---:|---:|---:|
| sections | 1,577 | 1,577 | 0 |
| paragraphs | 13,202 | 13,202 | 0 |
| sentences | 61,739 | 61,739 | 0 |
| figures | 286 | 286 | 0 |
| tables | 155 | 155 | 0 |

结论：

```text
PDF 结构零丢失
```

### 坐标

```text
PDF sentences 61,739
  page + bbox 全部保留

figures 286
  page 267
  bbox 267

tables 155
  page 0
  bbox 0
```

表格在旧 SQLite 中就没有 page/bbox，v2 不伪造。

---

## 4. 10 篇 PDF 溯源

```text
full_chain_papers  10 / 10
figures_bound      37 / 37
tables_bound        0 / 22
fts_hits           75
```

句子链：

```text
sentence → paragraph → section → paper
+ page + bbox
```

图：能按 page 找到 section。  
表：无 page/bbox，无法绑定，标 unresolved。

---

## 5. 修复记录

第一次全量：

```text
82 成功
1 失败：PostgreSQL text fields cannot contain NUL (0x00)
```

修复：

```text
所有文本字段去除 \x00
```

该 PDF 重跑成功：

```text
paper_PMC13598940_e4c38ff5
sections 11
paragraphs 141
sentences 1,100
pages 12
blocks 186
```

---

## 6. 已知缺口

```text
1. 5 篇 PDF 无源文件（结构保留，版面无法重建）
2. PDF tables 无 page/bbox
3. 部分 PDF 图表无法确定 section，标 unresolved
4. PDF 结构来自旧解析结果，不是重新跑 Docling
```
