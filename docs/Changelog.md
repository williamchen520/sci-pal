# SciPal 研发时间轴 / Changelog

> 更新：2026-11-12  
> 口径：以仓库内工作日志、迁移报告和验收文档为依据；早期 WorkBuddy 阶段没有完整日期，只保留决策顺序，不虚构精确日期。

---

## 1. WorkBuddy / CodeBuddy 时代

目标：把 SciPal 做成可本地运行的科研助手，而不是一次性脚本。

关键决策：

```text
本地优先
SQLite + Chroma 作为默认存储
文档、工单、验收报告随代码一起维护
AI 协作先写工单和验收标准，再改代码
```

代表文档：

- [协作约定-WorkBuddy-CodeBuddy](archive_legacy/协作约定-WorkBuddy-CodeBuddy.md)
- [HANDOVER](HANDOVER.md)
- [Research Logs Index](Research_Logs_Index.md)

遗留问题：

```text
SQLite 单文件并发弱
Chroma 与业务库分离，一致性难保证
大语料重建和恢复能力不足
```

---

## 2. PostgreSQL 单栈迁移（2026-11-07 / 11-08）

关键决策：

```text
生产运行时只保留 PostgreSQL 16 + pgvector
SQLite research.db 退役，不挂载、不创建
Chroma 退役，不再初始化
```

结果：

```text
PG-only 运行时
段落向量 + GIN 全文索引
可恢复的 corpus rebuild
```

代表文档：

- [PG-only 迁移总报告](PG-only迁移总报告-2026-11-08.md)
- [架构-PG单栈架构](架构-PG单栈架构.md)
- [架构-PG纯净化路线](架构-PG纯净化路线.md)

---

## 3. 数据层物理隔离（2026-11-09 / 11-10）

关键决策：

```text
scipal_core     业务 / 鉴权 / 项目 / 实验
scipal_rebuild  论文 / 段落 / 句子 / 向量
没有跨库外键
只用逻辑 ID
```

读写归属：

```text
core_connection()       业务
auth_connection()       鉴权
corpus_connection()     语料读
main_read_connection()  语料读
owner_connection()      语料写
ingest_connection()     入库写
```

代表文档：

- [数据层隔离审计](数据层隔离审计.md)
- [架构变更-数据层物理隔离](架构变更-数据层物理隔离.md)
- [架构变更-鉴权库物理隔离](架构变更-鉴权库物理隔离.md)

---

## 4. 鉴权与最小权限（2026-11-10 / 11-11）

关键决策：

```text
全局 API 鉴权：session / bearer / internal token
内部端点 /api/ingest、/api/embed 必须带内部 token
数据库角色：core_app / corpus_reader / corpus_writer
app 角色无 DDL
插件建表走独立迁移
```

代表文档：

- [P4e-开发者权限与break-glass](P4e-开发者权限与break-glass.md)
- [P4f-独立开发库结果](P4f-独立开发库结果.md)
- [架构变更-P4b-连接拆分](架构变更-P4b-连接拆分.md)

---

## 5. 检索架构演进

关键决策：

```text
pgvector HNSW 召回
PostgreSQL GIN 全文
RRF 融合
可选 cross-encoder rerank
句级证据 + 句子窗口
```

实验契约：

```text
RetrievalHit / RetrievalResult
hit_sentence_ids 参与评分
context_sentence_ids 只用于生成，不计 Recall
```

代表文档：

- [召回架构-SentenceWindow设计](召回架构-SentenceWindow设计.md)
- [召回架构-逻辑滑窗](召回架构-逻辑滑窗.md)
- [公共测试集选型](公共测试集选型.md)

---

## 6. DSH 适配与插件化

关键决策：

```text
DSH 作为推理/编排层
SciPal 保持证据层和确定性检索
MCP 作为工具边界
DSH 插件可移除，不污染核心
```

代表文档：

- [工作计划-DSH适配与插件化](工作计划-DSH适配与插件化.md)
- [DSH契约要点](DSH契约要点.md)
- [DSH Integration and Plugins](en/plans/DSH-Integration-and-Plugins.md)

---

## 7. 运维加固（2026-11-11 / 11-12）

关键决策：

```text
core 每 6h 备份，保留 7d
corpus 每 7d 备份，保留 28d
AES-256-CBC + PBKDF2 加密
恢复演练同时验证数据、GIN、HNSW
生产 DSN fail-closed
```

恢复演练结果：

```text
papers            13,201
paragraphs       410,270
sentences      1,780,306
embeddings       343,546
GIN              valid
HNSW             valid
```

代表文档：

- [恢复演练-20261112](恢复演练-20261112.md)
- [备份策略-双库](备份策略-双库.md)

---

## 8. 代码审查与工程治理（2026-11-12）

关键决策：

```text
P0：PaperStore 数据归属、插件运行时 DDL、硬编码 DSN、架构门禁
P1：读路径测试、统一 RetrievalResult、公共数据 loader、core 空壳、env fail-closed
治理门禁：高风险改动先停、先报计划、人类批准后执行
```

代表文档：

- [代码审查-20261112](代码审查-20261112.md)
- [修复计划-代码审查P0](修复计划-代码审查P0.md)
- [工程治理门禁规范](工程治理门禁规范.md)

---

## 9. 当前与下一步

当前：

```text
P0 / P1 关闭
生产 health 200
A 27/27、B 13/13
治理门禁接入 PR/CI
```

下一步：

```text
实验 Phase C
SciFact loader → sentence index → F0 → B ±1 → C 500 词句界 chunk → 20 claims 烟测
```

---

## 相关索引

- [文档总索引](README.md)
- [全部文档](_index/all.md)
