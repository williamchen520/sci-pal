# G3.8a 阻塞：批量 ingest 仍写 SQLite

> 日期：2026-11-05  
> 结论：gate 通过，但 `SCIPAL_INGEST_PG_ONLY` 覆盖不到批量路径

---

## 1. 已覆盖

```text
build_db/db_writer.py
  DatabaseWriter.insert_paper -> PG-only
```

适用：

```text
routes/papers_actions.py 的 parse/import 路径
```

---

## 2. 未覆盖

### A. XML 批量入库

```text
services/search/ingest.py
  conn.execute INSERT papers/paragraphs/sentences
  然后 write_papers_batch
```

写 SQLite 在 PG 之前，`SCIPAL_INGEST_PG_ONLY=1` 不会跳过。

### B. 在线下载增量入库

```text
services/search/online_downloader.py
  conn.execute INSERT papers/paragraphs
  然后 write_papers_batch
```

同样先写 SQLite。

---

## 3. 后果

如果现在：

```text
SCIPAL_INGEST_PG_ONLY=1
DROP dualwrite triggers
```

批量 ingest 会：

```text
SQLite 行新增
outbox 不再产生
PG 不新增
```

造成数据分叉。

---

## 4. 正确顺序

```text
G3.8a1 ingest.py 批处理 PG-only
G3.8a2 online_downloader PG-only
G3.8a3 开 SCIPAL_INGEST_PG_ONLY
G3.8a4 跑 gate
G3.8b 观察 pending
G3.8c 删 trigger
```

---

## 5. 验收

```text
新批量导入后：
  SQLite core 行数不增长
  PG core 行数增长
  outbox pending 0
```

---

## 5b. 代码进展

```text
services/search/ingest.py
  PG-only 批量分支
services/search/online_downloader.py
  PG-only 批量分支
```

测试：

```text
tests.test_ingest_pg_only 1 OK
```

默认关闭：

```text
SCIPAL_INGEST_PG_ONLY=0
```

## 6. 当前生产

```text
SCIPAL_INGEST_PG_ONLY 未设置
dualwrite triggers 仍启用
gate ok
app healthy
```
