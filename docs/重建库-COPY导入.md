# 独立重建库：COPY 级 XML 导入

> 日期：2026-11-10  
> 状态：`scipal_rebuild` 已建成，未切换生产

---

## 1. 数据源

```text
镜像内 /app/documents_xml
13,291 篇 JATS XML
```

独立数据库：

```text
scipal_rebuild
```

## 2. 流程

```text
1. 建 schema（build_db/postgres_schema.sql）
2. 解析 JATS -> 行数据
3. COPY 到 papers/sections/figures/tables/citations/paragraphs/sentences/sentence_links
4. 每 200 篇一个 COPY 批次
5. 摘要型论文补 Abstract 段落
6. 物化 section 树 depth/path
7. 全量结构审查
8. 建段落 embedding
9. 建 HNSW
```

## 3. 关键脚本

```text
build_db/import_jats_copy.py       COPY 行构造
scripts/import_rebuild_copy.py     区间导入 CLI
scripts/backfill_abstracts_rebuild.py
scripts/audit_rebuild_pg.py
```

## 4. 结果

```text
papers          13,201
sections       152,382
paragraphs     410,270
sentences    1,780,306
embeddings     343,546
```

摘要补全：

```text
3,917 篇无正文
3,827 篇补 Abstract
90 篇无正文无摘要，删除
```

审查：

```text
sections_missing_parent       0
sections_wrong_depth          0
sections_self_parent          0
paragraphs_missing_section    0
paragraphs_missing_paper      0
sentences_missing_paragraph   0
sentences_missing_paper       0
papers_without_paragraphs     0
empty_paragraphs              0
empty_sentences               0
```

## 5. 向量

```text
候选段落       401,983
写入向量       343,546
过滤跳过        58,437（参考文献/短文本/boilerplate）
```

HNSW：

```text
maintenance_work_mem  3GB
parallel workers      4
m                     16
ef_construction       64
耗时                  84.5 分钟
索引大小              1,326 MB
查询 LIMIT 10         13 ms
```

8GB 失败原因：

```text
容器 /dev/shm 只有 4GB
could not resize shared memory segment
```

## 6. 备份

```text
G:\sciPal_deploy\backups\scipal_rebuild_20261110.dump
SHA256 65D6DBF89ED50BBF17CFF82F1DB8946C0B8839175E2454664A6BBED6BE880835
```

## 7. 注意

```text
独立库，未接应用
生产仍是旧快照
切换前需做 20 题 / SciFact 冒烟
```
