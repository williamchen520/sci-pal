# 零技术债 Phase 5c：unified task manager PG-only

> 日期：2026-11-09  
> 状态：**任务管理器删除 SQLite fallback**

---

## 1. 改动

```text
services/unified_task_manager.py
  sqlite3 / _get_conn / _pg_enabled 删除
  create/update/complete/fail/cancel/get/list 固定 PG
```

---

## 2. 测试

```text
tasks routes + task lookup   8 passed
allowlist                    24 -> 23
```

---

## 3. 说明

检索引擎保持现状：

```text
旧引擎：默认
新句子级原型：仅 eval 脚本
```

本批不触碰检索路径。
