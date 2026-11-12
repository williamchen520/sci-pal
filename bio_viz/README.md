# BioViz Recipe RAG（Phase 0/1）

> 独立 `scipal_code`，不进入 SciPal 主程序。  
> 当前：20 个配方、2 个样式、12 条查询烟测。

---

## 1. 边界

```text
数据库     scipal_code
schema     code_rag
角色       scipal_code_owner / scipal_code_reader
模型       bge-small-zh-v1.5，512 维
索引       HNSW + pg_trgm
```

不共用：

```text
scipal_core
scipal_rebuild
scipal_docs
```

---

## 2. 当前内容

```text
recipes   20
styles     2（nature_single / nature_double）
queries   12
```

配方：

```text
volcano / MA / PCA / UMAP / dotplot / heatmap
survival / forest / boxplot / UpSet / spatial / enrichment
```

配方字段：

```text
recipe_id, title, chart_type, intent
data_schema, code, packages
style_id, source, license, tested
```

`tested=false`：

```text
代码已做语法检查
未在真实数据上执行/渲染
```

---

## 3. 建库

```bash
psql "$SCIPAL_CODE_DSN" -f bio_viz/schema.sql
```

环境：

```text
SCIPAL_CODE_DSN        owner
SCIPAL_CODE_READ_DSN   reader
SCIPAL_CODE_EMBED_MODEL
SCIPAL_CODE_DEVICE
```

真实 DSN 不提交仓库。

---

## 4. 灌库

```bash
python -m bio_viz.seed
```

输出：

```text
BIOVIZ_SEED_OK recipes=20 styles=2 dim=512
```

---

## 5. 检索

```bash
python -m bio_viz.search "单细胞 UMAP 按细胞类型着色" --top-k 5
```

融合：

```text
pgvector HNSW
pg_trgm title/intent
RRF
```

---

## 6. 烟测

```bash
python -m bio_viz.eval_search --json bio_viz/results/eval.json
```

当前：

```text
queries 12
Hit@1   1.00
Hit@3   1.00
Hit@5   1.00
```

**注意：**

```text
12 条查询是人工按配方写的
配方少、区分度高
不是开放 benchmark
不能说明真实用户查询也 100%
```

---

## 7. 还没做

```text
配方预览图 / 真实数据执行
更多配方（目标 20）
版本/方法追踪
DSH MCP 工具
渲染 + 视觉检查
```

---

## 8. 下一步

```text
1. 配方扩到 20
2. 每个配方加 synthetic data + 渲染预览
3. 建 DSH 工具：bioviz_search / bioviz_render
4. 再做 50 条真实问题
```
