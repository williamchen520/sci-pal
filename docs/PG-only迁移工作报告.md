# PG-only 迁移工作报告

> 日期：2026-11-07  
> 范围：SciPal 向量与业务存储去 Chroma、PG-only 收口  
> 结论：主链路完成；仍有少量历史分支/只读 SQLite 残留

---

## 1. 执行摘要

已完成：

```text
paragraph 向量           pgvector
ingest 写路径            pgvector
生产向量后端             SCIPAL_VECTOR_BACKEND=pgvector
Chroma 运行路径          已切断
Chroma 数据              已归档到 I 盘
chromadb 源码依赖        已从 requirements 移除
辅助向量搜索             figure/table/chunk/abstract 暂时下线
```

当前规模：

```text
papers                 10,102
paragraphs            331,263
paragraph_embeddings  320,928
HNSW                  valid / 1.235 GB
PG database           约 5.4 GB
```

验证：

```text
app health 200
20 题 Recall@10 0.675 / nDCG@10 0.461
SciFact 300 Recall@10 0.8669 / nDCG@10 0.7458
```

---

## 2. 已完成项

| 项目 | 状态 | 证据 |
|---|---|---|
| paragraph 向量检索 | 完成 | `SCIPAL_VECTOR_BACKEND=pgvector` |
| HNSW 重建 | 完成 | 320,928 条，索引 valid |
| ingest 写 PG | 完成 | `_default_embed` PG 分支 |
| Chroma 初始化 | 切断 | PG-only 下 `client=None` |
| Chroma 数据 | 归档 | `I:\_archive\chroma-20261107` |
| chromadb 依赖 | 源码移除 | `requirements.txt` 无 chromadb |
| 辅助搜索 | 下线 | 集合为 None / 返回空 |
| 10k 扩容 | 完成 | 10,102 篇 |

---

## 3. 残余清单

### 3.1 功能性残留

| 残留 | 影响 | 优先级 |
|---|---|---|
| `AbstractSearch.fts_search` 仍读 `abstracts.db` | abstract FTS 仍可用，不是完全下线 | P1 |
| `HybridSearch` 仍打开 `research.db` | 只读 SQLite 快照仍在部分读路径 | P1 |
| `build_embeddings.py` 默认 Chroma | 开发构建脚本仍默认旧路径 | P2 |
| `build_chunks.py` 等 Chroma 构建脚本 | 辅助索引仍只能建 Chroma | P2 |
| `summary_vector_search` Chroma 分支 | lazy 代码仍在 | P2 |
| `api_server.get_embed_rows` Chroma 写函数 | 死代码，PG-only 不调用 | P3 |
| `online_downloader` Chroma 分支 | PG-only 提前 return | P3 |

### 3.2 镜像/环境残留

```text
当前 scipal-app:latest 的 base 层仍安装 chromadb
运行时不再 import/连接
```

原因：

```text
scipal-base:py312 被清理过
本次用现有 app 镜像临时打 base 标签构建
```

彻底清理需要重建 `scipal-base`。

### 3.3 数据残留

```text
G:\sciPal_deploy\data\research.db        1.75 GB
G:\sciPal_deploy\data\abstracts.db       49 MB
G:\sciPal_deploy\data\chroma_abstracts.empty-*  空目录
```

`research.db` 仍是 query-only 只读快照，不是 Chroma，但也不是 100% PG-only。

### 3.4 文档残留

```text
README.md
README.zh-CN.md
docs/架构.md
docs/架构总览.md
docs/en/Architecture-Overview.md
```

仍可能描述 Chroma 架构，需要后续统一。

---

## 4. 关键决策

### 决策 1：主链路 PG-only，不做双热栈

```text
pgvector 生产
Chroma 退出运行
```

原因：

```text
双栈存储翻倍
写入一致性复杂
回滚价值低于维护成本
```

### 决策 2：Chroma 数据先归档，不直接删除

```text
G -> I:\_archive
```

原因：

```text
保留取证/回滚可能
避免误删
```

### 决策 3：辅助向量搜索暂时下线

```text
figure / table / chunk / abstract
```

原因：

```text
没有 PG 向量表
重建成本高
主链路不依赖
```

代价：

```text
图表/块/摘要向量召回能力下降
```

### 决策 4：HNSW 参数不再继续调

```text
ef_construction 64 -> 100
ef_search 200 -> 1000
overfetch
```

结果：

```text
20 题完全一致
```

结论：

```text
指标差异不是 HNSW 参数造成
```

### 决策 5：HNSW 构建用 2 workers × 2GB

```text
1GB/worker 在 284,906 条时超出内存
2GB/worker × 2 成功
```

### 决策 6：10k 只导入 6,300 篇去重条目

```text
下载 10,000
去重 kept 9,277
导入 6,300
总库 10,102
```

原因：

```text
目标总规模 1 万
避免超量
```

### 决策 7：300 全文评测列入备选

```text
没有可靠 gold
人工标注精力不足
等公开集
```

### 决策 8：不把 GraphRAG 放主架构

```text
作为插件实验
baseline 不变
```

---

## 5. 遇到的问题

### 5.1 PG 双容器同时挂载同一 pgdata

现象：

```text
WAL 文件缺失
checkpoint 报错
```

处理：

```text
立即停旧容器
重建新容器
schema dump/计数正常
```

教训：

```text
重建 PG 必须先停旧容器
不能两个进程同写一个数据目录
```

### 5.2 基础镜像被清理

现象：

```text
FROM scipal-base:py312 拉取失败
```

处理：

```text
临时 tag 现有 app 镜像为 base
```

遗留：

```text
base 层仍含 chromadb
```

### 5.3 HNSW 构建内存不足

现象：

```text
hnsw graph no longer fits into maintenance_work_mem
```

处理：

```text
1GB/worker -> 2GB/worker × 2
```

### 5.4 10k 导入极慢

原因：

```text
paper_id 上没有索引
DELETE 全表扫描
```

处理：

```text
补 paragraphs/sentences/citations/figures/sections/sentence_links/tables 索引
```

### 5.5 Chroma 与 PG 规模不一致

```text
Chroma paragraphs 166,470
PG                 320,928
```

影响：

```text
10k 无法与 Chroma 做同规模对照
```

### 5.6 向量索引污染

```text
38,705 / 327,875 被标记（11.8%）
```

高置信删除：

```text
6,947 条
```

结果：

```text
20 题无变化
```

### 5.7 规模上升后 20 题下降

```text
3,802 篇 0.725 / 0.4847
10,102 篇 0.675 / 0.4610
```

判断：

```text
候选段落 17.6 万 -> 33.1 万
干扰项增加
不是后端切换导致
```

---

## 6. 指标汇总

| 实验 | 规模 | Recall@10 | nDCG@10 |
|---|---:|---:|---:|
| Chroma 内部 | 20 题 | 0.7500 | 0.4961 |
| pgvector 内部 | 20 题 | 0.7250 | 0.4847 |
| pgvector SciFact | 300 题 | 0.8669 | 0.7458 |
| Chroma SciFact | 300 题 | 0.8669 | 0.7470 |
| pgvector 10k | 20 题 | 0.6750 | 0.4610 |

判断：

```text
pgvector 非劣
不能声称更优
```

---

## 7. 后续清理建议

### P1

```text
关闭 AbstractSearch.fts_search 的 SQLite 路径
或在 PG-only 下整体返回空
```

### P1

```text
评估 research.db 剩余读路径
逐项迁 PG 或明确保留为只读快照
```

### P2

```text
build_embeddings.py 默认改 PG
build_chunks 等脚本标记 legacy
```

### P2

```text
重建 scipal-base，真正移除 chromadb
```

### P3

```text
清理空目录/文档旧描述
```

---

## 8. 验收结论

```text
PG-only 主链路：通过
向量后端：通过
10k 规模：通过
辅助向量搜索：明确下线
全代码库无 Chroma：未完全达到
全业务库 PG-only：未完全达到
```

准确表述：

```text
SciPal 已完成“向量与写入 PG-only”
尚未完成“全代码/全读路径 PG-only”
```

---

## 9. 产物

```text
docs/PG-only架构迁移备忘录.md
docs/向量索引污染审查.md
docs/1万篇扩容结果.md
docs/检索实验报告-2026-11-07.md
```
