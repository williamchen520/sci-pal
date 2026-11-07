# research.db 读路径盘点

> 日期：2026-11-07  
> 目的：B1 盘点，为逐模块 PG 迁移提供清单  
> 结论：写入多已 PG，读路径仍大量 SQLite

---

## 1. 现状

```text
research.db   1.75 GB
表            91（含 FTS shadow）
journal       DELETE
运行模式      query-only
```

`query_only` 只保证不写，不保证已迁 PG。

---

## 2. 表规模

| 表 | 行数 |
|---|---:|
| sentences | 862,677 |
| sentence_links | 296,951 |
| citations | 182,817 |
| paragraphs | 167,388 |
| paper_links | 164,802 |
| sections | 69,128 |
| summaries | 69,128 |
| xml_citation_links | 46,825 |
| xml_references | 37,198 |
| full_citation_edges | 36,088 |
| reference_nodes | 35,190 |
| figures | 13,471 |
| tables | 4,922 |
| users | 2 |
| workspaces | 1 |
| review_projects | 1 |

FTS shadow 表较多：

```text
sentences_fts
paragraphs_fts
summaries_fts
```

---

## 3. 模块清单

| 模块 | SQLite 角色 | PG 现状 | 迁移优先级 |
|---|---|---|---|
| `services/tenancy/service.py` | 读已 PG（env） | 写入已 PG | 验证 |
| `services/experiments/service.py` | 实验/运行读 | 写入部分 PG | P0 |
| `services/projects/service.py` | 项目/成员读 | 写入已 PG | P0 |
| `routes/watch.py` | watch 读 | PG store 可用 | P1 |
| `services/review/review_generator.py` | reviews/papers 读 | 未迁 | P1 |
| `routes/papers_actions.py` | 论文/附件/文件读 | papers 写已 PG | P1 |
| `api_server.py` | 多个蓝图 db_path | 混合 | P0 |
| `services/search/hybrid_search.py` | 过滤/辅助读 | 段落向量已 PG | P2 |
| `routes/abstracts.py` | 已修 PG | 完成 | — |

---

## 4. 关键判断

### 4.1 不是“一个库”迁移

`research.db` 被多个模块共享：

```text
tenancy
projects
experiments
watch
review
papers
search
```

不能一次性删库；必须按模块切读路径。

### 4.2 写路径已基本 PG

已有：

```text
tenancy pg_writes
projects pg_writes
experiments pg_writes
watch pg_store
papers pg_writes
```

但读路径仍回 SQLite。

### 4.3 迁移顺序

```text
W1 验证 tenancy
W2 projects
W3 experiments / runs
W4 watch
W5 review
W6 papers_actions
W7 hybrid/search 过滤器
W8 归档 research.db
```

理由：

```text
先身份/权限
再业务对象
最后检索辅助
```

---

## 5. 每模块验收

```text
该模块无 sqlite3.connect(DB_PATH)
该模块测试走 PG
20 题/接口回归
query_only 下无报错
```

---

## 6. 风险

```text
模块共享 SQLite 事务
外键/触发器
测试 fixture 依赖 SQLite
读写混合导致部分迁移
```

缓解：

```text
一个模块一个 PR
先只读后写
每步保留 PG 对照
不一次性删 research.db
```

---

## 7. 时间

```text
W1 验证 tenancy   0.5 天
W2 projects       2 天
W3 experiments    2 天
W4 watch          1 天
W5 review         2 天
W6 papers_actions 2 天
W7 hybrid/search  1 天
W8 归档           0.5 天
```

合计约 10.5 天，单开发者。

---

## 8. 下一步

```text
B2 W1：tenancy 读路径迁 PG
```

这是最小、最独立、权限最敏感的模块，适合作为第一刀。


---

## 9. 完成度复核（2026-11-07）

不是“都做过”。逐个核对代码与生产 env：

| 波次 | 模块 | 状态 | 依据 |
|---|---|---|---|
| W1 | tenancy | 基本完成 | `TENANCY_PG_ONLY=1` / `TENANCY_READ_BACKEND=postgres` |
| W2 | projects | 部分 | 写 PG；读仍走 `service.py` SQLite |
| W3 | experiments/runs | 部分 | experiments 路由 PG；runs 仍 SQLite |
| W4 | watch | 基本完成 | `WATCH_PG_STORE=1`，`pg_store` 接管 |
| W5 | review | 部分 | `REVIEWS_BACKEND=postgres` 管 reviews CRUD；generator 仍读 SQLite |
| W6 | papers_actions | 未完成 | 仍 `sqlite3.connect` 读 papers/sections/附件 |
| W7 | hybrid/search 过滤器 | 部分 | 段落向量 PG；过滤/辅助仍可能读 SQLite |
| W8 | 归档 research.db | 未完成 | 仍被上述模块读取 |

### 特别说明

```text
projects/pg_service.py 存在
但 service.py 没有调用
所以不能因为“有 PG 模块”就认为已迁移
```

```text
experiments/pg_read.py 存在
但只被部分路由使用
runs 仍走 SQLite
```

### 结论

```text
W1/W4：基本完成，剩 fallback 清理
W2/W3/W5/W7：读路径只迁了一部分
W6/W8：未完成
```

所以下一步不是“重做 W1”，而是：

```text
W1 验证 fallback
W2 把 projects 读接到 pg_service
W3 把 runs 读迁 PG
W5 把 generator 的 papers 读取迁 PG
W6 papers_actions
W7 search 过滤器
W8 归档
```
