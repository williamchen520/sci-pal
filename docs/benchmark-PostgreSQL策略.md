# Benchmark PostgreSQL 策略（Route B）

> 日期：2026-10-31  
> 状态：策略已实现；PostgreSQL 业务后端尚未实现

---

## 1. 规则

```text
大规模（>100 篇）测试：必须 PostgreSQL
并发测试（>1 worker）：必须 PostgreSQL
小规模本地验证（≤100 篇、单进程）：允许 SQLite，但必须显式 opt-in
```

严禁使用 SQLite 进行高并发测试。

---

## 2. 默认连接串

```text
postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench
```

环境变量：

```powershell
$env:SCIPAL_BENCH_DATABASE_URL = "postgresql://user:pass@host:5432/db"
```

小规模 SQLite：

```powershell
$env:SCIPAL_BENCH_DATABASE_URL = "sqlite:///data/bench_local.db"
$env:SCIPAL_BENCH_ALLOW_SQLITE = "1"
```

---

## 3. 行为

`services/quality/benchmark_db.py` 在 benchmark 启动时检查：

```text
1. URL scheme 必须是 postgresql:// 或 sqlite://
2. PostgreSQL：必须有 psycopg/psycopg2 driver
3. SQLite：
   - papers > 100 -> 直接失败
   - concurrent > 1 -> 直接失败
   - 没有 SCIPAL_BENCH_ALLOW_SQLITE=1 -> 直接失败
4. 其他 scheme -> 直接失败
```

失败信息明确指向策略，不静默退回 SQLite。

---

## 4. 当前限制

```text
业务数据库仍是 SQLite；
没有 PostgreSQL schema / 迁移 / FTS 替换；
没有 psycopg 依赖。
```

因此：

```text
默认 benchmark 会 fail-fast，提示安装 PostgreSQL driver；
小规模本地测试需显式允许 SQLite。
```

这是有意的：宁可失败，也不让高并发测试偷偷跑在 SQLite 上。

---

## 5. 后续迁移

完整 PostgreSQL 迁移应单独开计划，至少包括：

```text
1. psycopg 连接层
2. schema 迁移
3. SQLite FTS5 -> PostgreSQL tsvector/pg_trgm
4. 多 worker / 连接池
5. 双写与回滚
6. 并发测试
```

不要用“改连接字符串”冒充迁移完成。

---

## 6. 代码

- `services/quality/benchmark_db.py`
- `tests/test_benchmark_db.py`
- `eval/plugin_bench.py`
- `eval/claim_verifier_bench.py`
- `eval/retriever_bench.py`
