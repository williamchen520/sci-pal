# G3.10g 部署验证

日期：2026-11-06

## 1. 部署

镜像：

```text
ctx72
```

HEAD：

```text
3a9ae75
```

## 2. 启用开关

```text
SCIPAL_SEARCH_META_BACKEND=postgres
SCIPAL_FTS_SQLITE_FALLBACK=0
```

## 3. 20 题回归

```text
Recall@10   0.75
MRR         0.4392
nDCG@10     0.4961
```

与 Chroma 基线一致。

## 4. 任务状态

```text
completed  474
failed       2
cancelled    1
running      0
queued       0
```

启动恢复未误伤任务。

## 5. 已生效

```text
tasks queued/claim/recovery
webhooks PG
hybrid metadata PG
SQLite FTS fallback disabled
```

## 6. 仍未做

```text
SQLite query_only
watch repo 删除
```

## 7. 结论

```text
生产健康
检索指标无回退
PG-only 路径继续收敛
```
