# Schema v2：按源类型建模设计

> 日期：2026-11-01  
> 状态：设计稿，不执行迁移  
> 目标：保留 XML / PDF 各自的数据特征，不强行压成同一种扁平结构。  
> 原则：共同核心用于检索，源特征用于溯源；**不伪造 Page/BBox，不丢 XPath/原生树**。

---

## 1. 设计目标

```text
1. XML 保留原生 JATS 树与 XPath
2. PDF 保留 page / bbox / 版面块
3. 共同核心支持 paper → section → paragraph → sentence
4. figure/table 能绑定 section/paragraph
5. 句子级 FTS
6. 任何来源都能回答“这句话从哪来”
```

非目标：

```text
不把 XML 强行补成 PDF 坐标
不把 PDF 强行补成 JATS XPath
不要求两类数据字段完全一致
```

---

## 2. 总体结构

```text
documents                 源文件与校验
  └─ source_nodes         原生树节点（XML XPath / PDF block）
  └─ papers              论文核心身份
       ├─ sections       共同章节
       ├─ paragraphs     共同段落
       ├─ sentences      共同句子 + FTS
       ├─ figures        图表 + 可选坐标 + 绑定
       ├─ tables         表格 + 可选坐标 + 绑定
       └─ pdf_pages      PDF 页级版面（仅 PDF）
```

共同核心只放检索与关系统一需要的字段；  
`source_*` 与 `pdf_*` 保留来源特征。

---

## 3. documents

一行一个源文件。

```sql
CREATE TABLE documents (
    document_id     TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml','pdf')),
    source_path     TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    parser          TEXT NOT NULL,
    parser_version  TEXT,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (paper_id, source_type, sha256)
);
```

用途：

```text
同一 paper 可以同时有 XML 和 PDF
重跑时用 sha256 判断是否重复
source_path 只存相对项目根路径
```

---

## 4. papers

论文身份与展示元数据，尽量保持现状。

```sql
CREATE TABLE papers (
    paper_id        TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL DEFAULT 'ws_default',
    title           TEXT,
    authors         TEXT,
    journal         TEXT,
    year            INTEGER,
    doi             TEXT,
    abstract        TEXT,
    parse_status    TEXT,
    source_flags    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`source_flags` 示例：

```json
{"has_xml": true, "has_pdf": false, "coordinate_source": "xml-unavailable"}
```

不把“有没有 PDF 坐标”塞进多个布尔列；用 JSONB 保留扩展。

---

## 5. source_nodes：原生树

一行一个原生节点。

```sql
CREATE TABLE source_nodes (
    node_id         TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    parent_node_id  TEXT REFERENCES source_nodes(node_id),
    node_type       TEXT NOT NULL,       -- paper/section/paragraph/sentence/figure/table/page/block
    source_path     TEXT,                -- XML XPath 或 PDF JSON pointer
    source_order    INTEGER,
    native_json     JSONB,               -- 该节点的原生子树/版面块
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_source_nodes_paper ON source_nodes(paper_id);
CREATE INDEX idx_source_nodes_parent ON source_nodes(parent_node_id);
```

规则：

```text
XML：node_type=section/paragraph/sentence/figure/table
     source_path=/article/body/sec[2]/p[3]
     native_json=该 JATS 节点的精简 JSON

PDF：node_type=page/block
     source_path=/pages/3/blocks/7
     native_json={page,bbox,block_type}
```

---

## 6. sections

共同章节表。

```sql
CREATE TABLE sections (
    section_id      TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    parent_id       TEXT REFERENCES sections(section_id),
    level           INTEGER NOT NULL,
    seq             INTEGER NOT NULL,
    title           TEXT,
    path            TEXT,              -- "1. Introduction / 1.1 ..."
    depth           INTEGER,
    source_node_id  TEXT REFERENCES source_nodes(node_id),
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml','pdf')),
    page            INTEGER,            -- PDF only
    bbox            TEXT,               -- PDF only
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (coordinate_source IN ('pdf','xml-unavailable','unavailable'))
);

CREATE INDEX idx_sections_paper ON sections(paper_id, seq);
CREATE INDEX idx_sections_parent ON sections(parent_id);
```

约束：

```text
XML：page/bbox = NULL，coordinate_source='xml-unavailable'
PDF：有 page/bbox 时 coordinate_source='pdf'
```

不为了统一而给 XML 填假页码。

---

## 7. paragraphs

```sql
CREATE TABLE paragraphs (
    para_id         TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    section_id      TEXT REFERENCES sections(section_id),
    seq             INTEGER NOT NULL,
    text            TEXT NOT NULL,
    source_node_id  TEXT REFERENCES source_nodes(node_id),
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml','pdf')),
    page            INTEGER,
    bbox            TEXT,
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
);
```

---

## 8. sentences

```sql
CREATE TABLE sentences (
    sentence_id     TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    para_id         TEXT NOT NULL REFERENCES paragraphs(para_id),
    section_id      TEXT REFERENCES sections(section_id),
    seq             INTEGER NOT NULL,
    text            TEXT NOT NULL,
    char_start      INTEGER,
    char_end        INTEGER,
    source_node_id  TEXT REFERENCES source_nodes(node_id),
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml','pdf')),
    page            INTEGER,
    bbox            TEXT,
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable',
    search_vector   tsvector GENERATED ALWAYS AS
        (to_tsvector('english', coalesce(text,''))) STORED
);

CREATE INDEX idx_sentences_paper ON sentences(paper_id);
CREATE INDEX idx_sentences_para ON sentences(para_id);
CREATE INDEX idx_sentences_search ON sentences USING GIN (search_vector);
```

说明：

```text
FTS 直接建在 sentence 上
XML 返回 source_node_id → XPath
PDF 返回 page/bbox
```

---

## 9. figures / tables

### figures

```sql
CREATE TABLE figures (
    fig_id          TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    section_id      TEXT REFERENCES sections(section_id),
    para_id         TEXT REFERENCES paragraphs(para_id),
    fig_number      TEXT,
    caption         TEXT,
    file_path       TEXT,
    source_node_id  TEXT REFERENCES source_nodes(node_id),
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml','pdf')),
    page            INTEGER,
    bbox            TEXT,
    placement_source TEXT NOT NULL
        CHECK (placement_source IN ('jats-parent','pdf-caption','pdf-region','unresolved')),
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
);

CREATE INDEX idx_figures_paper ON figures(paper_id);
CREATE INDEX idx_figures_section ON figures(section_id);
CREATE INDEX idx_figures_para ON figures(para_id);
```

### tables

与 figures 同构：

```text
table_id, paper_id, section_id, para_id,
table_number, caption, markdown,
source_node_id, source_type,
page, bbox, placement_source, coordinate_source
```

绑定规则：

```text
XML：
  如果 <fig>/<table> 在 <sec> 内 → section_id 直接来自父 sec
  para_id 可空；placement_source='jats-parent'
  有 context/引用时可进一步绑定到段落

PDF：
  caption + 区域 → section_id/para_id
  page + bbox 必须保留
  placement_source='pdf-caption' 或 'pdf-region'
```

无法绑定：

```text
section_id = NULL
placement_source='unresolved'
不伪造
```

---

## 10. pdf_pages / pdf_blocks

仅 PDF 使用。

```sql
CREATE TABLE pdf_pages (
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    page_no         INTEGER NOT NULL,
    width           DOUBLE PRECISION,
    height          DOUBLE PRECISION,
    text            TEXT,
    layout_json     JSONB,
    PRIMARY KEY (paper_id, page_no)
);

CREATE TABLE pdf_blocks (
    block_id        TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
    page_no         INTEGER NOT NULL,
    bbox            TEXT NOT NULL,
    block_type      TEXT,
    text            TEXT,
    parent_block_id TEXT,
    source_order    INTEGER,
    FOREIGN KEY (paper_id, page_no) REFERENCES pdf_pages(paper_id, page_no)
);
```

XML 论文不建这些行；查询时按 `source_type` 选择。

---

## 11. FTS 查询策略

### XML

```sql
SELECT s.sentence_id, s.text, sn.source_path
FROM sentences s
JOIN source_nodes sn ON sn.node_id = s.source_node_id
WHERE s.search_vector @@ websearch_to_tsquery('english', %s)
  AND s.source_type = 'xml'
ORDER BY ts_rank(s.search_vector, websearch_to_tsquery('english', %s)) DESC;
```

返回：

```text
source_path（XPath）
无 page/bbox
```

### PDF

```sql
SELECT sentence_id, text, page, bbox
FROM sentences
WHERE search_vector @@ websearch_to_tsquery('english', %s)
  AND source_type = 'pdf'
ORDER BY ts_rank(...) DESC;
```

返回：

```text
page + bbox
```

### 聚合

```text
句子级检索
→ 按 para_id 聚合成段落
→ 按 paper_id 聚合成论文
```

不把 sentence FTS 降级回 paragraph FTS。

---

## 12. 重建流程

```text
P0 备份旧库；新库 scipal_v2
P1 建 schema v2
P2 重建 XML 2,820 篇：
     documents/source_nodes/sections/paragraphs/sentences
     figures/tables section_id
P3 重建 PDF 约 83 篇：
     pdf_pages/pdf_blocks
     page/bbox
     figure/table 区域绑定
P4 句子级 FTS 索引
P5 10 篇 XML + 10 篇 PDF 溯源测试
P6 对比旧库；确认后切换
```

旧库 `data/research.db` 和 `scipal_bench` 不动。

---

## 13. 验收

### XML 10 篇

```text
sentence → paragraph → section → paper
source_xpath 可回原 XML
figure/table → section
page/bbox 为空且标注 xml-unavailable
```

### PDF 10 篇

```text
sentence → paragraph → section → paper
page/bbox 可回原 PDF
figure/table 有 section_id 或明确 unresolved
```

### 数据

```text
行数/checksum 一致
无伪造坐标
无丢失 XPath
```

---

## 14. 未决问题

```text
1. PDF figure/table 的 section 绑定阈值
2. XML figure 在 sec 外时的归属规则
3. 同一 paper 同时有 XML+PDF 时，sentence 是否双份
4. 坐标单位：pt / px
5. workspace_id 是否进入 source_nodes
```

建议同一 paper 双源时：

```text
共同核心只保留一套 sentence
source_nodes 保留两套来源引用
sentence 上 source_node_id 指向主来源
```

---

## 15. P1 实施状态

```text
scipal_v2 已创建（空库）
10 张表
28 个外键
sentences.search_vector = tsvector
所有表 0 行
旧库未动
```

建库脚本：

```text
build_db/postgres_schema_v2.sql
scripts/create_pg_v2.py
```

## 16. 结论

```text
XML 按树重建
PDF 按页/版面重建
共同核心只负责检索与关系
源特征不丢
坐标不伪造
图表绑定可追溯
FTS 到句子级
```
