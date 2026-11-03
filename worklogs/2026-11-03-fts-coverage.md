# Worklog: FTS 覆盖补齐

> 日期：2026-11-03  
> PR：Pending Review

## 1. 需求

FTS 单栈盘点发现 SQLite 自身缺行，先补齐再谈切换。

## 2. ARCHITECTURE.json 变化

```text
无
```

## 3. 修改文件

```text
scripts/repair_fts_coverage.py
tests/test_repair_fts_coverage.py
docs/PostgreSQL迁移-FTS单栈盘点.md
docs/Research_Logs_Index.md
worklogs/2026-11-03-fts-coverage.md
```

## 4. 数据变化

修复前：

```text
paragraphs      167,388
paragraphs_fts  166,465  缺 923
summaries        69,128
summaries_fts    61,932  缺 7,196
```

修复后：

```text
paragraphs_fts  167,388
summaries_fts    69,128
missing          0 / 0
```

新增 trigger：

```text
summaries_ai
summaries_ad
summaries_au
```

## 5. 安全措施

```text
修复前快照：
D:\sciPal\backups\research_20261103_223739.db
integrity ok
papers 3313
sha256 3911f665...
```

修复脚本默认 dry-run，`--apply` 才写入；写入在单事务中。

## 6. 测试命令与通过率

```text
tests.test_repair_fts_coverage
2 tests OK

生产库 dry-run：
paragraphs 923 / summaries 7,196

apply 后：
missing 0 / 0
app health 200
```

## 7. 风险 / 外部 API

```text
无新增外部 API
SQLite FTS 索引变更
未删除任何数据
新增 summaries trigger
```

## 8. 未完成项

```text
PR Pending Review
PG FTS 适配器 / 影子对比未开始
```
