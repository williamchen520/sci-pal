# Outbox 收口状态

> 日期：2026-11-02  
> 结果：watch + claims/reviews outbox 已退役；其余表仍有阻塞项。

## 1. 已完成

watch 表：

```text
watch_profiles
watch_items
watch_runs
watch_seen
```

已删除 12 个 trigger：

```text
dualwrite_watch_{profiles,items,runs,seen}_{ai,au,ad}
```

删除 pending：

```text
4 条（canary cleanup 事件）
```

验证：

```text
watch triggers 0
outbox pending 0
```

脚本：

```text
scripts/retire_watch_outbox.py
```

## 2. Claims / Reviews 退役

已删除 15 个 trigger：

```text
claim_cards
claim_card_evidence
claim_card_events
review_projects
review_events
```

其中 `review_projects.pico_json` 更新也已 PG-first。

当前：

```text
watch triggers          0
claims/reviews triggers 0
outbox pending          0
剩余 dualwrite triggers 27
```

## 2.1 仍保留的 trigger

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

papers 相关 trigger 暂不能删：

```text
build_sections_tree / build_sentences 仍 SQLite
```

决策：build 脚本也 PG-only，再删 trigger。

详见：[Build 时 Outbox 决策](决策-Build时Outbox策略.md)

详见：[Papers outbox 阻塞](架构-Outbox-Papers阻塞.md)

## 3. 为什么不能继续删

### papers / paragraphs / sentences

```text
paper row PG-first
paragraph/sentence batch 是 best-effort
PG 失败时 outbox 仍是修复路径
```

### figures / tables

```text
build-time 写入
不在 API 运行时
```

### claims / reviews / links

```text
尚未做 PG-first 写路径
```

## 4. 退出条件

```text
所有写路径 fail-closed 或可验证 PG-primary
outbox pending = 0 连续 7 天
drift = 0
一次完整回滚演练
```

## 5. 测试

```text
tests/test_retire_watch_outbox.py
  2 tests OK
```

## 6. 当前生产

```text
watch triggers 0
outbox pending 0
app healthy
```

## 7. 下一步

```text
1. papers children fail-closed 或可验证
2. claims/reviews 写路径
3. figures/tables build-time
4. 再删剩余 trigger
```
