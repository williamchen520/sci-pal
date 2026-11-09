# 零技术债 Phase 3y：system route PG-only

> 日期：2026-11-09  
> 状态：**communities SQLite 删除；明确 404**

---

## 1. 事实

PostgreSQL 没有：

```text
paper_communities
community_members
```

社区功能从未迁 PG。

---

## 2. 改动

```text
routes/system.py
  sqlite3 删除
  /api/communities 固定 404
  error message 保留 build_communities 提示
```

不再假装可用，也不在 runtime guard 下 500。

---

## 3. 测试

删除两个 SQLite 列表/明细测试；保留：

```text
missing table -> 404
graph stats
```

结果：

```text
3 passed
```

---

## 4. Allowlist

```text
33 -> 32
```

---

## 5. 下一步

```text
routes/systematic_review.py
```

它是整条 route family 的双路径，单独迁移。
