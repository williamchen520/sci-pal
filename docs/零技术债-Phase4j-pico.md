# 零技术债 Phase 4j：pico PG

> 日期：2026-11-09  
> 状态：**/pico 不再使用 SQLite conn**

---

## 1. 改动

```text
services/review/pico.py
  auto_pico_pg(project_id)
  PG 查询 review_projects / papers
  PG 更新 pico_json

routes/systematic_review.py
  result = pico.auto_pico_pg(project_id)
```

---

## 2. 验证

```text
py_compile OK
```

---

## 3. 说明

`kappa` / `risk-of-bias` 已经是 PG 分支；本批补上 pico。

---

## 4. 下一步

```text
import / export / import-records / import-file / from-watch / webhooks
```

逐个确认 PG 覆盖后，才能删 route 的 else。
