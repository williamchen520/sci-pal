# 实验记录：Paper Data Flow

> 日期：2026-11-14  
> 状态：静态 artifact 读写边；动态调用不猜  
> 目标：从已绑定代码恢复文件/产物级数据流

---

## 1. API

```text
GET /api/papers/<paper_id>/data-flow
```

节点：

```text
file:<path>
artifact:<name>
```

边：

```text
reads
writes
confidence=explicit
method=regex
```

## 2. 支持模式

R/Python 静态调用：

```text
readRDS(file=...)
saveRDS(x, file=...)
read.csv / write.csv
read.table / write.table
fread
read_csv / to_csv
read_parquet / to_parquet
```

## 3. HCC 实测

```text
status ok
nodes  16
edges  16
```

关键边：

```text
Figure.1.R writes Total single-cell atlas.rds
Figure.1.R writes Our single-cell atlas.rds
Figure.2.R reads  Our single-cell atlas.rds
Figure.2.R reads  gene_order_human.txt
Figure.2.R reads  infercnv_result/infercnv.observations.txt
Figure.2.R writes cnvscore.csv
Figure.2.R writes NMFcluster.csv
Figure.3.R reads  Total single-cell atlas.rds
Figure.4.R reads  Total single-cell atlas.rds
Figure.5.R reads  Our single-cell atlas.rds
Figure.6.R reads  P9T/P10T Spatial
Figure.6.R reads  Our single-cell atlas.rds
Figure.6.R writes scenic.data.csv
Figure.7.R reads  Our single-cell atlas.rds
```

## 4. Analysis 聚合

`GET /api/papers/<id>/analysis` 现在包含：

```text
data_flow.status
data_flow.nodes
data_flow.edges
```

实测：

```text
status ok
code bound
bindings 1
flow ok
edges 16
```

## 5. 边界

```text
只抓字符串字面量
动态文件路径不抓
函数内部变量路径不抓
不推断业务含义
不生成 LLM 说明
```

## 6. 测试

```text
reads/writes extraction
unbound
bound library
```

```text
test_paper_flow 3 passed
test_paper_analysis 2 passed
```

## 7. 路由

```text
json_routes=266
app_routes=266
OK
```

## 8. 下一步

```text
1. 变量路径/动态路径标 unresolved
2. module purpose（inferred）
3. Rmd/mixed parser
```
