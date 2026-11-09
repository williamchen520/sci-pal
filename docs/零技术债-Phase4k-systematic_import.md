# 零技术债 Phase 4k：systematic 导入端点 PG

> 日期：2026-11-09  
> 状态：**from-watch / import-records / import-file 不再用 SQLite**

---

## 1. 新增

```text
services/review/pg_systematic.py
  add_from_watch(project_id, run_id)
  import_records(project_id, records)
```

---

## 2. 路由

```text
from-watch      -> pg_systematic.add_from_watch
import-records  -> pg_systematic.import_records
import-file     -> pg_systematic.import_records
```

`export.json` / `webhooks` 本来已有 PG 分支。

---

## 3. 验证

```text
py_compile OK
```

---

## 4. 下一步

```text
清理 route 里剩余的不可达 systematic.* 分支
```

然后 service 才能移入 tests。
