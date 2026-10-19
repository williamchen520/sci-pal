# Sci-Pal 文档索引（docs/）

> 项目总说明以仓库根目录的 [`../README.md`](../README.md) 为准（当前 V33.13）。
> 本目录只存放架构、接口、变更记录与图表，避免与根 README 维护两份重复正文。

## 从哪里开始

| 目的 | 文档 |
|------|------|
| 项目是什么、怎么启动、功能概览 | [`../README.md`](../README.md)（根目录，先看） |
| 整体大图、模块边界、环境约束 | [架构总览.md](架构总览.md) |
| 全部函数签名 / 参数 / 返回值 / 异常（写代码时查） | [接口明细.md](接口明细.md) |
| 版本倒序变更记录 | [变更日志.md](变更日志.md) |
| 按月开发记录 | [工作日志/](工作日志/) |
| 给 AI 代码助手的项目说明 | [`../AGENTS.md`](../AGENTS.md) · [`../AI_CONTEXT.md`](../AI_CONTEXT.md) |
| 机器可读架构（程序直接解析） | [`../ARCHITECTURE.json`](../ARCHITECTURE.json) |
| Windows 从零重建 | [`../README-WINDOWS.md`](../README-WINDOWS.md) · [WINDOWS-INSTALL-GUIDE.md](WINDOWS-INSTALL-GUIDE.md) |

## 架构图（HTML，浏览器打开）

| 文件 | 视角 |
|------|------|
| [sci-pal-architecture-v2.html](sci-pal-architecture-v2.html) | 7 层完整系统架构 |
| [sci-pal-dataflow-v2.html](sci-pal-dataflow-v2.html) | 核心数据流（简略） |
| [sci-pal-full-dataflow-with-parsers.html](sci-pal-full-dataflow-with-parsers.html) | 从 PDF 解析到前端的完整数据流 |
| [sci-pal-pdf-parsers-architecture.html](sci-pal-pdf-parsers-architecture.html) | PDF 解析子系统专项 |
| [sci-pal-three-layer-architecture.html](sci-pal-three-layer-architecture.html) | 核心/支撑/体验三层链路与实现状态 |
| [sci-pal-incremental-update-subgraph.html](sci-pal-incremental-update-subgraph.html) | 增量更新 8 步流程与句子关系判定 |

## 说明

- 检索层、综述流程、模型与环境变量的权威描述以根 README.md 与 AGENTS.md 为准。
- 本目录早期曾保留一份完整 README 副本，已改为索引页，防止多处正文版本漂移。
- 历史压缩包、旧版 HTML 副本（带 `(1)` / `- Copy` 后缀）为存档，不代表当前状态。
