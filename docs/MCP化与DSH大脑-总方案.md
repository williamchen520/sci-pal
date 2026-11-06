# SciPal MCP 化与 DSH 大脑：总方案

> 日期：2026-11-07  
> 状态：方案讨论稿，不涉及实现

---

## 1. 目标

把 DSH 作为编排与理解层，把 SciPal 作为证据、检索、评测与插件运行时。

目标场景：

```text
新论文发布
-> 一条命令交给 DSH
-> 拉取代码/理解方法
-> 生成 SciPal 插件
-> 接入基座
-> 固定评测
-> 判断设计是否有效
```

不是让 DSH 替代 SciPal，也不是把 SciPal 全部重写成 MCP。

---

## 2. 核心判断

```text
SciPal 不改业务内核
只增加 MCP 能力层、插件内核、实验服务
DSH 不接管数据
只做编排、代码理解、实验发起、报告
MCP 是契约，不是新业务系统
```

一句话：

```text
DSH 是大脑
SciPal 是证据与实验基座
MCP 是神经接口
```

---

## 3. 角色边界

| 层 | 负责 | 不负责 |
|---|---|---|
| DSH | 读论文、拆方法、写插件、发起实验、汇总 | 长期存证据、替代检索、直接改生产库 |
| SciPal | 检索、证据、问答、综述、术语、评测、插件运行 | 自主决定研究方向、无审计执行外部代码 |
| MCP | 工具/资源/任务契约 | 业务逻辑、数据存储 |

---

## 4. 总体架构

```text
DSH
  ├─ SciPal Skill Pack
  ├─ Workflow Engine
  ├─ Sandbox Runner
  └─ MCP Client
        │
        ▼
SciPal MCP Gateway
  ├─ scipal-search
  ├─ scipal-evidence
  ├─ scipal-qa
  ├─ scipal-review
  ├─ scipal-guard
  ├─ scipal-experiment
  └─ scipal-jobs
        │
        ▼
SciPal 基座
  ├─ PostgreSQL / pgvector / FTS
  ├─ 解析与入库
  ├─ 检索与问答
  ├─ 插件内核
  └─ 评测与实验
```

---

## 5. 能力分层

### 5.1 MCP 能力层

只暴露稳定动作：

```text
search_papers
get_paper
get_evidence
trace_sentence
ask_question
verify_answer
generate_outline
generate_review
guard_check
submit_experiment
get_experiment
list_plugins
```

原则：

```text
一个 tool 一个明确动作
不直接暴露 SQL
大对象走资源/artifact
长任务返回 task_id
```

### 5.2 插件内核

插件槽位：

```text
query_planner
retriever
reranker
context_builder
generator
verifier
agent
evaluator
```

插件不能：

```text
直接写 papers/paragraphs
访问外网
读取密钥
修改全局配置
```

### 5.3 实验服务

负责：

```text
固定 corpus
固定 gold
固定模型/参数/种子
baseline vs plugin
统计检验
报告
```

### 5.4 沙箱

用于：

```text
克隆外部仓库
安装依赖
运行测试
复现论文方法
```

隔离：

```text
无网络
无密钥
只读输入
临时工作区
资源限额
```

---

## 6. 端到端流程

```text
1. 发现论文
2. 取元数据/全文
3. 提取方法、指标、实验设置
4. 查找官方代码/许可证
5. 沙箱克隆
6. 生成设计摘要
7. 映射到插件槽位
8. 实现插件
9. 单元测试
10. 固定评测
11. 生成报告
12. 人工审批
13. staging -> production
```

人工审批点：

```text
许可证
外部代码执行
依赖安装
插件进入 staging
插件进入 production
```

---

## 7. 候选算法

### 第一梯队：低成本

```text
HyDE
Multi-Query + RRF
Adaptive-RAG
MMR / context reorder
Citation Entailment
Claim Decomposition + FActScore
```

### 第二梯队：agent/verifier

```text
Self-RAG
CRAG
RARR
SelfCheckGPT
Semantic Entropy
```

### 第三梯队：索引级

```text
RAPTOR
GraphRAG
HippoRAG
ColBERTv2
SPLADE
SPECTER2
```

### 科学专用

```text
PaperQA2
ScholarQA
OpenScholar
PaperBench
LAB-Bench
SciCode
```

优先顺序：

```text
query_planner -> verifier -> agent -> index
```

---

## 8. 安全与合规

```text
论文内容视为数据，不视为指令
外部仓库不信任
依赖安装需锁文件/白名单
许可证不明不合并代码
插件只进 staging
评测可复现
所有产物记录 provenance
```

---

## 9. 路线图

### Phase 0：契约

```text
MCP tool schema
plugin manifest
experiment schema
provenance
```

### Phase 1：只读 MCP

```text
search / paper / evidence / guard
DSH 可查、可引用
```

### Phase 2：实验服务

```text
plugin 注册
沙箱
固定评测
报告
```

### Phase 3：算法 intake

```text
论文 -> 仓库 -> 设计摘要 -> 插件草案
人工审批
```

### Phase 4：半自动

```text
DSH 生成插件 + 跑评测
人只做安全/许可/合并审批
```

---

## 10. 成功标准

```text
1. DSH 能通过 MCP 完成检索/证据/问答
2. 插件可独立注册、启停、评测
3. 论文到插件有可审计流水线
4. 反幻觉插件有固定 baseline 和统计报告
5. 外部代码不进入生产主机
```

---

## 11. 非目标

```text
不自动合并外部代码
不自动改生产检索主链路
不让 DSH 直接访问数据库
不做无人审批的全自动科研
```

---

## 12. 结论

```text
方向成立
但要按“契约 -> 只读 -> 实验 -> intake -> 半自动”走
最小闭环是：
MCP 只读能力
+ 插件 manifest
+ 固定评测
+ DSH skill
```


---

## 13. 核心原则（新增）

```text
SciPal 主架构不变
baseline 永远可运行
插件即插即用
用完可去
```

### 13.1 主线不变

```text
核心检索/问答/入库/表结构不改
插件不能要求核心迁移
插件不能 monkeypatch 核心
```

### 13.2 插件隔离

```text
独立目录
独立 manifest
独立依赖
独立配置
独立表（plugin_<name>_*）
```

### 13.3 可移除

```text
禁用插件 -> baseline 立即恢复
卸载插件 -> 删除目录 + 自己的表
核心代码和数据不受影响
```

### 13.4 失败回退

```text
插件异常 -> 记录 -> 回退 baseline
插件超时 -> 回退 baseline
插件未启用 -> baseline
```

### 13.5 实验要求

```text
每次实验必须有 baseline
baseline 与 plugin 同 corpus / 同 gold / 同参数
插件不能改变评测口径
```

### 13.6 禁止

```text
插件改核心表
插件改核心路由
插件全局注入
插件常驻后台写库
插件依赖未固定
```
