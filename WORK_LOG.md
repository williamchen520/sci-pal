# SciPal 工作日志

> 记录关键阶段、合并点与遗留问题。详细技术报告见 `docs/`。  
> 最新版本以 `VERSION` 为准。

---

## 2026-10-27

### 插件端口 M0

```text
PR #120
PortSpec / PluginManifest / PluginRun
registry + runner + JSONL provenance
```

### ClaimVerifier M1

```text
PR #121
NLI / rule / underdetermines 三个 adapter
```

### 平衡 claim 数据集

```text
PR #122
10 support / 10 refute / 10 underdetermine
```

### RetrieverPort M2

```text
PR #123
BM25 / dense / hybrid / hybrid-rerank
```

---

## 2026-10-31

### M2 检索集扩展

```text
PR #124
54 → 74 queries；32 → 100 papers
修复 hybrid adapter 的 paper_id 元数据读取
```

### Benchmark PostgreSQL 策略

```text
PR #125
>100 篇或并发测试必须 PostgreSQL
小规模 SQLite 必须显式 opt-in
```

### README Development Note

```text
PR #126
```

### PostgreSQL P0 基线

```text
PR #128
双盘 SQLite 快照
backup_sqlite.py
sha256 + integrity_check
```

### PostgreSQL P1 schema / adapter

```text
PR #129
60 张表
tsvector + GIN
SQLite / PostgreSQL DBAdapter
```

### PostgreSQL P2 只读 ETL

```text
PR #130
snapshot-only ETL
COPY writer
dry-run / checksum
```

### P2 真实 COPY 验证

```text
PR #131
citations.year 改为 TEXT
60 表 / 2,015,676 行
count mismatch 0
papers / paragraphs / sentences diff 0
```

### 跨平台路径体检

```text
PR #132
config/paths.py
清理 D:/G:/home 硬编码
tempfile / pathlib 规范
scripts/check_portability.py
Windows 开发警示文档
```

---

## 当前状态

```text
测试：716 项通过
PostgreSQL：60 表 / 2,015,676 行
默认数据库：SQLite
生产目标：Linux
```

## 遗留问题

```text
1. P3 影子读尚未开始
2. 30 条独立 claim 人工标注未完成
3. self_check 旧检查已修复；后续新增检查需同步测试
4. Linux 真机尚未跑完整 benchmark
```
