# 代码增强 RAG：SciPal 平台模块方案与 v1 计划

> 日期：2026-11-12  
> 状态：**取代此前“独立代码 RAG 产品/独立仓库”方案**  
> 定位：SciPal 平台内的“代码库”模块  
> 不复制文献 RAG 主程序，不共用索引

---

## 1. 结论

```text
SciPal = 超级科研平台
  ├─ 平台核心：用户、工作区、库、任务、权限、审计、搜索路由
  ├─ 文献库模块
  ├─ 文档库模块
  ├─ 代码库模块
  └─ 数据/其他模块
```

代码 RAG：

```text
独立数据库 scipal_code
独立 code-rag 服务 / MCP
独立 parser / indexer / search
作为 SciPal 平台的一个库类型与功能扩展
```

不是：

```text
另一个 SciPal
文献 RAG 主程序的复制品
scipal_rebuild 里的一组 code 表
全局共享代码索引
```

---

## 2. 平台抽象：一切皆库

平台层新增统一对象：

```text
libraries
  library_id
  owner_user_id
  workspace_id
  kind          literature / docs / code / data
  name
  visibility    private / workspace / public
  status        creating / indexing / ready / failed
  module_id     literature / docs / code
  config_ref
  created_at
```

用户看到的是：

```text
我的库
  ├─ 文献库
  ├─ 文档库
  └─ 代码库
       ├─ scanpy
       ├─ nf-core/rnaseq
       └─ 我的 pipeline
```

代码库额外配置：

```text
repo_url
ref / commit
language
license
index_status
last_indexed_at
embedding_model
```

敏感信息：

```text
GitHub token 加密存储
只在索引任务中解密
不下发到 DSH
不写日志
```

---

## 3. 平台与模块边界

### 平台负责

```text
用户 / 工作区 / 成员
库注册与 ACL
任务队列与状态
配额 / 审计
搜索路由
UI 壳
```

### code-rag 模块负责

```text
clone / snapshot
AST / parser
code units / edges
embedding
code search / trace
recipe search
```

### 明确禁止

```text
平台 import code-rag 的 parser
code-rag import 文献 RAG 的 corpus
code-rag 直接读写 scipal_core 业务表
文献 RAG 直接读写 scipal_code
跨库外键
```

---

## 4. 运行时形态

```text
DSH / Web UI
    │
    ▼
SciPal 平台 API / 搜索路由
    │
    ├── literature module  -> scipal_core + scipal_rebuild
    ├── docs module        -> scipal_docs
    └── code module        -> code-rag service -> scipal_code
```

code-rag 是独立进程：

```text
code-rag service
  ├─ MCP server
  ├─ index worker
  ├─ search API
  ├─ migrations
  └─ health
```

平台可以管理它的生命周期，但不把 parser 放进主 Flask 进程。

---

## 5. 数据库设计

### 5.1 平台库

`scipal_core`：

```text
libraries
  library_id, owner_user_id, workspace_id
  kind, name, visibility, status
  module_id, config_ref, created_at
```

### 5.2 代码模块库

`scipal_code` / schema `code_rag`：

```text
code_sources
  source_id, library_id, repo_url, license, acl

code_snapshots
  snapshot_id, source_id, library_id
  commit_sha, ref, package_version, created_at

code_files
  file_id, snapshot_id, library_id
  path, language, content_hash, is_generated

code_units
  unit_id, snapshot_id, library_id
  symbol_id, unit_type, text
  start_line, end_line, parent_unit_id

code_edges
  src_unit_id, dst_unit_id, library_id
  relation, source, confidence

code_embeddings
  unit_id, library_id, model, embedding

recipes
  recipe_id, library_id, chart_type, intent
  data_schema, code, style_id, tested
```

强制：

```text
每行都带 library_id
检索先过滤 library_id
不同 library 不共享 HNSW
不同 snapshot 不混检索
```

---

## 6. 搜索设计

### 6.1 平台路由

```text
请求 -> 确定 library_id 列表
     -> code module search
     -> 归一化结果
     -> 标注 library
```

默认：

```text
只搜当前库
```

显式：

```text
“搜我的所有代码库”
```

仍然：

```text
只限当前用户/工作区
不跨租户
不跨文献库
```

### 6.2 代码检索

```text
exact symbol
path
trigram
BM25
vector
RRF
metadata filter
```

优先级：

```text
精确符号 > 路径 > 词法 > 向量
```

版本：

```text
snapshot_id 固定
查询带 ref/commit
不默认用 latest 回答 pinned 问题
```

### 6.3 统一结果契约

```text
library_id
unit_id
symbol
path
start_line
end_line
snippet
score
source
snapshot_id
```

---

## 7. DSH 怎么接

DSH 只看到平台工具，不拿数据库 DSN：

```text
code_search(library_id, query, ...)
code_trace(library_id, unit_id, ...)
code_status(library_id)
bioviz_search(library_id, intent, ...)
```

平台负责：

```text
权限校验
library scope
token 注入
结果裁剪
```

DSH 负责：

```text
决定是否多跳
读实际文件
组织答案
```

不把 code-rag 做成第二个 agent。

---

## 8. AST 解析建库

```text
AST 解析 = 源码 -> 语法树
建库 = 从节点提取 unit + edge
```

解决：

```text
函数/类/process 边界
imports/calls
精确行号
父子结构
```

不解决：

```text
动态绑定
业务语义
代码能否运行
```

流程：

```text
1. 固定 commit
2. parser: ast / tree-sitter / Nextflow parser
3. 遍历节点，提取 function/class/process/config/test
4. 生成 unit（源码范围 + parent）
5. 生成 edge（imports/calls/config）
6. 只对 unit 建 embedding
7. 长函数才滑窗
8. 记录 parser 版本 + edge confidence
```

关键：

```text
AST 定边界
LSP/SCIP 定符号
embedding 找候选
grep 做精确兜底
```

---

## 9. 公开数据怎么用

借标准：

```text
SCIP / LSP / tree-sitter / SPDX / SBOM
```

借评测：

```text
RepoBench / CodeRAG-Bench / CodeSearchNet / SWE-bench / BioCoder
```

借语料：

```text
nf-core / Snakemake workflow catalog / Bioconda
Scanpy / Squidpy / Bioconductor
```

原则：

```text
公开 benchmark 只做 eval，不进生产索引
生产语料固定 commit + license allowlist
不抓全网，不混 generated/vendor
```

---

## 10. 仓库策略

### 现在：monorepo 模块

```text
sciPal/
  modules/
    code_rag/
      parsers/
      indexer/
      search/
      schema.sql
  mcp_server/
    code_server.py
  packages/
    dsh-scipal-code/
```

边界：

```text
modules/code_rag 不 import api_server/routes
不 import 文献 search 实现
独立 DSN
独立测试
```

### 什么时候拆仓库

```text
独立发版
独立团队
license/security 物理隔离
DSH 插件独立分发
```

拆的时候只换位置，不改模块契约。

现在不建议拆：

```text
一人维护
CI/文档/版本同步成本高
```

---

## 11. v1 计划表

| 阶段 | 工作 | 产出 | 人日 | Gate |
|---|---|---|---:|---|
| P0 | 平台 `libraries` + 代码库注册/ACL | core migration + API | 2 | 可创建代码库 |
| P1 | code-rag 服务骨架 + `scipal_code` schema | service + migration | 2 | 独立启动 |
| P2 | AST/tree-sitter + 2 repo 入库 | parser + units/edges | 4 | 可重建 |
| P3 | 混合检索 + 平台路由 | search + router | 3 | 按库隔离 |
| P4 | DSH `scipal-code` MCP | 3 个只读工具 | 2 | DSH 可调用 |
| P5 | UI「我的代码库」 | 创建/状态/搜索 | 3 | 用户可用 |
| P6 | 30 问题评测 | vs DSH baseline | 3 | Go/No-Go |
| P7 | 文档/manifest/失败案例 | handoff | 1 | 可复现 |
| 合计 |  |  | **20** | 约 4 周 |

v1 范围：

```text
2 个外部 repo
1 个 Python
1 个 Nextflow
30 个问题
6 张代码表
3 个只读工具
```

不做：

```text
多语言全支持
多租户大规模
自动改代码
GraphRAG
全文/代码混合全局搜索
```

---

## 12. Gate

```text
G0 代码库可创建、可删除、ACL 正确
G1 两个 repo 可重建，unit/edge 可复现
G2 搜索严格按 library_id 隔离
G3 DSH 可调用 3 个工具
G4 在外部 repo/跨文件/workflow 上优于 DSH 基线
```

G2 失败：

```text
停，不继续做 UI/版本
```

G4 失败：

```text
代码 RAG 只保留为手动工具
不进入平台主路径
```

---

## 13. 风险

| 风险 | 应对 |
|---|---|
| 平台与模块耦合 | 模块契约 + 禁止 import |
| 跨库泄漏 | 每行 library_id + 测试 |
| 索引陈旧 | code_status + snapshot |
| 私有 repo token | 加密 + 最小解密 |
| AST 动态代码 | LSP/测试兜底 |
| 公开数据 license | allowlist + SPDX |
| UI 过重 | v1 只做创建/状态/搜索 |
| 过早拆仓库 | 先 monorepo 模块 |

---

## 14. 结论

```text
代码 RAG 不做独立产品
做成 SciPal 平台里的“代码库”模块
独立数据库 / 独立服务 / 独立搜索
平台统一管理库、权限、任务、路由
DSH 通过 library-aware MCP 工具调用
```

一句话：

```text
独立的是库和服务
统一的是平台入口
不复制主程序
不共用索引
```
