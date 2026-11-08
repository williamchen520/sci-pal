# 零技术债 Phase 3d：batch 2

> 日期：2026-11-08  
> 状态：**四个模块的 SQLite 路径已删除**

---

## 1. reference_link

```text
sqlite3 -> main_read_connection
enrich_references 查 public.papers
db_path 参数保留但忽略
```

测试改为 fake PG。

---

## 2. europe_pmc

删除：

```text
DEFAULT_DB
download_and_import()
import sqlite3
build_db.import_jats.import_file
```

保留：

```text
EuropePMCClient.search / search_all / fetch_fulltext_xml
```

watch 只用 search，不受影响。

---

## 3. europe_pmc_batch

整个模块删除：

```text
services/search/europe_pmc_batch.py
```

原因：

```text
没有调用方
基于 SQLite import_jats
生产批量入库走 PG 路径
```

对应测试已删除。

---

## 4. preprint_ingest

```text
sqlite3 -> ingest_connection
_patch_metadata 直接 UPDATE public.papers
```

支持：

```text
title / authors / year / doi
```

---

## 5. Allowlist

```text
56 -> 52
SQLITE_ALLOWLIST_OK 52
```

---

## 6. 测试

```text
reference_link / sources_pipeline
10 passed
```

---

## 7. 下一步

```text
继续 batch 3
剩余 52
优先仍是离线/审计模块
```
