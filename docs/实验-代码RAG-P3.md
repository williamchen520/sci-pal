# 实验记录：code-rag P3 检索

> 日期：2026-11-12  
> 状态：**code_search 可用；10 条内部问题烟测**  
> 模块：`code_rag/`

---

## 1. 目标

验证：

```text
code_units 能否建 embedding
检索能否按 library_id 隔离
exact symbol + trigram + vector 能否组合
结果能否回到 path/line/symbol
```

不验证：

```text
对外部用户真实查询的泛化
DSH 工具调用
跨 repo 联合检索
版本/API diff
```

## 2. 索引

```text
scanpy      1,611 units
rnaseq        505 units
合计        2,116 units
model       bge-small-zh-v1.5
dim         512
```

跳过：

```text
file 级 unit
```

## 3. 检索

```bash
python -m code_rag.search \
  "normalize total counts" \
  --library-id lib_xxx --top-k 5
```

融合：

```text
exact symbol
symbol token boost
pg_trgm
pgvector HNSW
RRF
```

硬过滤：

```text
library_id
snapshot_id（可选）
unit_type <> 'file'
```

## 4. 10 条内部问题

```text
Hit@1 0.80
Hit@5 1.00
```

结果文件：

```text
code_rag/results/eval.json
```

命中：

```text
normalize_total
read_10x_h5
highly_variable_genes
FASTQC
STAR_ALIGN
SALMON_QUANT
MULTIQC
FASTP
```

未中 Top1：

```text
UMAP    -> embedding 排 1，umap 排 2
neighbor -> Neighbors 排 1，neighbors 排 4
```

## 5. 解释

### 5.1 exact symbol 很重要

代码查询里：

```text
符号精确匹配 > 向量语义
```

没有 symbol boost 时：

```text
Hit@1 0.10
Hit@5 0.70
```

加 token/精确符号 boost 后：

```text
Hit@1 0.80
Hit@5 1.00
```

### 5.2 测试/benchmark 会干扰

`tests/`、`benchmarks/` 里的同名函数会进入候选。  
P4/P5 应加：

```text
path 过滤
unit_type/priority
测试文件降权
```

### 5.3 这不是开放 benchmark

```text
10 条问题按 repo 手写
query 和 symbol 区分度高
不能说明真实用户查询也 80%
```

## 6. 已知缺口

```text
没有 code_trace
没有 DSH MCP
没有跨 repo 搜索
没有版本过滤 UI
没有 rerank
```

## 7. 下一步

```text
P4：DSH scipal-code MCP（只读）
  code_search
  code_status
  code_trace
```

先只读，不做写工具。
