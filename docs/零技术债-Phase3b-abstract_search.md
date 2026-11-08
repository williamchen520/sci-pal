# 零技术债 Phase 3b：abstract_search 收敛

> 日期：2026-11-08  
> 状态：**abstract_search SQLite/Chroma 分支已删除**

---

## 1. 删除

```text
sqlite3
chromadb
sentence_transformers
data/abstracts.db
data/chroma_abstracts
```

`AbstractSearch` 现在：

```text
vector_search -> []
fts_search    -> []
search        -> []
```

---

## 2. 原因

```text
PG 模式下本来就直接返回 []
Chroma 已归档
abstracts.db 不再是生产数据源
```

保留类只是为 `UnifiedRetriever` 兼容。

---

## 3. 测试

旧测试：

```text
新建 SQLite FTS 库
测 fts_search
```

已改为：

```text
断言三个方法返回空
```

结果：

```text
tests.test_abstract_search   1 passed
sqlite group                37 passed
```

---

## 4. Allowlist

```text
61 -> 60
```

---

## 5. 下一步

```text
继续从 60 个文件里删
候选：
  auto_merger
  title_recall
  boilerplate_filter
```
