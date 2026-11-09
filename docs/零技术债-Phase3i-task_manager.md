# 零技术债 Phase 3i：task_manager PG-only

> 日期：2026-11-09  
> 状态：**SQLite TaskManager 删除**

---

## 1. 改动

```text
services/review/task_manager.py
```

保留：

```text
PERSISTED_TASK_TYPES
_SELECT_COLUMNS
_now
_row_to_task
task_manager = PGTaskManager()
```

删除：

```text
sqlite3
DB_PATH
_connect
TaskManager 全部方法
SCIPAL_REVIEW_TASKS_BACKEND 分支
```

---

## 2. 兼容

```text
api_server.py
review_generator.py
task_lookup.py
services/review/task_manager import task_manager
```

导入路径不变，对象固定为 `PGTaskManager`。

---

## 3. 验证

```text
task_manager import   PGTaskManager
review actions/read   14 passed
allowlist             48 -> 47
```

---

## 4. Batch 4

```text
notifications      完成
task_manager       完成
claims/service     待做
notes/service      待做
```

---

## 5. 下一步

```text
claims/service 与 notes/service
先迁移测试，再删 SQLite 分支
```
