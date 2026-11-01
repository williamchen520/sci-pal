# P5 读路径 Canary

> 日期：2026-11-01  
> 范围：只切 `GET /api/papers` 列表读；写路径和 FTS 保持不变。  
> 默认：SQLite；PostgreSQL 只按百分比 canary。

---

## 1. 开关

```text
SCIPAL_PG_DSN=postgresql://...
SCIPAL_READ_CANARY_PERCENT=0..100
SCIPAL_READ_CANARY_SEED=scipal
```

语义：

```text
0    = 全 SQLite
10   = 约 10% 请求走 PG
100  = 全 PG
```

PG 异常自动回退 SQLite。

---

## 2. 范围

已切：

```text
GET /api/papers
```

已切：

```text
GET /api/papers
GET /api/papers/<id>
GET /api/papers/<id>/graph
```

未切：

```text
所有写接口
FTS / 检索
```

graph 开关：

```text
SCIPAL_READ_GRAPH_PERCENT=0..100
```

验证：

```text
single: 200 / postgres / count 10
5 workers:  50/50 postgres
20 workers: 50/50 postgres
```

detail 新开关（开发中）：

```text
SCIPAL_READ_DETAIL_PERCENT=0..100
```

已用 test client 验证 detail PG 与 SQLite 返回相同 key 结构；生产未开启。

原因：

```text
列表读最简单，响应结构稳定；
detail 依赖 cross_paper_index，先不扩大风险面。
```

---

## 3. 响应头

```text
X-SciPal-Read-Backend: sqlite | postgres
```

用于确认请求实际走了哪条路径。

---

## 4. 对比结果

脚本：

```text
scripts/read_canary_check.py
```

执行：

```powershell
$env:SCIPAL_PG_DSN = "postgresql://..."

python scripts\read_canary_check.py `
  --db data\research.db `
  --out docs\PostgreSQL迁移-P5-canary-check.json
```

结果：

```text
workspace: ws_default
sqlite_count: 3310
postgres_count: 3310
same_order: true
field_diffs: 0
missing_in_pg: 0
extra_in_pg: 0
status: ok
```

排序修复：

```text
SQLite: ORDER BY year DESC, title COLLATE BINARY, paper_id
PG:     ORDER BY year DESC NULLS LAST, title COLLATE "C", paper_id
```

`paper_id` 是稳定 tie-breaker；否则同标题论文顺序不稳定。

---

## 5. 实测 canary

Flask test client：

```text
SCIPAL_READ_CANARY_PERCENT=100
GET /api/papers
```

结果：

```text
HTTP 200
X-SciPal-Read-Backend: postgres
count: 3310
```

说明 PG 读路径已真实可用。

本地 Flask 10% canary（100 次 `/api/papers`）：

```text
sqlite:   90
postgres: 10
errors:   0
```

比例符合 10%；PG 响应正常。

生产数据实例（G 库 / 3312 篇）10% canary：

```text
sqlite:   90
postgres: 10
errors:   0
```

生产容器需要 `psycopg`：

```text
requirements.txt: psycopg[binary]>=3.2
```

没有它时 PG 分支会回退 SQLite，`X-SciPal-Read-Backend` 全是 sqlite。

---

## 6. 回退

```text
SCIPAL_READ_CANARY_PERCENT=0
```

立即全部回 SQLite。

不需要改数据库，不需要停 replay。

---

## 7. 建议上线顺序

```text
1. 0%    先部署，确认 SQLite 正常
2. 10%   观察 1–2 小时：5xx、延迟、响应头
3. 50%   观察
4. 100%  只切 /api/papers
```

每次变更只动环境变量。

---

## 8. 限制

```text
只覆盖 /api/papers 列表
没有切 detail / graph
没有切写路径
没有切 FTS
canary 按请求随机，不是按用户
```

---

## 9. 相关文件

```text
services/db/read_router.py
scripts/read_canary_check.py
tests/test_read_router.py
docs/PostgreSQL迁移-P5-canary-check.json
```
