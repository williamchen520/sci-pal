# SciPal — 检索增强的科研工作台

> **状态：开发中 / PG-only。** 尚无稳定版本。  
> 不要用于临床或受监管决策。

[English](README.md) | **简体中文**

SciPal 是一个可本地部署的科研系统，用于文献检索、结构化证据抽取、系统综述与可追溯写作。核心是确定性检索层：pgvector 向量召回、PostgreSQL 全文检索、RRF 融合、可选 cross-encoder 重排，以及按句子编号的上下文扩展。

生成层可选、可插拔：小模型做编排，云端或 DSH 模型做推理。

---

## 架构

```text
浏览器 / DSH / MCP
        │
        ▼
      Caddy
        │  HTTPS、安全头
        ▼
   Flask API（26 蓝图，204 route+method；开启 ingest-tracking 后 210）
        │
        ├── scipal_core
        │     用户 / 鉴权 / 工作区 / 项目 / 实验
        │     笔记 / 任务 / claim / 综述 / 审计
        │
        └── scipal_rebuild
              论文 / 章节 / 段落 / 句子
              向量 / 引用 / 图 / 表
```

检索：

```text
pgvector HNSW + PostgreSQL GIN FTS + RRF
句子级证据
句子窗口上下文
```

运维：

```text
worker          长任务
pg-backup       加密 PostgreSQL 备份
watch-cron      文献监测
```

数据归属是物理隔离，不是命名约定：

```text
core 与 corpus 是两个独立 PostgreSQL 数据库
没有跨库外键
只用逻辑 ID（paper_id / user_id）
业务读路径不碰语料库
语料读路径不碰业务库
```

---

## 当前数据

| 项目 | 数量 |
|---|---:|
| 论文 | 13,201 |
| 段落 | 410,270 |
| 句子 | 1,780,306 |
| 章节 | 156,208 |
| 段落向量 | 343,546 |
| HNSW 索引 | 1.326 GB，valid |
| PostgreSQL（rebuild） | 约 5.5 GB |

---

## 能力

| 能力 | 说明 |
|---|---|
| 文献检索 | pgvector + PG FTS + RRF + 可选 rerank |
| 结构化解析 | 多 PDF 引擎 + 原生 JATS XML |
| 句子溯源 | `/api/papers/<id>/trace`，page/bbox |
| 证据包 | 命中句 + 父级上下文 + 链接 |
| RAG 问答 | 引用、拒答、本地或云端模型 |
| 综述生成 | 大纲 → 章节检索 → 写作 → 校验 |
| 系统综述 | 筛选、PRISMA、证据、风险偏倚 |
| Claim | claim 卡、限定词、支持/反对证据 |
| 项目 / 实验 | 成员、运行、修订、审计 |
| 文献监测 | profile、期刊、运行、简报 |
| 多用户隔离 | 用户、工作区、角色、最小权限 DSN |
| 领域包 | 分类、章节类型、证据 schema |
| 可选插件 | ingest tracking、实验性 GraphRAG/RAPTOR |

---

## 安全与运维

```text
全局 API 鉴权         session / bearer / 内部服务 token
内部端点              /api/ingest、/api/embed 需要内部 token
数据库角色            core_app / corpus_reader / corpus_writer（无 DDL）
环境守卫              生产拒绝 loopback / 错库 DSN
备份                  core 每 6h（保留 7d），corpus 每 7d（保留 28d）
备份加密              AES-256-CBC + PBKDF2，文件 600
恢复演练              数据 + GIN + HNSW，2026-11-12 通过
治理门禁              高风险 PR 需要人类批准
```

不要把生产凭据提交到 git。

---

## 快速开始

### Docker Compose

```bash
cp deploy/.env.example deploy/.env
# 配置 DSN、SCIPAL_SECRET_KEY、备份 passphrase
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1/api/health
```

必需 DSN：

```text
SCIPAL_CORE_DSN            -> scipal_core（业务/鉴权）
SCIPAL_AUTH_DSN            -> scipal_core（auth schema）
SCIPAL_PG_DSN              -> scipal_core（兼容默认）
SCIPAL_PG_CORPUS_DSN       -> scipal_rebuild（读）
SCIPAL_PG_MAIN_READ_DSN    -> scipal_rebuild（读）
SCIPAL_PG_OWNER_DSN        -> scipal_rebuild（写，无 DDL）
SCIPAL_PG_INGEST_DSN       -> scipal_rebuild（入库写）
```

服务：

```text
app         Flask API
postgres    PostgreSQL 16 + pgvector
pg-backup   加密备份
watch-cron  文献监测
caddy       反向代理 / TLS
```

### 本地开发

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
# 配置 .env 或环境变量
python api_server.py
```

仅用于开发。生产使用 `APP_MODE=PROD_MODE` + gunicorn。

---

## 测试

```bash
python -m unittest discover -s tests -p "test_*.py"
python scripts/smoke_http.py        # A：27 个轻量 GET
python scripts/smoke_group_b.py     # B：13 个中等 GET
python scripts/check_data_boundary.py
python scripts/validate_arch.py
```

当前 smoke：

```text
A 27/27 200
B 13/13 200
```

路由计数：

```text
26 蓝图 / 204 route+method（默认）
27 蓝图 / 210 route+method（SCIPAL_INGEST_TRACKING=1）
```

已记录的检索结果：

```text
SciFact 300        Recall@10 0.8669 / nDCG@10 0.7458
rebuild_20 hybrid  Recall@10 0.7000 / nDCG@10 0.4894
```

---

## 配置

PG-only 默认：

```text
SCIPAL_VECTOR_BACKEND=pgvector
SCIPAL_FTS_BACKEND=postgres
SCIPAL_SEARCH_META_BACKEND=postgres
SCIPAL_PAPERS_READ_BACKEND=postgres
SCIPAL_INGEST_PG_ONLY=1
SCIPAL_TENANCY_PG_ONLY=1
SCIPAL_AUTH_REQUIRED=1
SCIPAL_ENV=production
```

鉴权相关：

```text
SCIPAL_AUTH_DSN
SCIPAL_INTERNAL_TOKEN
SCIPAL_INTERNAL_USER_ID
SCIPAL_INTERNAL_WORKSPACE_ID
```

备份：

```text
SCIPAL_BACKUP_PASSPHRASE
```

不要提交真实值。

---

## 目录

```text
api_server.py              Flask 入口与蓝图注册
routes/                    26 个蓝图
services/                  search、review、claims、projects、watch...
services/db/               连接工厂、环境守卫、连接池
eval/                      检索/问答评估、公共数据集 loader
build_db/                  解析、JATS 导入、PG 写入
plugins/                   可选插件
frontend/                  HTML/CSS/JS
docs/                      架构、迁移、运维、研究
scripts/                   smoke、审计、回填、治理门禁
deploy/                    Dockerfile、compose、env、SQL
tests/                     unittest/pytest
config/                    治理门禁配置
```

---

## 文档

| 文档 | 用途 |
|---|---|
| [架构与路由](docs/架构与路由全景图.md) | 路由、分层、数据流 |
| [开发-模块手册](docs/开发-模块手册.md) | 模块职责与入口 |
| [ARCHITECTURE.json](ARCHITECTURE.json) | 机器可读契约 |
| [数据层隔离审计](docs/数据层隔离审计.md) | 表/DSN 归属 |
| [备份策略](docs/备份策略-双库.md) | 备份与恢复 |
| [恢复演练 2026-11-12](docs/恢复演练-20261112.md) | 数据 + GIN + HNSW 验证 |
| [代码审查 2026-11-12](docs/代码审查-20261112.md) | P0/P1 findings |
| [工程治理门禁](docs/工程治理门禁规范.md) | 预检与批准 |
| [公共测试集选型](docs/公共测试集选型.md) | SciFact / LitQA2 / QASPER |

---

## 已知限制

```text
LitQA2 本地 82/199 可评估
QASPER 证据是段落级，不是句级
SciFact claim 的全文 benchmark 还没有
GraphRAG / RAPTOR 仍是实验，不在核心路径
客户端 ingest tracking 需要单独迁移
无稳定版本；API 和 schema 可能变化
```

---

## License

见 [LICENSE](LICENSE)。
