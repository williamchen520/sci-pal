# Phase 2：Figures / Tables 不是运行时写路径

> 日期：2026-11-02  
> 结论：不在 ingest 里迁移 figures/tables；它们是 build-time 数据。

## 1. 检查结果

运行时 `services/search/ingest.py`：

```text
只把 data["figures"] / data["tables"] 放进 parsed result
_write_batch 不插入 figures / tables
```

实际插入位置：

```text
build_db/db_writer.py
build_db/build_database.py
build_db/build_xml_db.py
build_db/import_jats.py
build_db/backfill_xml_figures.py
```

这些是离线构建/回填脚本，不是 API 运行时。

## 2. 当前数据

```text
SQLite figures 13,471
SQLite tables   4,922

PG figures      13,471
PG tables        4,922
```

两边已一致，说明历史 outbox 已回放完成。

## 3. Outbox 触发

`figures` / `tables` 仍有：

```text
dualwrite_figures_ai/au/ad
dualwrite_tables_ai/au/ad
```

但触发来源是 build-time 脚本，不是 ingest 请求。

## 4. 为什么不在 ingest 加写入

```text
1. ingest 当前语义不写 figures/tables
2. 强行加入会改变 API 行为
3. 会重复 build_db 已有逻辑
4. 不是这次 PG 净化必须项
```

## 5. 正确的迁移方式

如果要把 build-time 也 PG-only：

```text
build_db/db_writer.py -> PG writer
build_db/import_jats.py -> PG writer
build_db/build_xml_db.py -> PG writer
```

这是独立的 ETL 迁移，不属于 API 写路径。

## 6. Phase 2 剩余

```text
online_downloader paper insert
preprint_ingest metadata update
outbox 收口
```

## 7. 决定

```text
不在 ingest 里加 figures/tables
不删 figures/tables outbox
先处理 online/preprint 运行时写
```
