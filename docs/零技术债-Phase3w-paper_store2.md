# 零技术债 Phase 3w：paper store 扩展

> 日期：2026-11-09  
> 状态：**assign / supplementary / list_local 已走 store**

---

## 1. Store 新方法

```text
PaperStore.assign_workspace
PaperStore.supplementary_counts
```

---

## 2. 路由

```text
assign_paper_workspace -> store.assign_workspace
_supplementary_counts  -> store.supplementary_counts
list_local_papers      -> 不再 sqlite3.connect
```

---

## 3. 测试

```text
SqlitePaperStore 增加 assign/supplementary
papers downloads/pdf/trace   16 passed
```

---

## 4. papers_actions 剩余

```text
parse existence check
trace payload SQLite fallback
render filename
```

文件仍在 allowlist，因为还有 3 处 connect。

---

## 5. 下一步

```text
trace payload 已有 _trace_payload_pg
parse existence 可 store.exists
render filename 可 store.filename
```

这三处清完后，`papers_actions.py` 才能真正退出 allowlist。
