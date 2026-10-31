# SciPal 文档索引（docs/）

> 项目总说明以仓库根目录的 [`../README.md`](../README.md) 为准。
> 本目录存放架构、接口、评测与计划文档；历史工单与旧方案在 [`archive/`](archive/README.md)。

## 从哪里开始

| 目的 | 文档 |
|------|------|
| 项目是什么、怎么启动 | [`../README.md`](../README.md) |
| 架构、模块、路由与数据流 | [架构与路由图.md](架构与路由图.md) |
| 文献监控 | [工作计划-自适应与文献情报.md](工作计划-自适应与文献情报.md) |
| 领域包 | [肿瘤免疫领域包](../packs/biomed-oncoimmuno/README.md) |
| Claim 试点 | [claim-pilot-审讯记录-01.md](claim-pilot-审讯记录-01.md) |
| Claim 写作口径 | [claim-pilot-在线入库-01.md](claim-pilot-在线入库-01.md) |
| Google CoE 对照 | [CoE-对照与借鉴.md](CoE-对照与借鉴.md) |
| 插件端口与对比评测 | [工作计划-插件端口与对比评测.md](工作计划-插件端口与对比评测.md) |
| PDF 三引擎解析 | [PDF解析-三引擎联合.md](PDF解析-三引擎联合.md) |
| JATS 导入与外部文献源 | [文献源-JATS与外部源.md](文献源-JATS与外部源.md) |
| 多用户与数据隔离 | [工作计划-多用户与数据隔离.md](工作计划-多用户与数据隔离.md) |
| 去学科化与领域包分发 | [工作计划-去学科化与领域包分发.md](工作计划-去学科化与领域包分发.md) |
| 自适应与文献情报 | [工作计划-自适应与文献情报.md](工作计划-自适应与文献情报.md) |
| 项目跟踪与实验记录 | [工作计划-项目跟踪与实验记录.md](工作计划-项目跟踪与实验记录.md) |
| DSH 适配与插件化 | [工作计划-DSH适配与插件化.md](工作计划-DSH适配与插件化.md) |
| 全部函数签名 / 参数 / 返回值 | [接口明细.md](接口明细.md) |
| 可选项与用户配置 | [可选项与用户配置.md](可选项与用户配置.md) |
| 模型分层与数据隔离配置 | [DSH-模型分层配置.md](DSH-模型分层配置.md) |
| 评测说明 | [评测说明.md](评测说明.md) |
| 证据与评测契约 | [证据与评测契约.md](证据与评测契约.md) |
| Contextual Retrieval | [Contextual-Retrieval.md](Contextual-Retrieval.md) |
| QA 预算评测 | [QA预算评测.md](QA预算评测.md) |
| 撤稿标记与 Prompt Injection | [可信度-撤稿与注入.md](可信度-撤稿与注入.md) |
| 摘要层（RAPTOR 精简版） | [摘要层-RAPTOR精简版.md](摘要层-RAPTOR精简版.md) |
| 引用意图 | [引用意图.md](引用意图.md) |
| Claim–Evidence 图 | [claim-evidence.md](claim-evidence.md) |
| 系统综述工作流 | [系统综述工作流.md](系统综述工作流.md) |
| 项目里程碑数据表 | [项目里程碑数据表.md](项目里程碑数据表.md) |
| Git 分支保护与本地钩子 | [Git-分支保护与钩子.md](Git-分支保护与钩子.md) |
| 许可证与依赖合规 | [许可证说明.md](许可证说明.md) |
| 历史工单 / 阶段验收 / 旧计划 | [archive/](archive/README.md) |
| 协作规范 | [协作规范.md](协作规范.md) |
| AI 最高优先级规则 | [`../.dsh_rules`](../.dsh_rules) |
| PR 自检模板 | [`../.github/pull_request_template.md`](../.github/pull_request_template.md) |
| 贡献指南 | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| 给 AI 代码助手的项目说明 | [`../AGENTS.md`](../AGENTS.md) |
| 机器可读架构（V33.96） | [`../ARCHITECTURE.json`](../ARCHITECTURE.json) |

## 维护规则

- 当前有效的架构、评测、五份工作计划放在 `docs/` 顶层；
- 历史工单、阶段验收、旧设计放 `docs/archive/`；
- 新增文档先判断是“当前规范”还是“过程记录”；
- 根 README 只保留入口，不复制正文。
