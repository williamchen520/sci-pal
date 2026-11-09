# 零技术债 Phase 3j：qa citations PG-only

> 日期：2026-11-09  
> 状态：**paragraph_citation 删除 SQLite fallback**

---

## 1. 改动

```text
services/qa/citations.py
  sqlite3 -> pg_connection
  SCIPAL_QA_CITATIONS_BACKEND 分支删除
  db_path 保留兼容但忽略
```

保留：

```text
fallback_citations
```

---

## 2. 测试

```text
test_paragraph_citation
  旧：临时 SQLite sentences 表
  新：fake PG 返回 s1/s2
```

结果：

```text
4 passed
```

---

## 3. Allowlist

```text
47 -> 46
```

---

## 4. 为什么先做它

```text
claims/service 与 notes/service 的测试绑定更深
qa/citations 单函数、PG 路径完整
适合作为 Batch 4 的收尾小步
```

---

## 5. 剩余

```text
claims/service
notes/service
```
