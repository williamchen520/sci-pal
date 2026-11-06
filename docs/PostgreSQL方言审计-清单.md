# PostgreSQL 方言审计清单

> 日期：2026-11-06  
> 范围：`services/ routes/ api_server.py mcp_server/ build_db/ scripts/`，排除 `tests/`、venv、eval 结果  
> 性质：只读扫描，不改业务代码

---

## 1. 结论

SQLite 宽容带来的风险不是单点，集中在六类：

```text
事务边界
类型严格性
大小写语义
NULL / 排序
唯一约束 / 外键
SQLite 专有语法
```

优先级：

| 级别 | 问题 | 影响 |
|---|---|---|
| P0 | tasks 无原子 claim，running 直接落库 | 重复执行/卡死 |
| P0 | webhooks 仍走 SQLite | SQLite 不能只读 |
| P0 | 空字符串写 int/bool | 运行时 500 |
| P1 | LIKE 大小写/通配符 | 搜索结果错误 |
| P1 | INSERT OR / lastrowid 残留 | fallback 触发即 500 |
| P1 | 唯一键大小写 | 重复用户/DOI |
| P2 | GROUP BY / ORDER BY NULL | 统计/分页偏差 |
| P2 | datetime / JSON / 标识符 | 局部兼容问题 |

---

## 2. 扫描统计

| 模式 | 命中 | 说明 |
|---|---:|---|
| `INSERT OR REPLACE/IGNORE` | 77 | 多数在 build_db；运行时约 18 |
| `AUTOINCREMENT` | 29 | 多数是 SQLite 建表 |
| `PRAGMA` | 63 | 多为 SQLite  introspection |
| `datetime/strftime` | 22 | 多数是 Python `strftime`，非 SQL |
| `GROUP_CONCAT` | 1 | build_db |
| `GLOB` | 26 | 多数是 `Path.glob`，误报 |
| `lastrowid` | 9 | 运行时 4 |
| `LIKE` | 71 | 含大量英文散文误报；SQL 约 20 |
| `ILIKE` | 2 | `services/protocols/pg_read.py` |
| `FOR UPDATE` | 1 | `services/trust/retraction.py` |
| `SKIP LOCKED` | 0 | 无 |

原始命中：

```text
eval/results/pg_dialect_scan.json
```

---

## 3. P0：tasks 事务与 claim

文件：

```text
services/review/pg_tasks.py
services/review/task_manager.py
```

### 3.1 现状

`create_task` 直接写：

```text
status='running'
started_at=now
```

并立即 commit。

没有：

```text
queued 状态
worker_id
lease / heartbeat
原子 claim
启动恢复
```

### 3.2 风险

```text
1. 创建后线程未启动 -> 永久 running
2. 两个进程同时调度 -> 同一任务重复执行
3. 进程崩溃 -> running 卡死
4. cleanup_old_tasks 只按 type/created_at 删除
   可能删掉 running 任务
```

`get_running_task` 只是查询，不是 claim。

### 3.3 正确方向

```text
status: queued -> running -> completed/failed/cancelled
claim:
  UPDATE tasks SET status='running', worker_id=%s, started_at=now()
  WHERE task_id = (
    SELECT task_id FROM tasks
    WHERE status='queued'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  RETURNING task_id
```

并补：

```text
heartbeat_at
lease_expires_at
启动时回收超时 running
idempotency key
```

### 3.4 现有优点

```text
complete/fail/cancel 都是 WHERE status='running' 的 CAS
单次状态写入后 commit
```

这部分设计是对的，缺的是 **入队/领取**。

---

## 4. P0：仍写 SQLite 的运行时路径

### 4.1 webhooks

```text
routes/systematic_review.py:581
routes/systematic_review.py:586
services/review/notifications.py:24
```

即使 systematic 已切 PG：

```text
_conn() 仍是 sqlite3.connect
review_webhooks 表仍在 SQLite
add_webhook 使用 cursor.lastrowid
```

影响：

```text
SQLite 不能只读
webhook 数据不在 PG
```

### 4.2 hybrid_search 元数据过滤

```text
services/search/hybrid_search.py:149
services/search/hybrid_search.py:458
```

使用：

```text
journal LIKE ?
p.journal LIKE ?
```

这是 SQLite 连接上的过滤，不是 PG。

影响：

```text
大小写行为仍是 SQLite
元数据过滤与 PG 数据可能不一致
```

### 4.3 旧搜索与摘要路由

```text
services/query/search_service.py
routes/abstracts.py
```

仍是 SQLite-only。

需要确认是否仍在生产被调用；如果是，属于未迁移模块；如果不是，应标记 dead code。

### 4.4 watch repo

```text
services/watch/repo.py:87/211/259 lastrowid
services/watch/repo.py:137/152/329 INSERT OR
```

watch 生产已走 PG Store，repo 是回滚路径。

但在 P7 删除前，不能把 SQLite 设为只读。

---

## 5. P1：LIKE / ILIKE

### 5.1 语义差异

SQLite：

```text
LIKE 对 ASCII 默认不区分大小写
```

PostgreSQL：

```text
LIKE 区分大小写
```

所以：

```text
title LIKE '%cancer%'
```

SQLite 命中 `Cancer`，PG 可能不命中。

### 5.2 运行时命中

```text
services/protocols/service.py:279
services/protocols/service.py:301
services/query/search_service.py:54/86/118-121/151-153
routes/abstracts.py:29/40
services/search/hybrid_search.py:149/458
```

### 5.3 不能全改 ILIKE

```text
ILIKE 不走普通 btree
%term% 仍然全表扫描
```

建议按字段定义：

```text
用户搜索       lower(col) LIKE lower(%s)
              + pg_trgm GIN
用户名/邮箱     citext 或 lower 唯一索引
DOI            lower 唯一索引
内部 ID        精确匹配
```

### 5.4 通配符

当前多处以：

```python
f"%{query}%"
```

直接拼接。

需要：

```text
转义 % 和 _
ESCAPE '\'
```

否则用户输入 `%` 会匹配全部。

---

## 6. P1：SQLite 专有语法

### 6.1 运行时残留

```text
services/claims/service.py:126/220       INSERT OR REPLACE
services/protocols/service.py:223        INSERT OR REPLACE
services/review/review_repository.py:102        INSERT OR REPLACE
services/review/systematic.py:118/137    INSERT OR REPLACE/IGNORE
services/search/ingest.py:367/416/439    INSERT OR REPLACE
services/search/online_downloader.py:586/609
services/tenancy/service.py:194/205/209/409
services/trust/retraction.py:70
services/watch/runner.py:98/184
```

多数是 SQLite fallback 分支；一旦 fallback 触发，PG 连接上执行会报语法错误。

### 6.2 lastrowid

```text
services/review/notifications.py:24
services/watch/repo.py:87/211/259
```

PG 没有 `lastrowid`，必须 `RETURNING id`。

webhooks 是当前真实运行时风险。

### 6.3 AUTOINCREMENT / PRAGMA

```text
services/data_sandbox/audit.py
services/db/dual_write.py
services/experiments/service.py
services/tenancy/schema.py
```

这些是 SQLite 建表/自省；PG-only 下应跳过，不能执行。

---

## 7. P1：唯一键与大小写

SQLite 常见：

```text
COLLATE NOCASE
```

PG 默认区分大小写。

风险字段：

```text
username
email
doi
paper_id
external_id
```

可能：

```text
Alice / alice
10.1/X / 10.1/x
```

需要：

```text
lower() 唯一索引
或 citext
```

---

## 8. P1：空字符串与类型

已发现：

```text
year = "" -> bigint 失败
```

同类风险：

```text
score = ""
is_admin = "0"
enabled = ""
progress_pct = ""
```

SQLite 会自动转换；PG 直接拒绝。

建议在写入边界统一：

```text
空字符串 -> None
数字字段 -> int/float
布尔字段 -> bool
```

---

## 9. P2：ORDER BY / GROUP BY / NULL

SQLite：

```text
ASC 时 NULL 在前
GROUP BY 允许非聚合列
```

PG：

```text
ASC 时 NULL 在后
GROUP BY 必须完整
```

影响：

```text
分页跳行/重复
统计取到任意行
```

需要显式：

```text
NULLS FIRST / NULLS LAST
GROUP BY 全列
```

---

## 10. P2：时间、JSON、标识符

### 时间

```text
datetime('now')
strftime
```

PG 用：

```text
now()
to_char()
```

### JSON

```text
json_extract
json_each
```

PG 用：

```text
->>
jsonb_array_elements
```

### 标识符

PG 未加引号会转小写；SQLite 不区分大小写。

需要检查：

```text
大写表名/列名
保留字
```

---

## 11. 建议的扫描流程

### 第一层：静态规则

已做，输出：

```text
eval/results/pg_dialect_scan.json
```

### 第二层：SQL 提取

从 Python 字符串中提取 SQL，用：

```text
sqlglot.parse(sql, dialect="postgres")
```

标记解析失败；当前正则只能发现模式，不能判断语义。

### 第三层：真实 SQL 捕获

staging：

```text
log_statement=all
pg_stat_statements
```

跑 API smoke 后比对真实执行 SQL。

### 第四层：行为测试

```text
空字符串
大小写
NULL
重复键
外键
并发 claim
提交后可见性
```

---

## 12. 建议修复顺序

```text
1. tasks queued/claim/lease
2. webhooks 去 SQLite
3. 空字符串类型边界
4. LIKE 语义与转义
5. 唯一键 lower/citext
6. SQLite syntax fallback 清理
7. ORDER BY/GROUP BY
8. JSON/时间/标识符
```

---

## 13. 本次未做

```text
未修改任何业务代码
未改数据库
未切生产
```

下一步先做 **SQL 提取 + sqlglot 解析**，把“模式命中”收敛成“真实不可执行 SQL 清单”。


---

## 14. P0 tasks 修复

已实施：

```text
create_task -> queued
claim_task  -> queued -> running CAS
cancel      -> queued/running 都可取消
get_running -> queued/running
```

冒烟：

```text
created queued
claim1  True  -> running
claim2  False
cancel  True  -> cancelled
```

已补：

```text
recover_stale_tasks(120min)
  queued/running 超时 -> failed
启动时自动执行
cleanup_old_tasks 只删终态
```

仍未做：

```text
heartbeat / lease_expires_at
```
