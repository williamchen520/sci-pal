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
