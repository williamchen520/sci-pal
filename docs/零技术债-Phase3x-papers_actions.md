# 零技术债 Phase 3x：papers_actions 退出 allowlist

> 日期：2026-11-09  
> 状态：**papers_actions 无 sqlite3.connect**

---

## 1. 最后三处

```text
parse 补充材料存在性 -> _paper_exists / store.exists
trace payload      -> _trace_payload_pg only
render filename    -> store.filename
```

---

## 2. 测试

`trace_payload` 增加注入：

```text
build_papers_actions_blueprint(..., trace_payload=...)
```

`test_trace_routes` 用 fake payload，不再依赖 SQLite trace 查询。

结果：

```text
papers downloads / pdf / trace   16 passed
```

---

## 3. Allowlist

```text
34 -> 33
papers_actions.py 已退出 allowlist
```

---

## 4. 当前

```text
routes/papers_actions.py
  0 个 sqlite3.connect
```

---

## 5. 下一步

```text
routes/system.py
routes/systematic_review.py
剩余核心检索 fallback
tenancy 边界
```
