# PG-only 彻底收尾计划表

> 日期：2026-11-07  
> 目标：从“向量 PG-only”走到“运行时不依赖 Chroma / SQLite”  
> 原则：先切断、再迁移、最后删数据

---

## 1. 两个不同层次

### A. Chroma 残余清理

```text
代码分支
构建脚本
依赖
镜像
数据
文档
```

可在 2–3 天完成。

### B. SQLite 业务读路径迁移

```text
research.db 仍被部分服务读取
query_only 只保证不写，不等于 PG-only
```

这是第二轮迁移，约 1–2 周，不应混在“清扫”里。

---

## 2. 总表

| ID | 优先级 | 工作 | 对象 | 验收 |
|---|---|---|---|---|
| A1 | P0 | 关闭 abstract FTS | `AbstractSearch.search` | PG-only 下返回空 |
| A2 | P0 | 删除 Chroma 死分支 | summary/online/api embed | 无 chromadb 调用 |
| A3 | P1 | build 脚本默认 PG | `build_embeddings.py` 等 | 默认不建 Chroma |
| A4 | P1 | 重建 base 镜像 | `Dockerfile.base` | 镜像内无 chromadb |
| A5 | P1 | 清理空目录/数据 | `abstracts.db`、empty dirs | 归档后删除 |
| A6 | P2 | 文档/测试更新 | README/架构/test | 不再把 Chroma 当主路径 |
| B1 | P0 | SQLite 读路径盘点 | `DB_PATH` 全部引用 | 清单 + 归属 |
| B2 | P1 | 逐模块迁 PG | tenancy/projects/experiments/runs/watch/review/papers | 模块无 SQLite 读 |
| B3 | P1 | 测试改 PG | tests | 无 SQLite fixture |
| B4 | P2 | 归档 research.db | data/research.db | 运行不挂载 |
| C1 | P0 | 最终验收 | 全系统 | 无 Chroma/SQLite 运行时连接 |

---

## 3. Phase A：Chroma 收尾

### A1 关闭 abstract FTS

问题：

```text
AbstractSearch.vector_search -> [] （已关）
AbstractSearch.fts_search    -> 仍读 abstracts.db
```

动作：

```text
PG-only 下 AbstractSearch.search 直接返回 []
或整体不实例化
```

验收：

```text
abstract 搜索接口返回空/410
不打开 abstracts.db
```

### A2 删除 Chroma 死分支

对象：

```text
api_server.get_embed_rows
services/search/online_downloader.py 的 Chroma 分支
services/search/summary_vector_search.py 的 Chroma 分支
services/search/ingest.py 的 Chroma 分支
```

动作：

```text
PG-only 路径删除
legacy 分支要么删除，要么移到 plugins/legacy
```

验收：

```text
运行时代码无 chromadb import
```

### A3 构建脚本

对象：

```text
build_db/build_embeddings.py
build_db/build_chunks.py
build_db/build_contextual_paragraph_index.py
build_db/build_summary_vector_index.py
build_db/build_figure_table_vectors.py
```

动作：

```text
默认 PG
Chroma-only 脚本标记 legacy
```

验收：

```text
默认命令不创建 Chroma 目录
```

### A4 base 镜像

问题：

```text
当前 app 镜像 base 层仍有 chromadb
```

动作：

```text
重建 scipal-base:py312
重新构建 app
```

验收：

```text
docker run --rm scipal-app python -c "import chromadb" 失败
```

### A5 数据清理

对象：

```text
data/abstracts.db
data/chroma_abstracts.empty-*
```

动作：

```text
先归档 I 盘
确认无读后删除
```

### A6 文档/测试

对象：

```text
README.md
README.zh-CN.md
docs/架构.md
docs/架构总览.md
docs/en/Architecture-Overview.md
tests/test_hybrid_filter.py
tests/test_summary_vector.py
```

动作：

```text
更新架构图
删除 Chroma 主路径描述
测试改为 PG-only 断言
```

---

## 4. Phase B：SQLite 读路径

### B1 盘点

按模块统计 `DB_PATH` / `research.db`：

```text
api_server.py
services/tenancy
services/projects
services/experiments
services/review
services/watch
routes/papers_actions
```

输出：

```text
模块 -> 表 -> 读/写 -> 是否已 PG -> 迁移难度
```

### B2 迁移顺序

```text
1. tenancy
2. projects
3. experiments / runs
4. watch
5. review
6. papers_actions
7. 剩余 route
```

原则：

```text
一个模块一个 PR
先读后写
保持 baseline 不变
```

### B3 测试

```text
去掉 SQLite fixture
改为 PG test schema
```

### B4 归档

```text
research.db 只读快照
确认无连接后归档/删除
```

---

## 5. 最终验收

```text
1. 启动日志无 chromadb
2. 运行进程无 Chroma 连接
3. 运行进程无 research.db 连接
4. 镜像无 chromadb 包
5. 数据目录无 chroma/abstracts.db
6. 20 题指标不退化
7. 10k 检索正常
8. 备份/恢复通过
```

---

## 6. 时间

```text
Phase A  2–3 天
Phase B  5–10 天
最终验收 0.5 天
```

单开发者约 1–2 周。

---

## 7. 风险

```text
B 阶段范围被低估
模块间通过 SQLite 共享状态
测试 fixture 大量依赖 SQLite
base 重建引入依赖漂移
```

缓解：

```text
A 先完成，立即降低复杂度
B 按模块切，不一次性删库
每步保留 PG 对照
```

---

## 8. 结论

```text
A 是清扫，先做
B 是迁移，单独排期
```

“彻底收尾”不是删两个目录：

```text
Chroma 收尾靠删代码/镜像/数据
SQLite 收尾靠逐模块迁读路径
```

两条都完成，才叫运行时 PG-only。
