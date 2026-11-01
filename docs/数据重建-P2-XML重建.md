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

## 4. 全量

全量 2,820 篇正在后台重建：

```text
per-paper commit
失败只回滚该篇
失败文件进 failures 列表
```

完成后输出：

```text
totals
failure_count
failures
```

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

## 6. 已知缺口

```text
1. 398 篇 XML 源文件缺失
2. 部分 fig/table 在 <sec> 外，placement_source=unresolved
3. XML 无 PDF 坐标，coordinate_source=xml-unavailable
```
