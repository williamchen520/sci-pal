# PostgreSQL 单栈迁移计划

> 日期：2026-11-04  
> 目标：彻底退出 SQLite + Chroma 混合架构  
> 原则：先验证、再切换、最后删除；任何阶段不达标就停  
> G0 状态：**已通过（2026-11-04）**，详见 `PostgreSQL迁移-G0-paradedb.md`

---

## 1. 最终目标架构

```text
PostgreSQL
  ├─ 业务表（papers / paragraphs / sentences / citations / ...）
  ├─ pg_search BM25 索引（paragraphs / summaries / sentences）
  ├─ pgvector 向量索引（paragraph / summary / paper）
  ├─ 租户 / 项目 / 审查 / 队列
  └─ 备份 / PITR

应用
  ├─ Flask + gunicorn（PROD_MODE）
  ├─ GPU reranker
  └─ 只连 PostgreSQL

文件
  └─ PDF / XML / 图片对象存储

删除
  ├─ SQLite 运行时
  ├─ FTS5
  ├─ Chroma
  ├─ dual-write outbox
  └─ 27 个 SQLite trigger
```

---

## 2. 当前基线（2026-11-04）

```text
papers / paragraphs / sentences / citations
  PostgreSQL 数据完整，ID 100% 对齐

读路径
  papers list/detail/graph 100% PG
  FTS / Chroma 仍 SQLite/Chroma

写路径
  元数据 PG-primary
  核心表 SQLite mirror + outbox

FTS
  SQLite FTS5 生产
  PG native ts_rank 仅影子
  PG Jaccard .20 / .41，延迟 4–6s

向量
  Chroma

rerank
  GPU RTX 4060，热态 2.7s

测试
  849 tests OK
```

结论：

```text
数据迁移完成
查询面和写入面仍是混合态
原生 PG FTS 不可用，必须引入 BM25 引擎
```

---

## 3. 计划总表

| ID | 阶段 | 工作 | 产出 | 验收 | 预估 |
|---|---|---|---|---|---|
| G0 | 可行性 | ParadeDB / pg_search spike | 对比报告 | 20/96 达标 | 2–3 天 |
| G1 | FTS 切流 | paragraphs/summaries/sentences BM25 | PG BM25 adapter | 96 题不降 | 1–2 周 |
| G2 | 向量切流 | pgvector 替换 Chroma | PG 向量检索 | recall/延迟达标 | 1 周 |
| G3 | 写入单栈 | ingest PG-only | 删除 outbox | pending=0 / trigger=0 | 1 周 |
| G4 | 删除混合层 | 删 SQLite/Chroma 运行时 | 单栈代码 | 只连 PG | 1 周 |
| G5 | P6 归档 | 备份/观察/删除 SQLite | 归档完成 | 30 天无回退 | 1 周 |

总工期：**4–6 周**（单人开发，不含生产观察期）

---

## 4. G0：ParadeDB 可行性 spike

### 目标

```text
验证 PG + ParadeDB BM25 能否替代 SQLite FTS
```

### 任务

| ID | 任务 | 验收 |
|---|---|---|
| G0.1 | 起 paradedb/paradedb 容器 | PG 可连接 |
| G0.2 | 建 `paragraphs` BM25 索引 | `pdb.score` 可查 |
| G0.3 | 建 `summaries` BM25 索引 | 可查 |
| G0.4 | 导入 167k paragraphs | 行数一致 |
| G0.5 | 实现查询 adapter | 20 题可跑 |
| G0.6 | 对比 SQLite / PG native / ParadeDB | 指标表 |
| G0.7 | 延迟测量 | P95 |

### 验收门槛

```text
recall@10  >= 0.6615
nDCG@10    >= 0.5034
P95        <= 2s
```

不达标：

```text
停止，不进入 G1
重新评估 OpenSearch 或接受 SQLite FTS 作为独立搜索层
```

---

## 5. G1：FTS 切流

### 任务

| ID | 任务 | 验收 |
|---|---|---|
| G1.1 | 建 `PGParagraphBM25` | 与 SQLite top20 对齐 |
| G1.2 | 建 `PGSummaryBM25` | summary recall 不降 |
| G1.3 | 建 `PGSentenceBM25` | sentence highlight 可用 |
| G1.4 | query 语法转换 | 支持 AND/OR/短语 |
| G1.5 | 影子双跑 | 20/96 对比 |
| G1.6 | 灰度 10% → 50% → 100% | 回退开关可用 |
| G1.7 | 观察 7 天 | 无召回回退 |

### 验收

```text
96 题 recall / nDCG 不低于基线
FTS 查询 P95 <= 2s
SQLite fallback 仍保留
```

### 回退

```text
SCIPAL_FTS_BACKEND=sqlite
```

---

## 6. G2：pgvector

### 任务

| ID | 任务 | 验收 |
|---|---|---|
| G2.1 | 安装 pgvector 扩展 | `vector` 类型可用 |
| G2.2 | 建 embedding 表 | paragraph/summary/paper |
| G2.3 | 回填 167k paragraphs | 数量一致 |
| G2.4 | HNSW 索引 | 查询可用 |
| G2.5 | 替换 Chroma 查询 | 结果对比 |
| G2.6 | 调参与压测 | P95 达标 |
| G2.7 | 关闭 Chroma | 无运行时依赖 |

### 验收

```text
向量 recall 不低于 Chroma 基线
P95 <= 2s
Chroma 不再被 import
```

---

## 7. G3：写入单栈

### 任务

| ID | 任务 | 验收 |
|---|---|---|
| G3.1 | Ingest 直接写 PG | 入库事务完整 |
| G3.2 | 删除 SQLite mirror 写入 | SQLite 不再被写 |
| G3.3 | 停止 outbox replay | pending 不再增长 |
| G3.4 | 删除 27 个 trigger | trigger=0 |
| G3.5 | 删除 outbox 表 | 无引用 |
| G3.6 | 入库失败回滚 | 无半入库 |

### 验收

```text
新论文只写 PG
SQLite 只读
outbox pending = 0
```

---

## 8. G4：删除混合层

### 任务

| ID | 任务 | 验收 |
|---|---|---|
| G4.1 | 删除 SQLite adapter/FTS5 代码 | 无 import |
| G4.2 | 删除 Chroma 代码 | 无 import |
| G4.3 | 测试 fixture 改 PG | 全绿 |
| G4.4 | 删除 dual-write/shadow 代码 | 无引用 |
| G4.5 | 更新 ARCHITECTURE.json | validate 通过 |
| G4.6 | 更新 README/部署文档 | 单栈说明 |

### 验收

```text
运行时只依赖 PostgreSQL
测试只跑 PG
docker compose 只起 PG + app
```

---

## 9. G5：P6 归档

### 任务

| ID | 任务 | 验收 |
|---|---|---|
| G5.1 | 30 天无回退观察 | 记录完整 |
| G5.2 | SQLite 只读归档 | 不再写 |
| G5.3 | 两份异地备份 | 可恢复 |
| G5.4 | 删除 SQLite 文件 | 不参与运行 |
| G5.5 | 更新架构图/README | 单栈完成 |

### 验收

```text
SQLite 文件删除
备份可恢复
无运行时依赖
```

---

## 10. 时间表

| 周 | 工作 | Gate |
|---|---|---|
| W1 | G0 ParadeDB spike | G0 |
| W2 | G1 BM25 adapter + 影子 | G1 影子 |
| W3 | G1 灰度 + G2 pgvector | G1 完成 |
| W4 | G2 切向量 + G3 写入 | G2/G3 |
| W5 | G4 删除混合层 | G4 |
| W6 | G5 归档 + 文档 | G5 |

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| ParadeDB 兼容性 | 高 | G0 先验证；失败换 OpenSearch |
| BM25 中文/分词 | 高 | 单独评估 tokenizer |
| pgvector 召回下降 | 中 | 保留 Chroma 双跑 |
| 写入单栈丢数据 | 高 | 先 mirror 只读，再切 |
| 测试改造量大 | 中 | 分批 fixture |
| 回滚窗口不足 | 高 | 每个 Gate 保留开关 |

---

## 12. 回退策略

```text
G0 失败 -> 不进入 G1
G1 失败 -> SCIPAL_FTS_BACKEND=sqlite
G2 失败 -> 保留 Chroma
G3 失败 -> 恢复 SQLite mirror 写
G4 失败 -> 恢复上一版镜像
```

任何阶段不删除 SQLite，直到 G5。

---

## 13. 完成定义（DoD）

```text
[ ] 运行时只连 PostgreSQL
[ ] FTS 由 PG BM25 提供
[ ] 向量由 pgvector 提供
[ ] 无 SQLite 读写
[ ] 无 Chroma 依赖
[ ] 无 outbox/trigger
[ ] 849+ tests 全绿
[ ] 96 题指标不低于基线
[ ] 备份/PITR 验证
[ ] PROD_MODE gunicorn 可部署
[ ] README 单栈说明
```

---

## 14. 立即下一步

```text
1. 起 ParadeDB 容器
2. 建 paragraphs BM25 索引
3. 跑 q001–q020 对比
4. 出 G0 报告
5. 再决定是否进入 G1
```

当前生产保持：

```text
SQLite FTS + PG 元数据 + GPU rerank
```

不因计划推进而中断。
