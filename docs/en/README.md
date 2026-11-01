# SciPal Documentation (English)

**English** | [简体中文](../README.md)

This directory contains the English editions of SciPal's core architecture, routing, API, and planning documents. The Chinese documents under `docs/` remain the canonical engineering record; the English pages are maintained as a faithful translation for international contributors and reviewers.

## Start Here

| Topic | Document |
|---|---|
| Project overview, quick start, and feature list | [README](../../README.md) |
| System layers, modules, and data flow | [Architecture Overview](Architecture-Overview.md) |
| Routes, services, database, and end-to-end flows | [Architecture and Routes](Architecture-and-Routes.md) |
| Function signatures, parameters, and callers | [API Reference](API-Reference.md) |
| PostgreSQL migration: ETL, dual-write, and read canary | [PostgreSQL Migration Plan](plans/PostgreSQL-Migration.md) |
| Users, workspaces, roles, and data isolation | [Multi-User and Data Isolation](plans/Multi-User-and-Data-Isolation.md) |
| Domain packs, taxonomy, and distribution | [Domain Packs and Distribution](plans/Domain-Packs-and-Distribution.md) |
| Plugin ports and comparative benchmarks | [Plugin Ports and Benchmarks](plans/Plugin-Ports-and-Benchmarks.md) |
| From review generation to an auditable claim–evidence workbench | [Argument Workbench](plans/Argument-Workbench.md) |
| Adaptive retrieval, weekly digests, and literature intelligence | [Adaptive Retrieval and Literature Intelligence](plans/Adaptive-Retrieval-and-Literature-Intelligence.md) |
| DSH integration, MCP tools, and plugin UI | [DSH Integration and Plugins](plans/DSH-Integration-and-Plugins.md) |
| Projects, experiments, ELN runs, audit, and signatures | [Project Tracking and ELN](plans/Project-Tracking-and-ELN.md) |

## Translation Policy

- Markdown only. Source code, Python comments, SQL, and inline code identifiers are **not** translated.
- Code blocks, commands, API routes, paths, table layouts, Mermaid node IDs, and technical identifiers are preserved.
- Chinese source documents are authoritative. If an English page diverges, open an issue and update both.
- English prose follows North American spelling and common open-source terminology.
- Some runtime output strings remain in Chinese because they are emitted verbatim by the application. They are shown in backticks and should not be translated in code without changing the program.

## Maintenance

When a core Chinese document changes:

1. Update the Chinese source first.
2. Update the corresponding English page in the same pull request when the change affects public behavior, APIs, or architecture.
3. Keep headings and tables aligned so reviewers can diff the two editions.
4. Link new English pages from this index and from the root [README](../../README.md).

## Chinese Editions

- [Chinese documentation index](../README.md)
- [Architecture overview](../架构总览.md)
- [Architecture and routes](../架构与路由图.md)
- [API reference](../接口明细.md)
- [PostgreSQL migration plan](../工作计划-PostgreSQL迁移.md)
- [Multi-user and data isolation](../工作计划-多用户与数据隔离.md)
- [Domain packs and distribution](../工作计划-去学科化与领域包分发.md)
- [Plugin ports and benchmarks](../工作计划-插件端口与对比评测.md)
- [Argument workbench](../工作计划-论证工作台改造.md)
- [Adaptive retrieval and literature intelligence](../工作计划-自适应与文献情报.md)
- [DSH integration and plugins](../工作计划-DSH适配与插件化.md)
- [Project tracking and ELN](../工作计划-项目跟踪与实验记录.md)
