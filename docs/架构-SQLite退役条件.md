# 架构：SQLite 退役条件与当前数据权威源

> 日期：2026-11-02  
> 结论：**SQLite 尚未退役，仍是生产运行库。**

## 1. 为什么需要这份文档

过去几轮完成了：

```text
paper 读路径 -> PostgreSQL
tenancy 写路径 -> PostgreSQL primary + SQLite mirror
```

但这不等于 SQLite 已停用。实际生产中，多个关键能力仍在 SQLite 上：

```text
paragraph FTS
papers / watch 写入
outbox
部分业务表
```

这份文档固定当前事实，避免把“部分迁移”误认为“完全退役”。

## 2. 当前数据权威源

| 能力 | 当前权威源 | 说明 |
|---|---|---|
| paper 列表 / detail / graph | PostgreSQL | 读路径已切 |
| tenancy 读 | PostgreSQL | `SCIPAL_TENANCY_READ_BACKEND=postgres` |
| tenancy 写 | PostgreSQL primary | SQLite 保留 mirror |
| papers 写 | SQLite primary | 经 outbox 复制到 PG |
| watch 业务写 | SQLite primary | 经 outbox 复制到 PG |
| watch run 结束 | SQLite -> outbox -> PG | `SCIPAL_WATCH_WRITE_BACKEND=postgres` 时主动 catch-up |
| paragraph FTS | **SQLite FTS5** | 生产排序仍用它 |
| sentence FTS | PostgreSQL `scipal_v2` | 仅评估，不生产 |
| Chroma 向量 | 本地 Chroma | 独立于 SQLite/PG |
| 文件 / XML / PDF | 本地文件系统 | 不在数据库 |

生产环境变量：

```text
SCIPAL_TENANCY_READ_BACKEND=postgres
SCIPAL_TENANCY_WRITE_BACKEND=postgres
SCIPAL_WATCH_WRITE_BACKEND=postgres
SCIPAL_PAPER_WRITE_BACKEND 未开启
```

## 3. 为什么 SQLite 还不能停

### 3.1 检索仍依赖 SQLite FTS5

`HybridSearch` 和 paragraph 检索直接连接：

```text
config.paths.DB_PATH -> data/research.db
```

查询：

```text
paragraphs_fts
sentences_fts
```

当前生产排序：

```text
paragraph FTS
```

没有等价的 PG 生产路径，所以停 SQLite 会直接停检索。

### 3.2 写路径还有 SQLite primary

papers / watch 的写入仍是：

```text
SQLite transaction
-> trigger / outbox
-> replay to PG
```

`SCIPAL_PAPER_WRITE_BACKEND` 默认关闭，watch 也只是 run 后 catch-up。停 SQLite 会丢写入入口。

### 3.3 tenancy 还有 SQLite mirror

tenancy 已 PG-primary，但 SQLite mirror 仍用于：

```text
旧读路径兼容
故障回退
drift 检查
```

在删除 mirror 前，需要先删除所有 SQLite fallback 读。

## 4. SQLite 退役的分阶段条件

### Phase A：检索切 PG

必须先满足：

```text
PG FTS 与 paragraph FTS 同指标
  Recall@10 1.0000
  MRR >= 0.8806
  nDCG@10 >= 0.9097
p95 <= 3s
gold sentence 不低于当前 paragraph 基线
```

当前不满足：

```text
sentence FTS MRR 0.6250
sentence FTS p95 24.92s
```

所以 Phase A 未开始。

### Phase B：papers 写路径 PG-primary

条件：

```text
ingest metadata 不再依赖 outbox
workspace assignment 已 PG-primary
outbox pending = 0 连续 7 天
SQLite/PG paper drift = 0
```

当前：workspace 已 opt-in，但未开启；ingest 仍是 best-effort。

### Phase C：watch 写路径 PG-primary

条件：

```text
watch_profiles/runs/items/seen 写入 PG-primary
不再需要 run 后 catch-up
outbox pending = 0 连续 7 天
watch 真实 run 连续成功
```

当前：仍 SQLite primary + catch-up。

### Phase D：tenancy mirror 删除

条件：

```text
所有 tenancy 读不再 fallback SQLite
mirror drift = 0 连续 7 天
回滚演练通过
```

当前：mirror 保留。

### Phase E：停 SQLite

只有 A-D 全部完成，且：

```text
备份/恢复演练通过
PG 监控/告警覆盖
一次完整回滚演练
```

才能讨论停 SQLite。

## 5. 当前明确不能做的事

```text
不能因为 paper 读路径在 PG，就删 SQLite
不能把 SQLite mirror 当作权威源
不能把 sentence_id 跨库直接 join
不能用 SQLite 做 >100 篇并发基准
```

## 6. sentence_id 不一致的定位

这不是 SQLite 退役问题，而是两套库同时运行时的 ID 稳定性问题：

```text
SQLite XML  ..._00015_sent_001
PG v2 XML    ..._00016_sent_001
SQLite PDF   ..._para_..._sent_005
PG v2 PDF    sent_..._001104
```

17/17 gold sentence 文本相同，0/17 ID 相同。

详见：[数据-句子ID不一致.md](数据-句子ID不一致.md)

## 7. 结论

```text
PostgreSQL：读路径 + tenancy 写的权威源
SQLite：检索 + 写入队列 + 部分业务数据的运行库
```

SQLite 不是“已停止采用”，而是“部分领域已迁出、尚未退役”。

在 Phase A-D 完成前，任何“SQLite 已停用”的说法都是错误的。
