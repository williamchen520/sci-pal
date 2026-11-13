# SciPal Paper 单篇论文分析插件设计 v1

> 日期：2026-11-13  
> 状态：设计，不实现  
> 插件名：`scipal-paper`  
> 目标：围绕一篇论文，做结构、证据、代码、模块、数据流和复刻计划分析  
> 原则：只读分析；下载/执行/复制仍走人工 gate

---

## 1. 一句话

```text
scipal-paper
  = 单篇论文的结构化阅读器
  + 句级证据检索
  + 代码链接/模块分析
  + 数据流重建
  + 复刻计划
```

不是“再做一个总结器”。

---

## 2. 为什么单独做插件

主平台已经做了：

```text
文献 RAG
代码 RAG
章-节-句树
evidence / artifact
plans / approvals / jobs
多租户
```

单篇分析是另一种交互：

```text
不是“搜一堆论文”
而是“把一篇论文读透”
```

需要：

```text
稳定 paper_id
outline
paragraph / sentence 导航
代码链接
模块表
数据流
复刻目标
```

这些不适合塞进通用搜索接口。

---

## 3. 使用场景

### A. 快速读一篇论文

```text
给我这篇的摘要、研究问题、数据、方法、结论、局限
```

### B. 按节读

```text
把 Methods 按小节展开
```

### C. 句级溯源

```text
这句话来自哪一段哪一句
```

### D. 找代码

```text
这篇的代码在哪
license 是什么
能不能入库
```

### E. 解释模块

```text
Figure.1 到 Figure.7 各做什么
数据如何流动
```

### F. 学代码

```text
这个函数怎么用
给我最小调用示例
```

### G. 复刻计划

```text
先复刻 Figure.1 的 QC + Harmony
需要哪些输入、环境、测试
```

---

## 4. 非目标

```text
不自动下载 PDF
不自动 clone/执行 repo
不自动生成整篇论文复刻
不复制无 license/GPL 代码
不替代人工裁决
不把 LLM 总结当论文事实
```

---

## 5. 依赖

### 平台已有

```text
paper_id
papers
sections / paragraphs / sentences
paragraph_embeddings
paragraphs.search_vector
sentences.search_vector
evidence / artifact
code RAG providers
libraries / workspace ACL
```

### 必须先补

```text
sections 表或 section_path 完整性
sentences 实际入库
sentence FTS 可查
paper_sources（HTML/PDF/JATS）
paper_code_links
```

### 语言解析

```text
Python  parser 已有
R       parser 未实现
Rmd     parser 未实现
Nextflow 已有
```

插件必须显式返回：

```text
parser_supported=false
```

不能假装模块分析成功。

---

## 6. 架构

```text
DSH / Web
   │
   ▼
scipal-paper plugin
   ├── paper resolver
   ├── outline service
   ├── evidence service
   ├── code-link service
   ├── module mapper
   ├── data-flow mapper
   └── replication planner
   │
   ▼
SciPal APIs
   ├── papers
   ├── paragraphs / sentences
   ├── evidence search
   ├── code RAG
   └── artifacts
```

插件不直接访问 DB；只调平台 API。

---

## 7. 插件接口

### 7.1 paper_resolve

```json
paper_resolve({"doi": "10.1038/..."})
```

返回：

```json
{
  "paper_id": "paper_...",
  "title": "...",
  "doi": "...",
  "sources": ["html", "pdf"],
  "has_code": true,
  "status": "indexed"
}
```

### 7.2 paper_outline

```text
paper_outline(paper_id)
```

返回：

```json
{
  "paper_id": "...",
  "title": "...",
  "sections": [
    {
      "section_id": "sec_...",
      "title": "Results",
      "level": 1,
      "paragraph_count": 29,
      "first_para_id": "paper_..._para_00001"
    }
  ]
}
```

### 7.3 paper_section

```text
paper_section(paper_id, section_id)
```

返回：

```text
section
paragraphs
paragraph_count
```

### 7.4 paper_paragraph

```text
paper_paragraph(paper_id, para_id)
```

返回：

```text
paragraph text
section_path
sentence_ids
neighbors（前后段）
```

### 7.5 paper_first_paragraph

```text
paper_first_paragraph(paper_id, section="")
```

允许：

```text
section=""            解析顺序第一段
section="Abstract"    摘要第一段
section="Introduction" 正文第一段
```

明确返回：

```text
order_by=sequence
section_path
```

避免“第一段”歧义。

### 7.6 paper_sentences

```text
paper_sentences(para_id)
```

返回：

```text
sentence_id
sequence
text
char_start / char_end
```

### 7.7 paper_evidence

```text
paper_evidence(paper_id, query, top_k=8)
```

只在该 paper 内检索：

```text
paragraph vector recall
  -> sentence FTS
  -> rerank
```

返回：

```text
sentence_id
para_id
section_path
text
score
```

### 7.8 paper_code_links

```text
paper_code_links(paper_id)
```

返回：

```text
repo_url
repo_type
commit
license
confidence
evidence_sentence_id
status
```

### 7.9 paper_code_status

```text
paper_code_status(paper_id)
```

返回：

```text
library_id
snapshot
parser_supported
language
units
status
```

### 7.10 paper_module_map

```text
paper_module_map(paper_id)
```

返回：

```text
module
source_file
start_line / end_line
purpose
inputs
outputs
depends_on
confidence
```

### 7.11 paper_data_flow

```text
paper_data_flow(paper_id)
```

返回：

```text
nodes
edges
confidence
```

### 7.12 paper_replication_plan

```text
paper_replication_plan(paper_id, target)
```

返回：

```text
target
scope
data
environment
commands
tests
risks
status=planned
```

不执行。

### 7.13 paper_analysis_export

```text
paper_analysis_export(paper_id)
```

导出：

```text
analysis.json
```

---

## 8. 单篇分析流程

```text
1 resolve paper
2 get outline
3 read abstract / results / methods
4 sentence-level evidence
5 extract code links
6 check code ingest/parser
7 module map
8 data flow
9 replication plan
10 export
```

每一步可单独调用，不要求一次完成。

---

## 9. 输出结构 `PaperAnalysis`

```json
{
  "paper_id": "...",
  "title": "...",
  "doi": "...",
  "sources": [],
  "outline": [],
  "key_points": [
    {
      "text": "...",
      "evidence": ["sentence_id"]
    }
  ],
  "methods": [],
  "code": {
    "repo_url": "",
    "commit": "",
    "license": "",
    "library_id": "",
    "parser_supported": false
  },
  "modules": [],
  "data_flow": {
    "nodes": [],
    "edges": []
  },
  "replication": {
    "target": "",
    "status": "planned",
    "risks": []
  },
  "provenance": {
    "source_hash": "",
    "parser": "",
    "parser_version": ""
  }
}
```

---

## 10. 证据规则

每条 `key_point` 必须带：

```text
sentence_id
para_id
section_path
paper_id
```

没有 evidence 的句子：

```text
label=unsupported
```

不得进入 `key_points` 的“已证”部分。

模块/数据流：

```text
explicit   论文/代码中明确写出的
inferred   从调用关系推断的
unknown   无法判断
```

必须标注 confidence。

---

## 11. 代码分析规则

### 有链接

```text
验证 URL
读取 license
固定 commit
判断 parser
```

### 无链接

```text
返回 no_code_found
不猜
```

### R / 混合

```text
parser_supported=false
module_map 只能文件级/人工说明
```

不能声称函数级模块。

### 许可证

```text
MIT/Apache/BSD   可引用，保留声明
GPL/AGPL         只解释，不复制
无 license       只解释，不复制
```

---

## 12. 数据流重建

输入：

```text
code units
imports
call edges
script order
README
paper methods
```

输出：

```text
node: input / process / output / figure
edge: produces / consumes / calls / writes
```

规则：

```text
静态可证 -> explicit
推断     -> inferred
动态调用 -> unknown
```

不能把 R/Python 动态调用画成确定边。

---

## 13. 复刻计划

只做计划，不执行。

```text
target
  Figure.1 QC + Harmony
scope
  one script / one function
inputs
  counts matrix / metadata
environment
  R version / packages
commands
tests
  expected clusters / marker genes / runtime
risks
  missing data / package version / GPU
```

状态：

```text
planned
approved
running
partial
failed
verified
```

没有测试：

```text
不能标记 verified
```

---

## 14. 服务端 API

插件需要的只读 API：

```text
GET /api/papers/<paper_id>/outline
GET /api/papers/<paper_id>/sections/<section_id>
GET /api/papers/<paper_id>/paragraphs
GET /api/papers/<paper_id>/paragraphs/first
GET /api/paragraphs/<para_id>/sentences
POST /api/papers/<paper_id>/evidence
GET /api/papers/<paper_id>/code-links
GET /api/papers/<paper_id>/code-status
POST /api/papers/<paper_id>/module-map
POST /api/papers/<paper_id>/data-flow
POST /api/papers/<paper_id>/replication-plan
GET /api/papers/<paper_id>/analysis/export
```

---

## 15. 权限与租户

```text
paper 必须属于当前 workspace
或 main library + 可读
```

私有库：

```text
A 不能分析 B 的 paper
```

主库：

```text
只读
```

导出：

```text
不包含其他租户内容
```

---

## 16. 缓存与性能

缓存键：

```text
paper_id
workspace_id
source_hash
parser_version
```

缓存对象：

```text
outline
section
paragraph list
module map
data flow
```

不缓存：

```text
跨租户结果
未授权论文
```

---

## 17. 失败模式

```text
paper not found
PDF not parsed
sentences missing
no code link
repo unreachable
license unknown
R parser unsupported
module map partial
data flow partial
```

必须返回：

```text
status
partial
warnings
```

不能 200 空结果。

---

## 18. 验收指标

```text
outline_accuracy
section_paragraph_coverage
sentence_citation_coverage
evidence_precision
code_link_precision
module_coverage
data_flow_edge_precision
export_completeness
latency
```

最小验收：

```text
outline 与原文标题一致
first paragraph 可定位
evidence 有 sentence_id
code link 有 license/commit
module map 标 confidence
无 evidence 的结论不标 supported
```

---

## 19. 分阶段

| 阶段 | 工作 | 人日 |
|---|---|---:|
| P0 | paper outline / paragraphs / first paragraph | 2 |
| P1 | sentence tree + evidence | 3 |
| P2 | code links + status | 2 |
| P3 | module map | 3 |
| P4 | data flow | 3 |
| P5 | replication plan | 2 |
| P6 | export + UI/MCP | 2 |
| 合计 |  | **17 人日** |

前置：

```text
sentences 必须真的有数据
R parser 支持
```

---

## 20. 不做

```text
不自动下载
不自动执行
不复制 GPL/无 license 代码
不生成整篇复刻
不把 inferred 当 explicit
不跳过 evidence
```

---

## 21. 与现有模块关系

```text
scipal-search     论文检索
scipal-code       代码检索/上下文
scipal-paper      单篇论文分析
DSH               规划/生成/汇总
Control Plane     下载/入库/任务/审计
```

`scipal-paper` 不替代任何一个，只做单篇的“结构化阅读层”。

---

## 22. 结论

```text
单篇论文分析 = 结构 + 证据 + 代码 + 模块 + 数据流 + 复刻计划
```

没有章-节-句树，插件只能做摘要。  
没有 sentence evidence，插件只能给“看起来像”的结论。  
没有代码 parser，插件只能解释文件，不能解释模块。

所以先完成：

```text
sentence tree
sentence FTS
R parser
```

再做 `scipal-paper`。
