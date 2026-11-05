# G3.10e2 protocols 盘点

> 日期：2026-11-05  
> 结论：需要 PG 适配类，不能只换连接

---

## 1. 当前结构

```text
api_server.py
  ProtocolService(DB_PATH)
```

类方法：

```text
import_payload
import_protocol
list / count / get
add_run / list_runs / update_run / delete_run
add_attachment / list_attachments / delete_attachment
export_markdown
recent_runs
```

约 500 行。

---

## 2. PG 已有

```text
protocol_imports   1
protocol_steps    15
```

---

## 3. PG 缺失

```text
protocol_runs
protocol_run_files
```

当前 `add_run` 写 SQLite 的 `experiment_runs`：

```text
protocol_id
operator
run_date
...
```

与 PG `experiment_runs`（experiment_id 维度）不是同一张表。

---

## 4. 迁移拆分

```text
G3.10e2a PG read adapter
  list / count / get

G3.10e2b import PG
  protocol_imports / protocol_steps

G3.10e2c runs PG
  新建 protocol_runs 表
  add/list/update/delete

G3.10e2d attachments PG
  protocol_run_files + 文件系统

G3.10e2e route 切换
  SCIPAL_PROTOCOLS_BACKEND=postgres
```

---

## 5. 验收

```text
import protocol 只写 PG
list/get 读 PG
run 创建/更新只写 PG
attachment 元数据 PG
SQLite protocol 表不增长
```

---

## 6. 当前生产

```text
projects      PG
protocols     SQLite
app           healthy
```
