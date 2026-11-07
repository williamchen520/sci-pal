# 全站端点分层烟测：C 组结果

> 日期：2026-11-08  
> 环境：生产容器、无 research.db、PG-only

## 结果

```text
tested  5
5xx     0
```

## 通过

```text
review-projects/<id>/prisma.svg
review-projects/<id>/report.html
review-projects/<id>/report.docx
review-projects/<id>/report.pdf
papers/<id>/trace.png
```

## 修复

```text
trace.png 的 filename 查询
  conn_filename(SQLite)
  -> _paper_filename(PG)
```

## 结论

```text
A/B/C 三组全部通过
无 5xx
```

仍存在 0 字节 research.db 占位文件，但不影响功能。
