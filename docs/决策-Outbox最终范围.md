# 决策：Outbox 最终范围

> 日期：2026-11-03  
> 决策：**保留 27 个 trigger，冻结退役。**

## 1. 当前事实

```text
triggers   27
pending     0
```

保留的 trigger：

```text
papers
sections
paragraphs
sentences
figures
tables
citations
sentence_links
paper_links
```

## 2. 已退役

```text
tenancy
watch_profiles / items / runs / seen
claim_cards / evidence / events
review_projects / review_events
```

## 3. 为什么保留 27 个

运行时写路径已大部分 PG-first：

```text
JATS ingest
DatabaseWriter PDF/preprint
online downloader
watch
claims/reviews
projects/experiments
```

但仍有 SQLite-first 路径：

```text
legacy build_database / build_xml_db
import_jats 的 SQLite 事务后 PG sync
build_sections/build_sentences 的 SQLite mirror
```

outbox 现在是：

```text
legacy/build 兼容桥
```

不是运行时主路径。

## 4. 最终决策

```text
不删除剩余 27 个 trigger
不再逐表追退役
不接受为了“零 trigger”而删掉 legacy 兼容
```

## 5. 重开条件

只有满足以下条件才重新讨论：

```text
1. legacy build 脚本删除或改为 PG-only
2. import_jats 改为 PG transaction，SQLite 仅 mirror
3. build_sections/build_sentences 不再写 SQLite
4. 连续 7 天 pending=0 / drift=0
```

## 6. 当前架构定义

```text
PostgreSQL：运行时读路径 + 主要写路径权威源
SQLite：FTS / Chroma 辅助 / legacy build mirror
Outbox：legacy build 到 PG 的桥
```

这不是“纯 PG”，但是**边界明确的混合架构**。

## 7. 停止条件

```text
不再以“删 trigger”为目标
转向：
  - 检索质量
  - SLO
  - legacy build 清理
  - 数据质量
```

## 8. 备注

```text
27 个 trigger 不代表 27 个未迁移业务域
它们只是 papers 图及其链接/build 兼容
```
