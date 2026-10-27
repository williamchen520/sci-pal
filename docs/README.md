# SciPal 文档索引（docs/）

> 项目总说明以仓库根目录的 [`../README.md`](../README.md) 为准（当前 V33.41）。
> 本目录存放架构、接口、变更记录与设计文档，避免与根 README 维护两份重复正文。

## 从哪里开始

| 目的 | 文档 |
|------|------|
| 项目是什么、怎么启动、功能概览 | [`../README.md`](../README.md)（根目录，先看） |
| 架构、模块、82 条路由与数据流图 | [架构与路由图.md](架构与路由图.md) · [芯片架构图](图-SciPal芯片架构.png) |
| PDF 三引擎解析设计 | [PDF解析-三引擎联合.md](PDF解析-三引擎联合.md) |
| JATS 导入与外部文献源 | [文献源-JATS与外部源.md](文献源-JATS与外部源.md) |
| 文献监测 / 上下文 / DSH 设计 | [设计-文献监测-上下文-DSH.md](设计-文献监测-上下文-DSH.md) |
| 阶段性总结 | [阶段性总结-20261027.md](阶段性总结-20261027.md) |
| 全部函数签名 / 参数 / 返回值 | [接口明细.md](接口明细.md) |
| 版本倒序变更记录 | [变更日志.md](变更日志.md) |
| DSH 定时监测任务示例 | [DSH-定时监测任务.md](DSH-定时监测任务.md) |
| 给 AI 代码助手的项目说明 | [`../AGENTS.md`](../AGENTS.md) · [`../AI_CONTEXT.md`](../AI_CONTEXT.md) |
| 机器可读架构 | [`../ARCHITECTURE.json`](../ARCHITECTURE.json) |

## 说明

- 早期 HTML/JPG/PDF 架构图与数据流图（sci-pal-architecture、sci-pal-dataflow 等）已删除，
  统一以 [架构与路由图.md](架构与路由图.md) 为准（Mermaid，Gitee 可直接渲染）。
- 检索层、综述流程、模型与环境变量的权威描述以根 README.md 与 AGENTS.md 为准。
- 历史工单、验收报告保留作为过程记录，不代表当前实现。
