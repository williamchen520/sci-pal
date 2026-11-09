# 零技术债 Phase 3k：summary_vector_search 收敛

> 日期：2026-11-09  
> 状态：**Chroma/SQLite summary vector 分支删除**

---

## 1. 改动

`services/search/summary_vector_search.py`

删除：

```text
chromadb
sentence_transformers
sqlite3
data/research.db
section_summaries collection
expand() 的 SQLite 查询
```

保留：

```text
available() -> False
search()    -> []
expand()    -> []
get_default()
```

---

## 2. 原因

```text
PG 模式下本来就直接不可用
Chroma 已归档
summaries 走 PG summary 检索
```

---

## 3. 测试

```text
test_summary_vector   1 passed
```

测试原本只断言 missing collection 安全，行为不变。

---

## 4. Allowlist

```text
46 -> 45
```

---

## 5. 下一步

```text
summary_search
review_repository
references/library
```

继续挑可独立收敛的 A 类。
