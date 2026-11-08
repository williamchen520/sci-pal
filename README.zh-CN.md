# SciPal — 检索增强的科研工作台

> **状态：开发中 / PG-only。** 尚无稳定版本。  
> 不要用于临床或受监管决策。

[English](README.md) | **简体中文**

SciPal 是一个可本地部署的科研系统，用于文献检索、结构化证据抽取、系统综述与可追溯写作。核心是确定性检索层：pgvector 向量召回、PostgreSQL 全文检索、RRF 融合、cross-encoder 重排与上下文扩展。

生成层可选、可插拔：小模型做编排，云端或 DSH 做推理。

---

## 架构

```text
浏览器 / DSH
    │ HTTP / MCP
    ▼
Flask API（26 个蓝图，186 条路由）
    │
    ├─ services/search        pgvector + PG FTS + RRF + rerank
    ├─ services/review        综述 + 系统综述
    ├─ services/claims        claim card + 证据
    ├─ services/projects      项目 / 实验 / 运行
    ├─ services/watch         文献监测 + 简报
    └─ build_db/*             解析、JATS 导入、PG 写入
    │
    ▼
PostgreSQL 16 + pgvector
    + documents/（PDF / XML）
    + packs/
```

已退出运行路径：

```text
SQLite research.db    已归档，不挂载，不创建
Chroma                已归档，不初始化
```

---

## 技术栈

| 层 | 选型 |
|---|---|
| 运行时 | Python 3.12，Flask 3 |
| 主存储 | PostgreSQL 16 |
| 向量 | pgvector + HNSW |
| 全文 | PostgreSQL GIN `tsvector`；可选 ParadeDB |
| Embedding | `BAAI/bge-base-en-v1.5` |
| 重排 | `BAAI/bge-reranker-base` |
| 解析 | PyMuPDF、Docling、GROBID、MinerU、JATS XML |
| 生成 | OpenAI 兼容云 API、Ollama、DSH 可选 |
| 前端 | 原生 HTML/CSS/JS + PDF.js |
| 部署 | Docker Compose：app + watch-cron + Caddy + PostgreSQL |

---

## 当前数据

| 项 | 数值 |
|---|---:|
| papers | 10,102 |
| paragraphs | 331,263 |
| sentences | 1,492,661 |
| sections | 124,216 |
| paragraph embeddings | 320,928 |
| summaries | 69,128 |
| HNSW 索引 | 1.235 GB，valid |
| PostgreSQL 体积 | 约 5.4 GB |

归档：

```text
research.db   I:\_archive\research.db-20261107
Chroma        I:\_archive\chroma-20261107
```

---

## 能力

| 能力 | 说明 |
|---|---|
| 文献检索 | pgvector + PG FTS，RRF，重排，章节扩展 |
| 结构化解析 | 多 PDF 引擎 + 原生 JATS XML |
| 章节/段落/句子树 | 明确 ID、页码、bbox |
| 引用/图/表链接 | 句子级溯源 |
| 句子溯源 | `/api/papers/<id>/trace`，页面裁剪 |
| 证据包 | 父上下文 + 命中句 + 链接 |
| RAG 问答 | 引用、拒答、本地或云端模型 |
| 综述生成 | 大纲 → 章节检索 → 起草 → 校验 |
| 系统综述 | 筛选、PRISMA、证据、偏倚、报告 |
| Claim | claim card、限定词、支持/反驳证据 |
| 项目/实验 | 成员、运行、修订、审计、签名 |
| 文献监测 | profile、期刊、运行、简报 |
| 多用户隔离 | 用户、工作区、角色 |
| 领域包 | 分类法/章节类型/证据 schema |
| 插件 | 入库追踪、端口、GraphRAG/RAPTOR 实验 |

---

## 快速开始

### Docker Compose

```bash
cp deploy/.env.example deploy/.env
# 修改 SCIPAL_PG_DSN、SCIPAL_SECRET_KEY
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1/api/health
```

服务：

```text
app         Flask API
postgres    PostgreSQL 16 + pgvector
watch-cron  文献监测调度
caddy       反向代理
```

### 本地开发

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set SCIPAL_PG_DSN=postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench
python api_server.py
```

开发服务器仅用于开发。生产：

```text
APP_MODE=PROD_MODE -> gunicorn
```

---

## 配置

必需：

```text
SCIPAL_PG_DSN=postgresql://user:pass@host:5432/scipal_bench
SCIPAL_SECRET_KEY=<random>
```

PG-only 默认：

```text
SCIPAL_VECTOR_BACKEND=pgvector
SCIPAL_FTS_BACKEND=postgres
SCIPAL_SEARCH_META_BACKEND=postgres
SCIPAL_SQLITE_QUERY_ONLY=1
SCIPAL_ABSTRACTS_BACKEND=postgres
SCIPAL_PROJECTS_BACKEND=postgres
SCIPAL_RUNS_BACKEND=postgres
SCIPAL_EXPERIMENTS_BACKEND=postgres
SCIPAL_REVIEWS_BACKEND=postgres
SCIPAL_SYSTEMATIC_BACKEND=postgres
SCIPAL_CLAIMS_BACKEND=postgres
SCIPAL_NOTES_BACKEND=postgres
SCIPAL_TASKS_BACKEND=postgres
SCIPAL_PAPERS_READ_BACKEND=postgres
SCIPAL_INGEST_PG_ONLY=1
SCIPAL_TENANCY_PG_ONLY=1
```

鉴权：

```text
SCIPAL_AUTH_REQUIRED=1
```

---

## API 示例

```bash
curl http://127.0.0.1/api/health

curl -X POST http://127.0.0.1/api/evidence/search \
  -H "Content-Type: application/json" \
  -d '{"query":"hepatocellular carcinoma","top_paragraphs":5}'

curl "http://127.0.0.1/api/papers?limit=5"
```

主要路由：

```text
/api/papers
/api/search
/api/evidence
/api/qa
/api/reviews
/api/review-projects
/api/projects
/api/experiments
/api/claims
/api/watch
/api/workspaces
/api/tasks
```

---

## 目录

```text
api_server.py              Flask 入口与蓝图注册
routes/                    26 个蓝图
services/                  检索、综述、claim、项目、监测等
build_db/                  解析、JATS 导入、PG 写入
plugins/                   可选插件
frontend/                  HTML/CSS/JS
docs/                      架构、迁移、运维
scripts/                   烟测、审计、回填
deploy/                    Dockerfile、compose、env
tests/                     pytest
```

---

## 测试

```bash
pytest

python scripts/smoke_http.py        # A 组 31 条
python scripts/smoke_group_b.py     # B 组 14 条
python scripts/smoke_group_c.py     # C 组 5 条
```

当前：

```text
50 条路由 / 0 个 5xx
research.db absent
```

检索：

```text
20 题回归       Recall@10 0.675 / nDCG@10 0.461
SciFact 300     Recall@10 0.8669 / nDCG@10 0.7458
```

---

## 已知限制

```text
12 组不同 PMCID 的同名文章尚未合并
300 题全文金标延期
GraphRAG / RAPTOR 仍是插件实验
客户端入库追踪尚未接真实导入 UI
基础镜像仍含 chromadb 包（运行不用）
部分冷门 POST 端点未进入自动烟测
```

---

## 文档

| 文档 | 用途 |
|---|---|
| [架构与路由图](docs/架构与路由图.md) | 系统数据流与路由 |
| [开发-模块手册](docs/开发-模块手册.md) | 模块职责与入口 |
| [PG-only 总报告](docs/PG-only迁移总报告-2026-11-08.md) | 迁移决策与验证 |
| [ARCHITECTURE.json](ARCHITECTURE.json) | 机器可读架构 |
| [分层烟测计划](docs/全站端点分层烟测计划.md) | 端点测试 |

---

## 许可证

见 [LICENSE](LICENSE)。
