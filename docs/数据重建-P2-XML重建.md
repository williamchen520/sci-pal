# P2 XML 重建

> 日期：2026-11-01  
> 目标库：`scipal_v2`  
> 范围：仅 XML/JATS；不重建 PDF，不写 page/bbox。

---

## 1. 源数据

```text
XML 文件：2,820
SQLite XML papers：3,218
源文件缺失：398
```

这 398 篇只有 SQLite 元数据，没有可重放的 XML 文件。  
P2 只重建有源文件的 2,820 篇；缺口单独列出，不伪造。

---

## 2. 实现

```text
build_db/jats_parser.py
  保留 <sec> 嵌套
  fig/table 记录父 section_id 与 XPath

build_db/pg_v2_import_xml.py
  XML → scipal_v2
  papers/documents/source_nodes/sections/paragraphs/sentences/figures/tables

scripts/check_v2_trace.py
  10 篇链、图表绑定、句子 FTS 检查
```

### source_nodes

```text
paper
  └─ section (parent_node_id)
       └─ paragraph
            └─ sentence
       └─ figure / table
```

每个节点带：

```text
source_path（XML XPath）
native_json（精简原生节点）
```

### 坐标

```text
page = NULL
bbox = NULL
coordinate_source = 'xml-unavailable'
```

不伪造 PDF 坐标。

### 图表

```text
<fig>/<table-wrap> 在 <sec> 内 → section_id
placement_source = 'jats-parent'

不在 <sec> 内 → section_id = NULL
placement_source = 'unresolved'
```

---

## 3. 10 篇 pilot

导入 10 篇：

```text
papers       10
sections    127
paragraphs  206
sentences   1,347
figures      42
tables        5
```

溯源检查：

```text
full_chain_papers  10 / 10
figures_bound      54 / 56
tables_bound        9 / 11
fts_hits           7
```

说明：

```text
10/10 句子链完整
图 2 个、表 2 个无法从 JATS 父节点确定 section
标 unresolved，不强行绑定
```

---

## 4. 全量完成

```text
attempted       2,820
failures            0
```

总计：

```text
papers        2,820
sections     58,395
paragraphs  123,038
sentences   653,831
figures      11,688
tables        4,770
source_nodes 854,542
```

398 篇 metadata-only 已单独导入。

### 与旧库同源对比

只比较有源文件的 2,820 篇：

| 表 | 旧 SQLite | v2 | 差异 |
|---|---:|---:|---:|
| sections | 58,372 | 58,395 | +23 |
| paragraphs | 123,038 | 123,038 | 0 |
| sentences | 653,831 | 653,831 | 0 |
| figures | 11,683 | 11,688 | +5 |
| tables | 4,767 | 4,770 | +3 |

结论：

```text
同源 XML 的段落/句子零丢失
章节/图表少量增加，来自新的父节点采集
```

差异主要来自 398 篇无源文件论文，旧库有、v2 只能保留元数据。

### 图表绑定

```text
figures 11,688
  bound 6,467
  unresolved 5,221

tables 4,770
  bound 2,930
  unresolved 1,840
```

unresolved 主要是 JATS `<floats-group>` 里的图/表，没有 `<sec>` 父节点；不强行绑定。

---

## 5. 验收

```text
sentence → paragraph → section → paper
source_xpath 可回 XML
figure/table → section
sentences.search_vector 可检索
page/bbox 全 NULL 且标注 xml-unavailable
```

---

## 6. 398 篇只有元数据

这 398 篇没有全文源文件，不能重建结构。

处理：

```text
papers 表保留
fulltext_status = 'metadata_only'
source_flags = {"fulltext": "missing", "has_xml": false}
不创建 documents / source_nodes / sections / sentences
不伪造全文
```

查询：

```sql
SELECT paper_id, title, fulltext_status
FROM papers
WHERE fulltext_status = 'metadata_only';
```

## 7. 已知缺口

```text
1. 398 篇只有元数据，没有全文
2. 部分 fig/table 在 <sec> 外，placement_source=unresolved
3. XML 无 PDF 坐标，coordinate_source=xml-unavailable
```
