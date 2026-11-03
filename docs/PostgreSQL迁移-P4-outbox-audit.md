# P4 Outbox 审计（开发态）

> 日期：2026-11-03  
> 模式：只读，未修改 SQLite / PG  
> 结论：**P4 开发态冻结，不删除核心表 trigger**

## 1. 实测

```text
pending              0
failed               0
oldest_pending       null
triggers             27
status               ok
```

行数：

| table | SQLite | PostgreSQL | match |
|---|---:|---:|---|
| papers | 3313 | 3313 | yes |
| sections | 69128 | 69128 | yes |
| paragraphs | 167388 | 167388 | yes |
| sentences | 862677 | 862677 | yes |
| figures | 13471 | 13471 | yes |
| tables | 4922 | 4922 | yes |
| citations | 182817 | 182817 | yes |
| sentence_links | 296951 | 296951 | yes |
| paper_links | 164802 | 164802 | yes |

Tenancy：

```text
users        sqlite=1  postgres=1  drift=false
workspaces   sqlite=1  postgres=1  drift=false
memberships  sqlite=2  postgres=2  drift=false
```

## 2. 为什么不能删 27 个 trigger

剩余 trigger 在核心数据表：

```text
papers
sections
paragraphs
sentences
figures
tables
citations
sentence_links
paper_links
```

这些表的 SQLite 镜像仍被：

```text
SQLite FTS5 / BM25
legacy retrieval
evidence / paragraph 读取
```

使用。

如果直接删除 trigger：

```text
SQLite 继续被写
outbox 不再入队
PG 不再同步
→ SQLite / PG 数据分叉
```

因此不能“一键删 trigger”。

## 3. 当前实际状态

```text
tenancy 写路径      PG-primary，无 outbox trigger
watch/projects/...  PG-primary
核心数据表          SQLite mirror + outbox -> PG
outbox pending      0
```

结论：

```text
P4 不是“完全关闭”
P4 是“核心表保留 mirror/outbox，元数据已 PG-primary”
开发态接受该混合态
```

## 4. 开发态决定

```text
保留 27 个 dualwrite trigger
保留 outbox 表与历史行
不删除 SQLite 核心表
不执行 P6 归档
pending > 0 或 drift 时再处理
```

## 5. 生产态再评估

上服务器前再决定：

```text
是否把 FTS 也切到 PG
是否停止核心表 SQLite mirror
是否关闭 outbox
是否执行 P6
```

这些都需要单独的迁移计划和回滚方案，不在开发态执行。
