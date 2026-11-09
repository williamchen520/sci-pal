# 零技术债 Phase 5g：PDF annotator PG-only

> 日期：2026-11-09  
> 状态：**PDF 路径查询固定 PG**

---

## 1. 改动

```text
services/pdf/annotator.py
  sqlite3 删除
  get_pdf_path -> PG papers
```

---

## 2. 验证

```text
papers downloads routes   7 passed
allowlist                 20 -> 19
```

---

## 3. 下一步

```text
services/quality/guard.py
```
