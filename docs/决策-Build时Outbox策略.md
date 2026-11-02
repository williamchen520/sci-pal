# 决策：Build 阶段与 Outbox 策略

> 日期：2026-11-02  
> 决策：**A. build 脚本也 PG-only，分阶段执行。**

## 1. 背景

运行时写路径已基本 PG-first，但 `papers/sections/paragraphs/sentences` 的 outbox trigger 仍保留。

原因是：

```text
build_db/build_sections_tree.py
build_db/build_sentences.py
```

仍直接写 SQLite。

## 2. 三个选项

### A. Build 脚本 PG-only

```text
build_sections_tree -> PG sections
build_sentences     -> PG sentences
SQLite 只保留 FTS/兼容读取
```

优点：

```text
运行时和 build 都不依赖 trigger
最终可以真正删 papers trigger
```

缺点：

```text
需要改两个离线脚本
SQLite FTS 需要单独 rebuild
```

### B. 接受 build 阶段使用 outbox

```text
保留 trigger
build 继续 SQLite + outbox
```

优点：

```text
改动小
FTS 不受影响
```

缺点：

```text
永远无法真正停 outbox
跨库状态继续存在
```

### C. 运行时删 trigger，build 时临时启用

```text
正常生产：无 trigger
build 时：install triggers -> build -> replay -> drop
```

优点：

```text
运行时干净
```

缺点：

```text
操作步骤复杂
忘记 drop 就回到旧状态
容易产生隐性依赖
```

## 3. 决策

```text
选 A
不选 B
不选 C
```

理由：

```text
目标就是 PG 单库
B 会让 outbox 永久化
C 把正确性依赖在运维步骤上
A 的工作量集中在两个离线脚本，边界清楚
```

## 4. 执行顺序

```text
Phase A1
  build_sections_tree.py -> PG sections
  build_sentences.py -> PG sentences

Phase A2
  SQLite FTS rebuild 保持独立
  不让 FTS 阻塞 PG 写入

Phase A3
  验证 PG sections/sentences 与 SQLite 一致
  连续 7 天 outbox pending=0

Phase A4
  drop papers/sections/paragraphs/sentences triggers
```

## 5. 验收

```text
build 过程不产生新的 outbox 行
PG sections/sentences count 与 build 输入一致
SQLite FTS 仍可重建
papers trigger 删除后 watch/ingest 正常
```

## 6. 回滚

```text
保留 trigger SQL
保留 outbox 表
保留 SQLite 原表
必要时重新 install trigger
```

## 7. 当前状态

```text
决策：A
实现：未开始
papers trigger：保留
```

下一步先改 `build_sections_tree.py`，再改 `build_sentences.py`。
