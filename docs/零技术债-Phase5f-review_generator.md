# 零技术债 Phase 5f：review_generator PG-only

> 日期：2026-11-09  
> 状态：**元数据 / 标题 / DOI 映射固定 PG**

---

## 1. 改动

```text
services/review/review_generator.py
  _fetch_paper_metadata -> PG papers
  _paper_titles         -> PG papers
  _get_fulltext_doi_map -> PG papers
  sqlite3 删除
```

修正：

```text
_fetch_paper_metadata 不再因 research.db 不存在直接返回空
```

这是生产隐患：旧代码在 `research.db` 退役后会丢掉所有参考文献元数据。

---

## 2. 测试

```text
review actions + reviews routes + title recall   17 passed
allowlist                                        21 -> 20
```

---

## 3. 下一步

```text
services/experiments/*
services/projects/service.py
```
