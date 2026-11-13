# SciPal Paper → Code → Replication 主动科研工作流 v1

> 日期：2026-11-13  
> 状态：设计，不实现  
> 目标：让多智能体具备“发现—建议—入库—抽取—生成—验证”的主动能力  
> 原则：主动发现可以自动，下载/执行/发布必须有人类 gate

---

## 1. 一句话

```text
论文发现
  -> 人工确认
  -> PDF 入库
  -> 文献 RAG 总结
  -> 抽取代码链接
  -> 人工确认 repo
  -> code RAG 入库
  -> exemplar 抽取
  -> 大模型按需生成/适配
  -> 沙箱测试
  -> 人审查
  -> 复刻/学习/另写
```

不是“整篇论文喂模型”，也不是“自动吞下所有生信代码”。

---

## 2. 主动能力的边界

### 可以自动

```text
按方向监控新论文
去重
候选打分
生成摘要
生成入库建议
排队
生成 repo 候选
生成复刻计划
夜间处理已批准候选
```

### 必须人工

```text
下载付费/受限 PDF
下载并执行外部 repo
批准代码入库范围
批准代码生成范围
批准复刻目标
接受生成代码
发布/导出
```

```text
主动 = 发现 + 建议 + 排队
不等于未授权下载/执行/发布
```

---

## 3. 使用场景

### A. 领域监控

```text
关注 scRNA / spatial / workflow 方向
  -> 每周/每日检索
  -> 新论文候选
  -> 人去重/确认
  -> 入库
```

### B. 读到一篇论文

```text
标题/DOI
  -> 找 PDF
  -> 入库
  -> 总结要点/方法/数据/局限
  -> 找代码
```

### C. 学代码

```text
从论文代码库抽一个函数
  -> 解释
  -> 调用示例
  -> 不生成新代码
```

### D. 复刻一部分

```text
目标：复刻一个函数/一步分析
  -> exemplar
  -> 生成独立实现
  -> 测试
```

### E. 学思路另写

```text
参考方法
  -> 按我们项目接口重写
  -> 标 inspired_by
```

### F. 整项目复刻尝试

```text
论文 + repo + 数据 + 环境
  -> 容器
  -> 跑通一个最小目标
  -> 记录 partial/failed/verified
```

---

## 4. 总体架构

```text
DSH
  发现 / 计划 / 解释 / 生成
      │
      ▼
SciPal Control Plane
  plans / approvals / jobs / runs
  evidence / artifacts / adjudication
      │
      ├── literature RAG (scipal_rebuild)
      ├── code RAG (scipal_code)
      ├── docs RAG (scipal_docs)
      └── future RAG providers
      │
      ▼
Workers
  acquisition / parse / ingest / exemplar / synthesis / sandbox
```

---

## 5. 端到端流程

```text
1. discovery
2. human approve acquisition
3. acquire PDF
4. parse + literature ingest
5. analyze paper
6. extract repo candidates
7. human approve repo
8. code ingest
9. exemplar extraction
10. human approve synthesis scope
11. code generation
12. compile + tests
13. human review
14. optional replication attempt
15. evidence / artifact / seal
```

---

## 6. 阶段一：发现

### 输入

```text
主题
关键词
期刊
作者
预印本源
```

### 输出

```text
paper candidate
  title
  doi / pmid / pmcid
  source
  published_at
  abstract
  license / open_access
  score
  dedupe_key
```

### 规则

```text
按 DOI/PMCID 去重
保留来源
不自动下载闭源 PDF
候选只进入队列
```

### 现有能力

```text
scipal-search search_online
watch_profiles / watch_run
```

---

## 7. 阶段二：PDF 获取与入库

### 获取方式

```text
A. PMC 开放获取自动下载
B. 人工上传 PDF
C. 人工粘贴合法下载链接
```

### 入库

```text
PDF
  -> parse
  -> sections
  -> paragraphs
  -> sentences
  -> embeddings
  -> scipal_rebuild
```

### 必须记录

```text
paper_id
doi
pmcid
source_url
license
downloaded_by
downloaded_at
file_hash
```

### Gate

```text
下载前：人确认
入库后：人可查看失败/重复
```

---

## 8. 阶段三：文献分析

输出固定结构：

```text
研究问题
数据
方法
关键步骤
主要结论
局限性
代码可用性
数据可用性
```

每条结论必须带：

```text
paper_id
section
paragraph_id
sentence_id
```

### 代码链接抽取

候选来源：

```text
Code Availability
Data Availability
Methods
Supplementary
GitHub / GitLab / Zenodo / Bitbucket
```

候选结构：

```text
repo_url
repo_type
paper_id
evidence_sentence
confidence
```

### 防幻觉

```text
URL 必须可访问
GitHub API 必须存在
license 必须读取
commit 必须固定
```

---

## 9. 阶段四：代码获取

### 有链接

```text
repo_url
  -> validate
  -> license
  -> default branch / commit
  -> archive
  -> code RAG ingest
```

### 无链接

```text
A. 人上传 zip
B. 人粘贴 URL
C. 从补充材料提取
```

### 入库粒度

```text
一篇论文一个 code library
或一个项目一个 code library
```

禁止把论文代码混入公共库。

### 固定版本

```text
commit_sha
repo_url
ref
license
snapshot_id
```

---

## 10. 阶段五：Exemplar Pack

code RAG 不只返回 snippet，而返回：

```json
{
  "exemplar_id": "ex_...",
  "source_unit_id": "unit_...",
  "library_id": "lib_...",
  "snapshot": "snap_...",
  "path": "src/...",
  "start_line": 136,
  "end_line": 315,
  "signature": "normalize_total(adata, *, target_sum=None, ...)",
  "code": "...",
  "imports": ["import scanpy as sc"],
  "call_sites": ["..."],
  "minimal_usage": "sc.pp.normalize_total(adata, target_sum=1e4)",
  "preconditions": ["adata.X contains counts"],
  "tests": ["..."],
  "license": "BSD-3-Clause",
  "commit": "abc123"
}
```

### 为什么

```text
模型不需要整个 repo
只需要 1–3 个正确模块
```

---

## 11. 阶段六：代码生成

### 模式

```text
learn       解释，不改
extract     抽一个函数/步骤
adapt       按我们的接口改写
reimplement 学思路，重新实现
project     整项目复刻
```

### 输入

```text
任务说明
目标接口
输入/输出
依赖限制
exemplars
许可证限制
测试要求
```

### 输出

```text
patch
new_files
tests
provenance
license_note
```

### 来源标注

```text
copied_from
adapted_from
inspired_by
```

无 license 或 GPL 风险时：

```text
只能 inspired_by
不能 copied_from
```

---

## 12. 代码验收

没有测试，不叫成功。

```text
import test
compile / lint
unit test
golden output
error case
```

### 指标

```text
compile_pass
test_pass
target_test_pass@1
```

不得把：

```text
LLM 生成代码
```

当作：

```text
复刻成功
```

---

## 13. 阶段七：复刻尝试

### 定义

```text
Replication Attempt
```

不是：

```text
Reproduce Paper
```

### 范围

```text
一个小目标：
  - 一个预处理步骤
  - 一张图的统计
  - 一个函数
  - 一个工作流节点
```

### 环境

```text
container image + digest
python / R / nextflow
dependencies lock
input hash
command
exit code
logs
```

### 状态

```text
planned
running
partial
failed
verified
```

### 人工

```text
批准目标
看结果
决定是否接受
```

---

## 14. 阶段八：夜间候选池

### 正确做法

```text
候选池
  -> 人工/规则批准的列表
  -> 夜间 worker
  -> 配额
  -> 失败重试
  -> 早报
```

### 配额

```text
每晚 repo 数
磁盘上限
embedding GPU 时间
GitHub rate limit
```

### 不做

```text
全网爬生信 repo
无授权批量下载
无人值守生成/执行代码
```

```text
夜间批量 = 已批准候选的入库
不是自动吞下领域
```

---

## 15. 数据模型

### 论文与代码链接

```text
paper_repo_links
  link_id
  paper_id
  repo_url
  repo_type
  commit_sha
  license
  confidence
  evidence_id
  status candidate/approved/rejected
  approved_by
```

### 论文代码库

```text
paper_code_libraries
  paper_id
  library_id
  snapshot
  commit_sha
  license
```

### 代码任务

```text
code_tasks
  task_id
  paper_id
  library_id
  mode
  target
  status
  plan_hash
  approved_by
  created_by
```

### 生成与测试

```text
code_generations
  generation_id
  task_id
  patch_uri
  provenance
  license_note
  compile_status
  test_status
  artifact_uri
```

### 复刻

```text
replication_jobs
  replication_id
  paper_id
  library_id
  target
  status
  container_digest
  input_hash
  output_hash
  result
```

### 复用现有

```text
rag_plans / rag_jobs / rag_runs
rag_evidence / rag_artifacts
rag_multi_queries / rag_adjudications
```

---

## 16. DSH 工具

```text
paper_watch
paper_acquire
paper_ingest
paper_analyze
repo_candidates
repo_validate
repo_ingest
code_exemplar
code_generate
code_test
replication_submit
workflow_status
```

### 规则

```text
paper_acquire 只提交，不直接下载
repo_ingest 只提交，不直接 clone
code_generate 只生成草稿
code_test 必须沙箱
replication_submit 必须人工批准
```

---

## 17. 人工 Gate

| 动作 | Gate |
|---|---|
| 下载闭源 PDF | 人 |
| 下载/执行 repo | 人 |
| 选择复刻目标 | 人 |
| 生成代码范围 | 人 |
| 接受生成代码 | 人 |
| 夜间批量 | 人批准候选 |
| 导出/发布 | 人 |

DSH 不能自批。

---

## 18. 许可证矩阵

| License | copied | adapted | inspired |
|---|---|---|---|
| MIT | 可，保留声明 | 可 | 可 |
| Apache-2.0 | 可，保留 NOTICE | 可 | 可 |
| BSD | 可，保留声明 | 可 | 可 |
| GPL/AGPL | 默认不 | 默认不 | 可 |
| 无 license | 不 | 不 | 可 |
| 不明 | 不 | 不 | 可 |

许可证判断结果必须写入 artifact。

---

## 19. 安全

```text
外部 repo 不可信
  -> 沙箱
  -> 无网络
  -> CPU/内存/时间限制
  -> 不挂载宿主目录
```

```text
PDF/网页 prompt injection
  -> 当数据，不当指令
```

```text
数据出境
  -> cloud_gate
```

---

## 20. 与多 RAG 扩展的关系

每个 RAG 注册：

```text
rag_id
capabilities
input/output
endpoint
model bindings
data residency
```

工作流按 capability 选 provider：

```text
literature  -> evidence_search
docs        -> doc_search
code        -> code_search / code_exemplar
future      -> 任意 capability
```

新增 RAG 不需要改工作流代码，只需要：

```text
manifest
worker
health
capability
```

---

## 21. 最小验证实验

选一篇：

```text
开放获取
有 GitHub
代码可运行
数据不大
```

验证：

```text
1. 标题找到 paper
2. PDF 入库
3. 总结要点
4. 抽 repo
5. 人确认
6. code 入库
7. exemplar 抽取
8. 生成一个函数
9. 测试
10. 导出 evidence/artifact
```

### 成功标准

```text
paper 入库
summary 有 evidence
repo 校验通过
code units > 0
exemplar 可定位
生成代码 compile
测试通过
```

### 不宣称

```text
整篇论文复刻成功
```

除非真的跑通对应目标。

---

## 22. 分阶段

| 阶段 | 工作 | 人日 |
|---|---|---:|
| P0 | 单篇 manual pipeline | 3 |
| P1 | paper acquire/ingest/analyze | 4 |
| P2 | repo validate/ingest | 3 |
| P3 | exemplar pack | 3 |
| P4 | code synthesis + sandbox tests | 5 |
| P5 | replication attempt | 5 |
| P6 | nightly candidate pool | 3 |
| P7 | 多 RAG 通用化 | 3 |
| 合计 |  | **29 人日** |

先做 P0，不先做 P6。

---

## 23. 不做

```text
不自动吞下整个领域
不自动执行不可信 repo
不把生成代码当复刻成功
不把无 license 代码复制进项目
不把整 repo 塞给模型
不让 agent 自批
不把 RAG 检索当代码生成
```

---

## 24. 租户私有库与主库联合使用

### 24.1 目标

```text
用户 A 可以批量入库文章/代码
  -> 只进入 A 的私有库
  -> 不影响主库
  -> 可以联合查询主库
  -> 不能读取用户 B 的私有库
```

### 24.2 三种 scope

```text
scope=private
  只查当前 workspace 的私有 library
scope=main
  只查公共主库
scope=both
  私有库 + 主库联合检索
```

所有入口都必须显式携带：

```text
workspace_id
scope
library_id（可选）
```

不能只在 UI 层过滤。

### 24.3 结果分组

```text
private group
main group
```

规则：

```text
不跨库合并分数
不把私有 evidence 写回主库
保留 library_id / snapshot / workspace 来源
```

### 24.4 现有基础与缺口

已有：

```text
workspace / membership / role
library.owner / workspace
library.visibility
code RAG 的 library_id + snapshot_id
```

缺口：

```text
literature RAG 仍是主库形态
检索入口没有统一 scope
缓存/任务/证据没有强制 workspace 过滤
```

### 24.5 文献私有库的两条路线

```text
A. scipal_rebuild 增加 library_id 分区
   主库 default main
   私有库 private:<workspace>
   所有检索强制 scope

B. 单独 private corpus
   主库完全不动
   私有库独立 schema/DB
```

先评估 A；迁移会影响现有索引，必须单独做，不得直接改生产索引。

### 24.6 代码侧

code RAG 已经是：

```text
library_id
snapshot_id
```

每篇论文/项目一个逻辑 library：

```text
lib_private_<workspace>_<paper>
lib_main_<project>
```

联合查询就是多 library 分组检索，不需要每篇一个数据库。

### 24.7 主库写入与晋升

普通用户：

```text
只能写自己的私有库
只能读主库
```

主库入库：

```text
curator / admin
license review
provenance
```

私有库晋升：

```text
private library
  -> 提名
  -> 许可证/质量审查
  -> 复制到 main
  -> 保留原 library_id 来源
```

不是移动，是复制 + 溯源。

### 24.8 配额

私有批量入库必须计入：

```text
存储
embedding GPU 时间
检索 QPS
夜间任务数
```

否则单个用户可打满平台。

### 24.9 隔离检查清单

```text
查询是否带 workspace_id
缓存 key 是否含 workspace/library/model
向量索引是否强制 library filter
evidence 是否能被其他租户反查
后台任务是否会扫到其他租户
删除私有库是否影响主库
导出包是否带私有数据
```

### 24.10 实施顺序

```text
P1.5 文献私有库/scope 路由   4 人日
P2.5 配额/审计                2 人日
P3.5 私有 -> 主库晋升         2 人日
```

先做 P0 单篇 pipeline，再做私有库合并；不要同时改主库索引和生成链路。

## 25. 结论

```text
文献监控 -> 入库      可行
论文总结 -> 代码链接  可行
代码按需入库          可行
exemplar 抽取         可行
按需生成/适配          可行，但需测试
整项目复刻             独立工作流
夜间批量               只处理已批准候选
```

一句话：

```text
让 code RAG 提供“正确的最小实现样例”
让大模型做“适度调整”
让测试证明“没有写坏”
让人决定“是否接受”
```
