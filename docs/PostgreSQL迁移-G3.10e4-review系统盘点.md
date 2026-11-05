# G3.10e4 review systematic 盘点

> 日期：2026-11-05  
> 结论：PG 表已齐，服务仍是 SQLite connection 风格

---

## 1. PG 已有

```text
review_projects          1
review_project_members
review_project_papers
screening_decisions      1
evidence_rows            1
review_events            0
review_webhooks
```

与 SQLite 行数一致。

---

## 2. 当前结构

```text
routes/systematic_review.py
  _conn() -> sqlite3
  systematic.create_project(conn,...)
  systematic.screen(conn,...)
  systematic.prisma(conn,...)
  systematic.list_evidence(conn,...)
```

`systematic.py` 有 30+ 个函数，全部接收 SQLite conn。

---

## 3. 迁移拆分

```text
G3.10e4a PG systematic service
  projects / members / papers

G3.10e4b screening
  screen / adjudicate / prisma / conflicts / kappa

G3.10e4c evidence
  add / list / csv

G3.10e4d events / notifications / webhooks

G3.10e4e reports
  brief / html / docx / pdf
```

---

## 4. 风险

```text
screening 与 evidence 依赖 review_project_papers
PRISMA 计数依赖 screening_decisions
报告依赖 evidence_rows
```

必须按依赖顺序迁，不能只切 projects。

---

## 5. 当前生产

```text
reviews             PG
review systematic   SQLite
protocols           PG
projects            PG
app                 healthy
```

---

## 5b. G3.10e4a 完成

```text
services/review/pg_systematic.py
  create/get/list/can_access
  add_member/members
  add_papers
routes/systematic_review.py
  SCIPAL_SYSTEMATIC_BACKEND=postgres
```

冒烟：

```text
list 1
create/get
add_papers 1
cleanup ✅
```

仍未切：

```text
screen / prisma / evidence / reports
```

## 5c. G3.10e4b 完成

```text
pg_systematic.screen / adjudicate / prisma / conflicts
```

修复：

```text
screening_decisions identity sequence 落后
adjudications identity sequence 落后
setval -> max(id)+1
```

冒烟：

```text
screen include/exclude
prisma 1/1
conflicts 1
adjudicate -> included
cleanup ✅
```

路由按 `SCIPAL_SYSTEMATIC_BACKEND` 切换。

## 5d. G3.10e4c 完成

```text
pg_systematic.add_evidence / list_evidence / evidence_csv
```

修复：

```text
evidence_rows identity sequence 落后
```

冒烟：

```text
papers 1
evidence 1
csv 411
cleanup ✅
```

## 5e. G3.10e4d events

```text
pg_systematic.log_event
pg_systematic.list_events
```

冒烟：

```text
events 1
cleanup ✅
```

报告仍未迁：

```text
brief
report.html
report.pdf
report.docx
```

## 5f. G3.10e4e brief/report

```text
services/review/pg_report.py
  build_brief
  render_html
```

冒烟：

```text
projects 1
brief 599
html 5170
```

PDF/DOCX 已补：

```text
services/review/pg_pdf.py
```

## 5g. 报告路由修复

brief/html/pdf/docx 的预检查仍查 SQLite，已改为按 flag 查 PG。

共修复 5 处。

API 冒烟：

```text
papers 1
screen included
evidence 1
```

brief/pdf 待部署后复测。

## 6. 下一步

```text
G3.10e4a PG systematic projects
```
