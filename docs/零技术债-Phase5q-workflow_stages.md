# 零技术债 Phase 5q：workflow stages PG-only

> 日期：2026-11-09  
> 状态：**论文元数据读取固定 PG**

---

## 1. 改动

```text
services/workflow/stages.py
  sqlite3 删除
  _paper_metadata -> PG papers
  context.services["paper_metadata"] 可注入（测试）
```

---

## 2. 测试

```text
workflow stages + runner   全部通过
allowlist                  10 -> 9
```

---

## 3. 下一步

```text
services/search/online_downloader.py
```
