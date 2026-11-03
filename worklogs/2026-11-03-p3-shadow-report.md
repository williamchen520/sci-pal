# Worklog: P3 Shadow Read 报告脚本

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

把 P3 shadow read 变成可重复运行、可读的报告，而不是一次性脚本输出。

## 2. ARCHITECTURE.json 变化

```text
无
```

## 3. 修改文件

```text
scripts/p3_shadow_report.py
services/db/shadow_read.py
tests/test_p3_shadow_report.py
docs/PostgreSQL迁移-P3-shadow.json
docs/PostgreSQL迁移-P3-shadow.md
docs/PostgreSQL迁移-最终验收.md
docs/Research_Logs_Index.md
worklogs/2026-11-03-p3-shadow-report.md
```

## 4. 业务逻辑变化

```text
新增 P3 报告脚本：
  默认读取 backups/*.db 最新快照
  拒绝 data/research.db
  比较 7 张核心表
  输出 JSON + Markdown
  有 diff 时 exit 1

shadow_read:
  增加 ignore_fields
  默认忽略 created_at / updated_at
  避免 ETL 时间戳造成假 diff
```

## 5. validate_arch 结果

```text
json_routes=202
app_routes=202
OK
```

## 6. 测试命令与通过率

```text
tests.test_shadow_read + tests.test_p3_shadow_report
7 tests OK

真实 PG 报告：
  status ok
  papers 3313
  sections 69128
  paragraphs 167388
  sentences 862677
  citations 182817
  sentence_links 296951
  paper_links 164802
  field_diffs 0
```

## 7. 风险 / 外部 API

```text
只读，无数据变更
依赖本地快照
时间戳字段被忽略，语义字段仍比较
```

## 8. 未完成项

```text
PR Pending Review
生产态每日调度（开发态手动运行）
后续可加 FTS 查询对比
```
