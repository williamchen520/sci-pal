# Worklog: 修复摘要库 papers_fts

> 日期：2026-11-04  
> PR：Pending Review

## 1. 现象

`/api/evidence/search` 日志：

```text
摘要 FTS 搜索失败: no such table: papers_fts
```

## 2. 根因

生产数据目录：

```text
G:\sciPal_deploy\data\abstracts.db       0 bytes
G:\sciPal_deploy\data\chroma_abstracts   空壳
```

D 盘有完整副本：

```text
D:\sciPal\data\abstracts.db              51,781,632 bytes
D:\sciPal\data\chroma_abstracts         71 MB
```

## 3. 修复

```text
1. 停 app
2. 备份空壳
3. 复制 D abstracts.db -> G
4. 复制 D chroma_abstracts -> G
5. 启动 app
```

恢复后：

```text
papers       3,923
papers_fts   3,855
missing      68
```

补齐 68 条并安装 trigger：

```text
papers_ai / papers_ad / papers_au
最终 papers_fts = 3,923
```

## 4. 验证

直连 FTS：

```text
query: hepatocellular carcinoma
hits: 3
top pmid: 42803632
```

app：

```text
health 200
healthy
```

## 5. 备份

```text
D:\sciPal\backups\abstracts_before_fts_20261104.db
```

空壳备份：

```text
G:\sciPal_deploy\data\abstracts.db.empty-*
G:\sciPal_deploy\data\chroma_abstracts.empty-*
```

## 6. 测试

```text
tests.test_repair_abstract_fts 2 OK
全量 845 tests OK
```

## 7. 说明

完整 `/api/evidence/search` 仍慢，原因是 contextual/hybrid/rerank，不是摘要 FTS。

## 8. 未完成项

```text
PR Pending Review
完整请求 profile
```
