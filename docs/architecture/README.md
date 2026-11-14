# 架构规范

> 共 180 篇 · 分类索引，文件原路径不变

| 标题 | 摘要 | 文档 |
|---|---|---|
| SciPal 研发时间轴 / Changelog | --- | [Changelog.md](../Changelog.md) |
| Google CoE（Chain-of-Evidence）对照与借鉴 | --- | [CoE-对照与借鉴.md](../CoE-对照与借鉴.md) |
| Sci-Pal Data Layer Architecture V2 | --- | [DATA_LAYER_ARCHITECTURE_V2.md](../DATA_LAYER_ARCHITECTURE_V2.md) |
| DSH 配置：模型分层与数据隔离 | { | [DSH-模型分层配置.md](../DSH-模型分层配置.md) |
| DSH（DeepSeek Harness）契约要点 — 核对于官方文档 | --- | [DSH契约要点.md](../DSH契约要点.md) |
| Git 分支保护与本地钩子 | 入口： | [Git-分支保护与钩子.md](../Git-分支保护与钩子.md) |
| GitHub 主仓 + Gitee 镜像 | - GitHub 仓库：https://github.com/williamchen520/sci-pal （public） | [GitHub主仓与Gitee镜像.md](../GitHub主仓与Gitee镜像.md) |
| Project Handover Guide | This document is the first thing a new maintainer should read after .dshrules | [HANDOVER.md](../HANDOVER.md) |
| SciPal MCP 化与 DSH 大脑：总方案 | --- | [MCP化与DSH大脑-总方案.md](../MCP化与DSH大脑-总方案.md) |
| SciPal MCP 化与 DSH 大脑：细化策略 | --- | [MCP化与DSH大脑-细化策略.md](../MCP化与DSH大脑-细化策略.md) |
| P3：sentence backend 接入 | --- | [P3-sentence-backend接入.md](../P3-sentence-backend接入.md) |
| P3b PMC OA 语料清单 | downloaded 25 | [P3b-PMC-OA语料清单.md](../P3b-PMC-OA语料清单.md) |
| P4b：只读语料切换 | --- | [P4b-只读语料切换.md](../P4b-只读语料切换.md) |
| P4c3 owner 写边界 | --- | [P4c3-owner写边界.md](../P4c3-owner写边界.md) |
| P5 清理记录 | 旧库 scipalbench -> 重命名 -> DROP | [P5-清理.md](../P5-清理.md) |
| PDF 三引擎联合解析（Docling + GROBID + MinerU） | XML（PMC）走独立结构化导入，不参与此流水线。 | [PDF解析-三引擎联合.md](../PDF解析-三引擎联合.md) |
| Research Logs Index | --- | [Research_Logs_Index.md](../Research_Logs_Index.md) |
| 无域名公网 HTTPS：Tailscale Funnel | --- | [TLS-公网Funnel.md](../TLS-公网Funnel.md) |
| Windows 开发警示与跨平台规范 | --- | [Windows开发警示与跨平台规范.md](../Windows开发警示与跨平台规范.md) |
| ADR-001：机器守卫的范围 | 日期：2026-11-09 | [ADR-001-guard-scope.md](../adr/ADR-001-guard-scope.md) |
| Claim–Evidence 图（试点） | claims(claimid, paperid, sentenceid, claimtext, claimtype, createdat) | [claim-evidence.md](../claim-evidence.md) |
| Claim 试点反例标注 v1（AI 辅助，待人工复核） | --- | [claim-pilot-反例标注-01.md](../claim-pilot-反例标注-01.md) |
| Claim 试点在线入库 v1 | --- | [claim-pilot-在线入库-01.md](../claim-pilot-在线入库-01.md) |
| Claim 试点第一轮审讯记录（AI 预审） | --- | [claim-pilot-审讯记录-01.md](../claim-pilot-审讯记录-01.md) |
| Claim 试点语料扩展 v1 | --- | [claim-pilot-语料扩展-01.md](../claim-pilot-语料扩展-01.md) |
| API Reference | --- | [API-Reference.md](../en/API-Reference.md) |
| Architecture Overview | This is the short English entry point. For the machine contract see | [Architecture-Overview.md](../en/Architecture-Overview.md) |
| SciPal Architecture and Routes | This document covers the current cross-module flow and route groups. The | [Architecture-and-Routes.md](../en/Architecture-and-Routes.md) |
| Developer Guide: Modules and Routes | Start with the module index | [Modules-and-Routes.md](../en/Modules-and-Routes.md) |
| SciPal Documentation (English) | English | 简体中文(../../README.zh-CN.md) | [README.md](../en/README.md) |
| Work Plan: Adaptive Retrieval and Literature Intelligence | 1. Generate one literature digest per week for every user with profiles enabled; | [Adaptive-Retrieval-and-Literature-Intelligence.md](../en/plans/Adaptive-Retrieval-and-Literature-Intelligence.md) |
| Work Plan: From "Review Generation" to an "Argument Workbench" | --- | [Argument-Workbench.md](../en/plans/Argument-Workbench.md) |
| Work Plan: DSH Integration and Plugins | DSH desktop/server | [DSH-Integration-and-Plugins.md](../en/plans/DSH-Integration-and-Plugins.md) |
| Work Plan: Discipline-Agnostic Core, Domain Packs, and Distribution | SciPal still contains HCC/biomedicine hardcoding: | [Domain-Packs-and-Distribution.md](../en/plans/Domain-Packs-and-Distribution.md) |
| Work Plan: Multi-User Support and Data Isolation | Lab scenario: | [Multi-User-and-Data-Isolation.md](../en/plans/Multi-User-and-Data-Isolation.md) |
| Work Plan: Plugin Ports and Comparative Benchmarking | --- | [Plugin-Ports-and-Benchmarks.md](../en/plans/Plugin-Ports-and-Benchmarks.md) |
| Work Plan: SQLite → PostgreSQL Migration | --- | [PostgreSQL-Migration.md](../en/plans/PostgreSQL-Migration.md) |
| Work Plan: Project Tracking and Experiment Records (ELN) | To be explicit: | [Project-Tracking-and-ELN.md](../en/plans/Project-Tracking-and-ELN.md) |
| 架构守卫使用说明 | ARCHITECTURE.json 描述：路由表 / 蓝图 / 数据层 | [guards.md](../guards.md) |
| research.db 读路径盘点 | --- | [research.db读路径盘点.md](../research.db读路径盘点.md) |
| scipal-guard 质量评估 | 场景 B 的 3 个 unknown 全部是人为编造，没有把真基因误判；场景 C 里 CRISPR、Western blot、qPCR、flow cytometry 没有被判 unknown。 | [scipal-guard-评估.md](../scipal-guard-评估.md) |
| 专家建议评审：架构防腐与暗病防呆 | --- | [专家建议评审-架构防腐.md](../专家建议评审-架构防腐.md) |
| 事故报告：测试建库误删主库表 | --- | [事故报告-主库误删-20261110.md](../事故报告-主库误删-20261110.md) |
| 主项目代码审查报告 | --- | [代码审查-20261112.md](../代码审查-20261112.md) |
| 决策：Build 阶段与 Outbox 策略 | 运行时写路径已基本 PG-first，但 papers/sections/paragraphs/sentences 的 outbox trigger 仍保留。 | [决策-Build时Outbox策略.md](../决策-Build时Outbox策略.md) |
| 决策：Outbox 最终范围 | triggers 27 | [决策-Outbox最终范围.md](../决策-Outbox最终范围.md) |
| 动态上下文滑窗：工业级实现与遗漏兜底策略 | --- | [动态上下文滑窗-工业级实现与兜底.md](../动态上下文滑窗-工业级实现与兜底.md) |
| SciPal 协作规范 | --- | [协作规范.md](../协作规范.md) |
| 方法 | services/search/sentenceroles.py： | [句子角色选句实验.md](../句子角色选句实验.md) |
| 召回架构原型：Sentence Window Hybrid | --- | [召回架构-SentenceWindow设计.md](../召回架构-SentenceWindow设计.md) |
| 召回架构：智能逻辑滑窗 | --- | [召回架构-逻辑滑窗.md](../召回架构-逻辑滑窗.md) |
| 可信度：撤稿标记与 Prompt Injection 防护 | paperflags( | [可信度-撤稿与注入.md](../可信度-撤稿与注入.md) |
| 状态图例 | --- | [可选项与用户配置.md](../可选项与用户配置.md) |
| 1. 结论 | 在建立向量索引前，原先没有段落级审查。 | [向量索引污染审查.md](../向量索引污染审查.md) |
| 实验记录：BioViz Recipe RAG Phase 0/1 | --- | [实验-BioViz-Recipe-RAG.md](../实验-BioViz-Recipe-RAG.md) |
| 实验记录：HTML 论文解析器 | --- | [实验-HTML解析器.md](../实验-HTML解析器.md) |
| 实验记录：Paper Analysis 聚合入口 | --- | [实验-Paper-Analysis.md](../实验-Paper-Analysis.md) |
| 实验记录：Paper Reader API | --- | [实验-Paper-Reader-API.md](../实验-Paper-Reader-API.md) |
| 案例：HCC 新辅助免疫治疗 LAM 论文 → 代码模块与数据流 | --- | [实验-Paper-to-Code-HCC-LAM案例.md](../实验-Paper-to-Code-HCC-LAM案例.md) |
| 案例：HCC 多组学分子分型论文（HTML + Zenodo） | --- | [实验-Paper-to-Code-HCC-基因组案例.md](../实验-Paper-to-Code-HCC-基因组案例.md) |
| 实验记录：RAG 控制面 R0 Provider Registry | --- | [实验-RAG控制面-R0.md](../实验-RAG控制面-R0.md) |
| 实验记录：RAG 控制面 R1 Plans / Jobs / Lease | --- | [实验-RAG控制面-R1.md](../实验-RAG控制面-R1.md) |
| 实验记录：R10 Reviewer 权限 | --- | [实验-RAG控制面-R10-reviewer.md](../实验-RAG控制面-R10-reviewer.md) |
| 实验记录：R11 双人 Reviewer 与 Kappa | --- | [实验-RAG控制面-R11-双人kappa.md](../实验-RAG控制面-R11-双人kappa.md) |
| 实验记录：R12 Reviewer 指派与完成度 | --- | [实验-RAG控制面-R12-指派.md](../实验-RAG控制面-R12-指派.md) |
| 实验记录：R13 最终确认 Gate 与封存哈希 | --- | [实验-RAG控制面-R13-最终确认.md](../实验-RAG控制面-R13-最终确认.md) |
| 实验记录：R14 封存签名与只读 | --- | [实验-RAG控制面-R14-封存签名.md](../实验-RAG控制面-R14-封存签名.md) |
| 实验记录：R15 带签名的研究包导出 | --- | [实验-RAG控制面-R15-签名导出.md](../实验-RAG控制面-R15-签名导出.md) |
| 实验记录：R16 CSV 导出 | --- | [实验-RAG控制面-R16-CSV.md](../实验-RAG控制面-R16-CSV.md) |
| 实验记录：R17 可独立验证的封存包 | --- | [实验-RAG控制面-R17-独立验证.md](../实验-RAG控制面-R17-独立验证.md) |
| 实验记录：R18 封存公钥目录 | --- | [实验-RAG控制面-R18-公钥目录.md](../实验-RAG控制面-R18-公钥目录.md) |
| 实验记录：RAG 控制面 R2 模型与索引绑定 | --- | [实验-RAG控制面-R2.md](../实验-RAG控制面-R2.md) |
| 实验记录：RAG 控制面 R3 Local Worker + E2E | --- | [实验-RAG控制面-R3.md](../实验-RAG控制面-R3.md) |
| 实验记录：RAG 控制面 R4 Evidence / Artifact Ledger | --- | [实验-RAG控制面-R4.md](../实验-RAG控制面-R4.md) |
| 实验记录：RAG 控制面 R5 Gateway Query | --- | [实验-RAG控制面-R5.md](../实验-RAG控制面-R5.md) |
| 实验记录：R6 DSH Live 验收 | --- | [实验-RAG控制面-R6-live.md](../实验-RAG控制面-R6-live.md) |
| 实验记录：R6.1 Query Worker | --- | [实验-RAG控制面-R6.1.md](../实验-RAG控制面-R6.1.md) |
| 实验记录：RAG 计划审批 UI | --- | [实验-RAG控制面-R6.2-UI.md](../实验-RAG控制面-R6.2-UI.md) |
| 实验记录：RAG 控制面 R6.3 多 RAG 路由 | --- | [实验-RAG控制面-R6.3.md](../实验-RAG控制面-R6.3.md) |
| 实验记录：RAG 控制面 R6.4 Docs 路由 | --- | [实验-RAG控制面-R6.4-docs.md](../实验-RAG控制面-R6.4-docs.md) |
| 实验记录：RAG 控制面 R6.5 多 RAG Fanout | --- | [实验-RAG控制面-R6.5-fanout.md](../实验-RAG控制面-R6.5-fanout.md) |
| 实验记录：RAG 控制面 R6 DSH Tools | --- | [实验-RAG控制面-R6.md](../实验-RAG控制面-R6.md) |
| 实验记录：R7 分组证据与人工裁决 | --- | [实验-RAG控制面-R7-裁决.md](../实验-RAG控制面-R7-裁决.md) |
| 实验记录：R8 去重、冲突标记、审计导出 | --- | [实验-RAG控制面-R8-去重冲突导出.md](../实验-RAG控制面-R8-去重冲突导出.md) |
| 实验记录：SciPal 服务持久化 | --- | [实验-RAG控制面-服务持久化.md](../实验-RAG控制面-服务持久化.md) |
| 实验记录：Sentence Evidence 与 Caption 过滤 | --- | [实验-Sentence-Evidence.md](../实验-Sentence-Evidence.md) |
| 实验记录：Sentence Tree 入库 | --- | [实验-Sentence-Tree.md](../实验-Sentence-Tree.md) |
| 实验记录：代码库 UI 验收（A） | --- | [实验-代码RAG-A-UI.md](../实验-代码RAG-A-UI.md) |
| 实验记录：code-rag E0 评测脚手架与 L0 审计 | --- | [实验-代码RAG-E0.md](../实验-代码RAG-E0.md) |
| 实验记录：code-rag E2 DSH-like 对照 | --- | [实验-代码RAG-E2.md](../实验-代码RAG-E2.md) |
| 实验记录：code-rag E3 L2 上下文闭合 | --- | [实验-代码RAG-E3.md](../实验-代码RAG-E3.md) |
| 实验记录：code-rag E4 编译 / 执行（部分） | --- | [实验-代码RAG-E4.md](../实验-代码RAG-E4.md) |
| 实验记录：code-rag E5 真实 DSH 会话 pilot | --- | [实验-代码RAG-E5.md](../实验-代码RAG-E5.md) |
| 实验记录：code-rag P3 检索 | --- | [实验-代码RAG-P3.md](../实验-代码RAG-P3.md) |
| 实验记录：code-rag P4 DSH MCP | --- | [实验-代码RAG-P4.md](../实验-代码RAG-P4.md) |
| 实验记录：code-rag P5 UI「我的代码库」 | --- | [实验-代码RAG-P5.md](../实验-代码RAG-P5.md) |
| 实验记录：code-rag P6 30 问题评测 | --- | [实验-代码RAG-P6.md](../实验-代码RAG-P6.md) |
| 实验数据契约 v1 | --- | [实验数据契约.md](../实验数据契约.md) |
| 实验数据库设计：SciFact + 方法对比 | --- | [实验数据库设计.md](../实验数据库设计.md) |
| 实验方法调查表：检索 / 索引 / 系统 / 优化器 / 父子级 | --- | [实验方法调查表.md](../实验方法调查表.md) |
| 实验设计时间方案与可行性评估 | --- | [实验设计-时间方案.md](../实验设计-时间方案.md) |
| 工作总结 — 2026-11-02 | This is the durable summary of the engineering work completed up to this point, | [工作总结-2026-11-02.md](../工作总结-2026-11-02.md) |
| 工程治理门禁规范 | --- | [工程治理门禁规范.md](../工程治理门禁规范.md) |
| 开发手册：模块与路由 | 相关文档： | [开发-模块手册.md](../开发-模块手册.md) |
| 开发流程规范：架构即代码 | 1. 新增 / 修改 / 删除路由，先输出拟修改 JSON + 原因 | [开发流程规范.md](../开发流程规范.md) |
| 异步「下载 + 入库 + 向量化」设计 | --- | [异步入库-下载与向量化.md](../异步入库-下载与向量化.md) |
| 引用意图（citation intent） | sentencelinks 新增： | [引用意图.md](../引用意图.md) |
| 完整 evidence 请求耗时 Profile | 完整请求不是 PG FTS 慢 | [性能-profile-evidence.md](../性能-profile-evidence.md) |
| 接口文档 | --- | [接口明细.md](../接口明细.md) |
| 摘要层（RAPTOR 精简版） | summaries( | [摘要层-RAPTOR精简版.md](../摘要层-RAPTOR精简版.md) |
| Data Issue: Sentence IDs Differ Between SQLite and PostgreSQL | gold sentence total 65 | [数据-句子ID不一致.md](../数据-句子ID不一致.md) |
| 数据层雏形评估 | --- | [数据层雏形评估.md](../数据层雏形评估.md) |
| 1 万篇抽样方案与容量清单 | --- | [数据扩容-1万篇抽样与容量.md](../数据扩容-1万篇抽样与容量.md) |
| P3 PDF 重建 | --- | [数据重建-P3-PDF重建.md](../数据重建-P3-PDF重建.md) |
| End-to-End RRF Loop Profile | Per-query total (including both score counts): | [数据重建-P4-RRF-Loop-Profile.md](../数据重建-P4-RRF-Loop-Profile.md) |
| P4 RRF / Multi-Stage Experiment | --- | [数据重建-P4-RRF实验.md](../数据重建-P4-RRF实验.md) |
| rank_cd 小范围验证 | SentenceFTS.search(termlimit=8, topk=100, ranker="rankcd") | [数据重建-P4-RankCD-小范围.md](../数据重建-P4-RankCD-小范围.md) |
| Reranker Single-Query Profile | sentencesearch 1.604s | [数据重建-P4-Reranker-Profile.md](../数据重建-P4-Reranker-Profile.md) |
| Warm Reranker `/score` Latency | - Build 20 and 50 paragraph candidates from sentence FTS. | [数据重建-P4-Reranker-Service-Profile.md](../数据重建-P4-Reranker-Service-Profile.md) |
| Sentence FTS Latency Experiment | Direct SQL variants on the representative query: | [数据重建-P4-Sentence-FTS-Latency.md](../数据重建-P4-Sentence-FTS-Latency.md) |
| Warm Reranker Service | Single-query profile showed: | [数据重建-P4-Warm-Reranker.md](../数据重建-P4-Warm-Reranker.md) |
| P4 句子级 FTS | --- | [数据重建-P4-句子级FTS.md](../数据重建-P4-句子级FTS.md) |
| P4 Sentence-Level FTS Evaluation | --- | [数据重建-P4-句子级FTS评估.md](../数据重建-P4-句子级FTS评估.md) |
| Schema v2：按源类型建模设计 | --- | [数据重建-schema-v2-按源类型建模.md](../数据重建-schema-v2-按源类型建模.md) |
| 文献源与 JATS 结构化导入 | XML 的结构是权威的：<sec> 嵌套、<ref-list>、<fig>、<table-wrap>、 | [文献源-JATS与外部源.md](../文献源-JATS与外部源.md) |
| AI 时代，AI 在什么位置，你又在什么位置？ | --- | [文章-AI协作与项目复盘.md](../文章-AI协作与项目复盘.md) |
| Base 镜像策略 | scipal-base:py312 f301ba576744 | [架构-Base镜像策略.md](../架构-Base镜像策略.md) |
| Build / Ingest 脚本盘点 | services/search/europepmc.py | [架构-Build脚本盘点.md](../架构-Build脚本盘点.md) |
| Papers 相关 Outbox 阻塞 | papers | [架构-Outbox-Papers阻塞.md](../架构-Outbox-Papers阻塞.md) |
| Outbox 收口状态 | watch 表： | [架构-Outbox收口状态.md](../架构-Outbox收口状态.md) |
| SciPal PostgreSQL 单栈架构（G2 决策） | pgvector 是目标主引擎 | [架构-PG单栈架构.md](../架构-PG单栈架构.md) |
| 架构文档 | - 目标系统：Windows 10/11，Python 3.12（venv: venvsciPalpy312） | [架构.md](../架构.md) |
| SciPal 架构与路由全景图 | 配套： | [架构与路由全景图.md](../架构与路由全景图.md) |
| SciPal 架构与路由图 | --- | [架构与路由图.md](../架构与路由图.md) |
| 架构变更授权：P3b library_bench | --- | [架构变更-P3b-bench-library.md](../架构变更-P3b-bench-library.md) |
| 架构变更授权：P4 最终切换 | --- | [架构变更-P4-最终切换.md](../架构变更-P4-最终切换.md) |
| 架构变更授权：P4b 应用连接拆分 | --- | [架构变更-P4b-连接拆分.md](../架构变更-P4b-连接拆分.md) |
| 架构变更授权：P4b2a 写路径归属 | --- | [架构变更-P4b2a-写路径归属.md](../架构变更-P4b2a-写路径归属.md) |
| 架构变更授权：P4b2b1 租户表试点 | --- | [架构变更-P4b2b1-租户表试点.md](../架构变更-P4b2b1-租户表试点.md) |
| 架构变更授权：P4b2b2 项目/实验/Claim 租户表 | --- | [架构变更-P4b2b2-项目实验Claim租户表.md](../架构变更-P4b2b2-项目实验Claim租户表.md) |
| 架构变更授权：P4b2b3 tasks/watch 租户表 | --- | [架构变更-P4b2b3-tasks-watch租户表.md](../架构变更-P4b2b3-tasks-watch租户表.md) |
| 架构变更授权：P4c 撤销 public 写权限 | --- | [架构变更-P4c-撤销public写.md](../架构变更-P4c-撤销public写.md) |
| 架构变更授权：P6 联邦检索 API / MCP | --- | [架构变更-P6-联邦检索API.md](../架构变更-P6-联邦检索API.md) |
| 架构变更授权：P7 客户端入库追踪 | --- | [架构变更-P7-客户端入库追踪.md](../架构变更-P7-客户端入库追踪.md) |
| 环境约束（顶层设计，不可违反） | - 目标系统：Windows 10/11，Python 3.12（venv: venvsciPalpy312） | [架构总览.md](../架构总览.md) |
| 架构耦合检测规则 | --- | [架构耦合检测规则.md](../架构耦合检测规则.md) |
| 架构解耦评估 | --- | [架构解耦评估.md](../架构解耦评估.md) |
| HybridSearch + Rerank: 20-Query Evaluation | HybridSearch candidate path: vector + FTS5 + RRF | [检索-HybridSearch-Rerank-20query.md](../检索-HybridSearch-Rerank-20query.md) |
| Sentence-Level Retrieval Evaluation | paragraph baseline : SQLite paragraphsfts, top 300 paragraphs | [检索-Sentence-Level-评估.md](../检索-Sentence-Level-评估.md) |
| HybridSearch Recall Loss: Missing `paper_id` | HybridSearch.vectorsearch() returned: | [检索-修复HybridSearch丢失paper_id.md](../检索-修复HybridSearch丢失paper_id.md) |
| 检索评估：向量补全后（2026-11-03） | questions 96 | [检索-向量补全后评估-2026-11-03.md](../检索-向量补全后评估-2026-11-03.md) |
| 文档级偏置与冗余：社区方案调研 | 论文/项目不会把“同一文档多段命中”当成优点。 | [检索-文档级偏置方案调研.md](../检索-文档级偏置方案调研.md) |
| 段-句双权重重排：实验设计（暂缓实施） | 在 paragraph FTS 已经给出强基线的前提下，加入一个小权重句子信号，能否提升句子级证据命中，同时不损失论文级排序和 3s SLO？ | [检索-段句双权重实验设计.md](../检索-段句双权重实验设计.md) |
| Retrieval Near-Duplicate Suppression | services/search/dedup.py: | [检索-近重复抑制.md](../检索-近重复抑制.md) |
| 检索优化：社区与论文方案调研 | 当前不需要马上上 Elasticsearch/Milvus。 | [检索优化-社区方案调研.md](../检索优化-社区方案调研.md) |
| SciPal 检索实验报告 | --- | [检索实验报告-2026-11-07.md](../检索实验报告-2026-11-07.md) |
| HybridSearch 20-query Baseline | Raw: | [检索评估-HybridSearch-20query.md](../检索评估-HybridSearch-20query.md) |
| 父子级检索方案调查 | --- | [父子级检索方案调查.md](../父子级检索方案调查.md) |
| SciPal 状态与阈值（2026-11-03） | --- | [状态与阈值-2026-11-03.md](../状态与阈值-2026-11-03.md) |
| 硬件资源与 PG 调优 | CPU Intel Xeon E5-2673 v3 | [硬件资源与PG调优.md](../硬件资源与PG调优.md) |
| 算法设计稿 v0.1：句子滑窗检索 | --- | [算法设计-句子滑窗.md](../算法设计-句子滑窗.md) |
| 1. 表 | reviewprojects(projectid, owner, name, fieldtext, picojson, createdat) | [系统综述工作流.md](../系统综述工作流.md) |
| 生信代码 RAG 计划：补充建议书 | --- | [补充-生信代码RAG-DSH原生检索.md](../补充-生信代码RAG-DSH原生检索.md) |
| 领域覆盖、领域感知路由与主题级惩罚讨论书 | --- | [讨论-领域覆盖与领域感知路由.md](../讨论-领域覆盖与领域感知路由.md) |
| 许可证说明（AGPL-3.0-only） | SPDX-License-Identifier: AGPL-3.0-only | [许可证说明.md](../许可证说明.md) |
| SciPal Paper → Code → Replication 主动科研工作流 v1 | --- | [设计-Paper-to-Code与主动科研工作流-v1.md](../设计-Paper-to-Code与主动科研工作流-v1.md) |
| PostgreSQL Write Path Productionization | --- | [设计-PostgreSQL写路径生产化.md](../设计-PostgreSQL写路径生产化.md) |
| SciPal RAG 控制面设计 v1 | --- | [设计-RAG控制面-v1.md](../设计-RAG控制面-v1.md) |
| SciPal RAG 控制面与科研追溯方案 v1 | --- | [设计-SciPal-RAG控制面与科研追溯-v1.md](../设计-SciPal-RAG控制面与科研追溯-v1.md) |
| SciPal Paper 单篇论文分析插件设计 v1 | --- | [设计-scipal-paper-单篇论文分析插件-v1.md](../设计-scipal-paper-单篇论文分析插件-v1.md) |
| Retrieval SLO and Redundancy Control Design | --- | [设计-检索SLO与冗余控制.md](../设计-检索SLO与冗余控制.md) |
| 证据落地校验（Grounding） | services/qa/grounding.py： | [证据落地校验.md](../证据落地校验.md) |
| 调查总结与明日代码审查重点 | --- | [调查总结与明日代码审查重点.md](../调查总结与明日代码审查重点.md) |
| 领域标签与覆盖评估：开源方案调查报告 | --- | [调研-领域标签与覆盖评估.md](../调研-领域标签与覆盖评估.md) |
| 跨平台路径体检报告 | --- | [跨平台路径体检报告.md](../跨平台路径体检报告.md) |
| DOI 重复组软去重 | 保留两版解析 | [软去重-DOI重复组.md](../软去重-DOI重复组.md) |
| 部署记录：Preflight 入库审计（2026-11-03） | 生产已部署 preflight 预入库审计 | [部署-2026-11-03-Preflight.md](../部署-2026-11-03-Preflight.md) |
| 独立重建库：COPY 级 XML 导入 | --- | [重建库-COPY导入.md](../重建库-COPY导入.md) |
| 零技术债：剩余 49 个 SQLite connect 分类 | --- | [零技术债-剩余49分类.md](../零技术债-剩余49分类.md) |
| 项目简介（可直接复制） | 备用版本： | [项目简介.md](../项目简介.md) |
