# Legacy Build 脚本处置

> 日期：2026-11-02  
> 原则：不删除历史脚本，明确标记和边界。

## 1. 处置表

| 脚本 | 处置 | 原因 |
|---|---|---|
| `build_db/build_database.py` | **legacy** | 全库重建，已被 import_jats / parse_service 取代 |
| `build_db/build_xml_db.py` | **legacy** | 旧 XML schema，已被 import_jats 取代 |
| `build_db/build_fts.py` | 保留 | SQLite FTS 运维重建 |
| `build_db/build_embeddings.py` | 保留 | Chroma 向量重建 |
| `build_db/import_jats.py` | 运行时 | Europe PMC 全文导入 |
| `build_db/parse_service.py` | 运行时 | PDF/preprint 解析 |
| `build_db/db_writer.py` | 运行时 | DatabaseWriter |
| `build_db/build_sections_tree.py` | build | 已 PG-first |
| `build_db/build_sentences.py` | build | 已 PG-first |
| `build_db/backfill_*.py` | 一次性 | 历史修复，保留 |

## 2. Legacy 标记

`build_database.py` / `build_xml_db.py` 顶部已加：

```text
LEGACY full-rebuild script. Do not run on production.
```

不删除的原因：

```text
build_database.py 的 extract_doi 仍被 resolve_ref_dois 引用
历史重建仍可能需要
删除会破坏旧脚本导入
```

## 3. 禁止事项

```text
不要在 production 运行 build_database.py
不要用 build_xml_db.py 重建生产库
不要把 legacy 脚本当作日常 ingest
```

## 4. 后续

```text
1. 把 extract_doi 抽到独立 helper
2. 再评估是否删除 build_database.py
3. build_xml_db.py 可直接标记 deprecated
```

## 5. 当前状态

```text
legacy 已标记
未删除
papers trigger 不受影响
```
