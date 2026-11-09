# 零技术债 Phase 5d：outline communities 清理

> 日期：2026-11-09  
> 状态：**outline_generator 不再读 SQLite 社区表**

---

## 1. 改动

```text
services/review/outline_generator.py
  sqlite3 删除
  _load_communities 返回 {}
```

原因：

```text
PostgreSQL 没有 paper_communities / community_members
社区功能未迁 PG
```

outline 保持扁平，不再尝试读不存在的社区。

---

## 2. 测试

```text
review actions + reviews routes   13 passed
allowlist                         23 -> 22
```

---

## 3. 下一步

```text
services/review/title_recall.py
```
