# 代码增强 RAG v1 计划表

> **已废弃（2026-11-12）**：由 [计划-代码增强RAG-平台模块-v1](计划-代码增强RAG-平台模块-v1.md) 取代；仅保留历史讨论。


> 日期：2026-11-12  
> 状态：计划，不写实现  
> 目标：一个外部 Python repo + 一个 Nextflow repo + 30 个真实问题  
> 边界：独立 `scipal_code`，通过 MCP 挂 DSH，不动主程序

---

## 1. 范围

### v1 做

```text
1 个 Python 外部 repo
1 个 Nextflow 外部 repo
30 个代码问题
6 张核心表
3 个只读 MCP 工具
DSH 基线对比
```

### v1 不做

```text
当前 SciPal 仓库索引
全语言支持
GraphRAG / 多 repo 大平台
自动改代码
自动执行任意 repo
PaperQA2 / 系统层
```

---

## 2. 计划表

| 阶段 | 工作 | 产出 | 人日 | Gate |
|---|---|---|---:|---|
| P0 | 选 repo、license、commit、30 问题 | `scope.md` + gold | 2 | 30 题可回答 |
| P1 | 扩展 `scipal_code` 6 张表 | schema + migration | 1 | 表/索引可建 |
| P2 | AST/tree-sitter 解析与入库 | parser + units + edges | 4 | 两 repo 可重建 |
| P3 | 混合检索与过滤 | search CLI | 3 | 30 题可跑 |
| P4 | `scipal-code` MCP 工具 | 3 个只读工具 | 2 | DSH 可调用 |
| P5 | 与 DSH 基线对比 | eval 报告 | 3 | Go/No-Go |
| P6 | 文档、manifest、失败案例 | handoff | 1 | 可复现 |
| 合计 |  |  | **16** | 约 3 周 |

---

## 3. 数据源

### Python repo

```text
候选：scverse/scanpy
license：BSD-3-Clause
固定 release/tag
只索引源码 + 文档 + 测试
```

### Nextflow repo

```text
候选：nf-core/rnaseq 或 nf-core/modules
license：MIT（以 repo 实际 LICENSE 为准）
固定 release/tag
索引 process/module/workflow/config/tests
```

### 公开评测

```text
RepoBench        检索/补全任务设计
CodeRAG-Bench    检索增强代码生成口径
BioCoder         生信代码 sanity check
```

原则：

```text
公开 benchmark 不做生产索引
只做方法对照，防止泄漏
```

---

## 4. 30 个问题

```text
符号定位          10
调用链/数据流      8
workflow/config    6
版本/API           3
报错/测试          3
```

例子：

```text
plot_umap 在哪定义？
sc.pl.umap 的 color 参数怎么传？
FASTQC 的 reads 从哪个 channel 来？
nextflow.config 里 cpus 覆盖了哪个 process？
sample sheet 在哪个 process 被解析？
这个旧版本 API 现在叫什么？
这个报错来自哪个 test？
```

---

## 5. 数据库 v1

复用 `scipal_code`，新增：

```text
code_sources
code_snapshots
code_files
code_units
code_edges
code_embeddings
```

已有：

```text
recipes
styles
```

字段最少集：

```text
snapshot_id, repo_id, commit
file_id, path, language, content_hash
unit_id, symbol_id, unit_type
text, start_line, end_line, parent_unit_id
edge: src, dst, relation, source, confidence
embedding: unit_id, model, vector
```

规则：

```text
每个 unit 必须带 snapshot_id
不同 commit 不混检索
图边来自 parser/LSP，不让 LLM 猜
```

---

## 6. AST 解析建库是什么

### 6.1 一句话

```text
AST 解析 = 把源码变成语法树
建库 = 从树节点提取“可检索单元”和“关系”
```

它解决：

```text
函数/类边界
process/module 边界
imports/calls 关系
精确行号
父级/子级
```

它不解决：

```text
这段代码的业务含义
跨动态调用的真实绑定
代码是否可运行
```

---

### 6.2 普通文本切分 vs AST

| 方式 | 得到什么 | 问题 |
|---|---|---|
| 固定 500 词 | 文本块 | 切断函数/调用 |
| 正则 | 近似结构 | 注释/嵌套/多语言易错 |
| AST | 语法节点 + 范围 | 需要 parser，动态语义仍缺 |
| LSP/SCIP | 符号解析 + 引用 | 需要语言服务器/构建 |

正确组合：

```text
AST 定边界
LSP/SCIP 定符号绑定
embedding 做语义候选
grep 做精确兜底
```

---

### 6.3 Python 例子

源码：

```python
def plot_umap(adata, color="cell_type"):
    sc.pl.umap(adata, color=color)
```

AST 大致是：

```text
Module
  FunctionDef name=plot_umap
    arguments: adata, color
    Expr
      Call
        Attribute sc.pl.umap
        keyword color
```

建库结果：

```text
unit: plot_umap
  type: function
  start_line: 1
  end_line: 2
  parent: module

edge:
  plot_umap -> sc.pl.umap
  relation: calls
  source: ast_heuristic
```

注意：

```text
sc.pl.umap 是否真的绑定到 scanpy.pl.umap
AST 本身不知道
要靠 import 解析 / LSP / 运行时
```

所以边要标：

```text
source=ast
confidence=high|medium|low
```

---

### 6.4 Nextflow 例子

```groovy
process FASTQC {
  input:
  path reads
  script:
  """
  fastqc ${reads}
  """
}
```

解析结果：

```text
workflow_unit: FASTQC
  kind: process
  inputs: [reads]
  script: fastqc ${reads}
  parent: workflow/module

edges:
  FASTQC -> fastqc
  relation: calls
  source: nextflow_parser
```

配置：

```groovy
process {
  withName: FASTQC {
    cpus = 8
  }
}
```

建边：

```text
config_key cpus -> FASTQC
relation: config_override
```

这类接线是 grep 很难稳定回答的，也是代码图的价值。

---

### 6.5 建库流程

```text
1. clone / 固定 commit
2. 按文件 hash 判断增量
3. 选择 parser
   Python: ast + asttokens / tree-sitter
   Nextflow: tree-sitter 或 Nextflow parser
   WDL: WDL parser
   YAML/JSON: 配置解析
4. 遍历语法树
   提取 function/class/process/config/test
5. 生成 unit
   text = 源码 span
   start/end line
   parent_unit_id
6. 生成 edge
   imports/calls/references/config/process
7. 写 code_units + code_edges
8. 只对 unit 建 embedding
9. 长函数才滑窗
10. 记录 parser/version/confidence
```

---

### 6.6 常见误区

```text
把 AST 当“理解代码”
把每个 AST 节点都建 unit
把注释/空格丢了导致无法回读
不记录 commit
不标 edge 来源/置信度
动态 import 当成确定调用
```

正确：

```text
AST 只提供结构
语义靠检索 + LSP + 测试
```

---

## 7. 搜索引擎 + DSH

```text
DSH
  -> 判断：当前仓库还是外部代码
  -> 当前仓库：grep/read/LSP
  -> 外部代码：scipal-code MCP

scipal-code
  -> code_search
  -> code_trace
  -> code_status
  -> bioviz_search
```

检索：

```text
exact symbol
path
trigram/BM25
vector
RRF
metadata filter
```

DSH：

```text
决定多跳
读实际文件
组织答案
```

RAG 不跑自己的 agent loop。

---

## 8. 评测

基线：

```text
DSH grep/read/LSP
```

实验：

```text
code_search
code_search + code_trace
```

指标：

```text
file Recall@k
symbol Recall@k
dependency Recall
answer correctness
citation correctness
p95 latency
tool calls
```

Go 条件：

```text
在外部 repo / 跨文件 / workflow 接线上
明显优于 DSH 基线
且不牺牲精确符号定位
```

---

## 9. 风险

| 风险 | 应对 |
|---|---|
| AST 解析不了动态代码 | LSP/测试兜底，边标置信度 |
| Nextflow 语法变动 | 固定 parser 版本，测试样本 |
| 版本混用 | snapshot_id 强制过滤 |
| 公开数据泄漏 | benchmark 不入生产索引 |
| license 不清 | allowlist + SPDX |
| 索引陈旧 | code_status + last_verified |
| 图爆炸 | 1–3 跳，节点上限 |
| 自动改坏代码 | 只读工具，patch 需人工/测试 |

---

## 10. 结论

```text
AST 是“切得准、连得上”的基础
不是“理解代码”的魔法
```

v1 只做：

```text
两个 repo
30 个问题
6 张表
3 个只读工具
```

先证明“结构化检索 + 图”比 DSH grep 在外部代码上有增量，再扩多语言/多 repo。
