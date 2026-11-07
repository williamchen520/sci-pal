# PG-only 架构迁移备忘录

> 日期：2026-11-07  
> 决策：生产向量只走 PostgreSQL/pgvector  
> 辅助向量搜索：figure / table / chunk / abstract 暂时下线

---

## 1. 决策

```text
段落向量检索       pgvector
论文/图表/表格/块  PG 标量数据保留
辅助向量搜索       暂时下线
Chroma             冻结，不再写入
```

不再保留 Chroma 作为运行时回滚路径。

---

## 2. 范围

### 保留

```text
论文列表/详情
段落检索
证据/引用
图表/表格元数据展示
摘要列表/详情
QA / 综述
```

### 下线

```text
figure 向量搜索
table 向量搜索
chunk 向量搜索
abstract 向量搜索
summary 向量搜索
```

说明：

```text
图表/表格的元数据仍可读
只是不做向量召回
```

---

## 3. 当前依赖

| 位置 | 依赖 | 处理 |
|---|---|---|
| `hybrid_search.py` | paper/fig/table/chunk collections | PG-only 下不初始化 |
| `abstract_search.py` | `chroma_abstracts` | 下线 |
| `ingest.py` | Chroma 写入 | 改 PG |
| `online_downloader.py` | Chroma 写入 | 改 PG |
| `summary_vector_search.py` | Chroma | 下线 |
| `workflow/worker.py` | chroma_path | 移除 |
| `api_server.py` | Chroma embed rows | 移除 |

---

## 4. 运行开关

```text
SCIPAL_VECTOR_BACKEND=pgvector   必需
SCIPAL_AUX_VECTOR_SEARCH=0      默认关闭
```

生产启动检查：

```text
未设置 pgvector -> 启动失败
pgvector 不可用 -> 启动失败
禁止静默回退 Chroma
```

辅助接口行为：

```text
HTTP 410 Gone
code=FEATURE_OFFLINE_PG_ONLY
```

前端：

```text
隐藏 figure/table/chunk/abstract 向量搜索入口
保留普通列表/详情
```

---

## 5. 实施阶段

### P0 冻结

```text
停止 Chroma 写入
Chroma 目录只读
记录当前 166,470 向量为历史快照
```

### P1 主链路 fail-closed

```text
HybridSearch 只在非 pgvector 时导入 chromadb
pgvector 缺失直接报错
段落检索只走 PG
```

### P2 辅助下线

```text
figure/table/chunk/abstract/summary 搜索返回 410
前端隐藏入口
```

### P3 写路径

```text
ingest -> pgvector
worker -> 移除 chroma_path
online_downloader -> 只写 PG
```

### P4 验证

```text
10k 段落检索
20 题回归
引用/证据链路
health/启动日志无 chromadb
```

### P5 清理

```text
移除 chromadb 依赖
归档/删除 data/chroma
删除 chroma_abstracts
```

---

## 6. 验收

```text
1. 启动不再连接 Chroma
2. 生产无 chromadb import
3. 段落检索正常
4. 辅助搜索返回 410，不是 500
5. 前端入口隐藏
6. 20 题指标不退化
7. 10k 语料可检索
8. 备份/恢复仍可用
```

---

## 7. 风险

```text
客户端仍调用旧接口
前端残留入口
图表问答能力下降
PDF 解析仍写 Chroma
测试环境仍依赖 Chroma
```

缓解：

```text
410 明确错误
前端 feature flag
解析写路径先改
测试 fixture 改 PG
```

---

## 8. 不做

```text
不删除图表/表格元数据
不删除摘要
不删除论文
不把 Chroma 当回滚路径
不在迁移中改主检索算法
```

---

## 9. 时间

```text
P0-P2  1 天
P3     1 天
P4     0.5 天
P5     0.5 天
```

单开发者约 3 天。

---

## 10. 结论

```text
主链路 PG-only
辅助向量搜索暂时下线
Chroma 冻结后清理
```

这是一次**能力收缩**，不是检索算法变更；  
先保证主链路稳定，再决定是否用 PG 重建图表/块向量。
