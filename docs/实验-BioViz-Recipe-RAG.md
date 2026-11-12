# 实验记录：BioViz Recipe RAG Phase 0/1

> 日期：2026-11-12  
> 状态：**独立库与配方检索跑通；配方未执行/未渲染**  
> 代码：`bio_viz/`

---

## 1. 目标

验证：

```text
Python 生信绘图配方能否独立建库
能否按中文意图检索到正确配方
能否与 SciPal 主库完全隔离
```

不验证：

```text
AI 生成的图是否好看
配方能否在真实数据上运行
DSH 工具集成
版本/方法追踪
```

---

## 2. 独立库

```text
数据库     scipal_code
schema     code_rag
角色       scipal_code_owner / scipal_code_reader
模型       bge-small-zh-v1.5，512 维
索引       HNSW + pg_trgm
```

表：

```text
recipes
styles
packages
embeddings
ingest_runs
```

没有共用：

```text
scipal_core
scipal_rebuild
scipal_docs
```

---

## 3. 配方

```text
12 个配方
2 个样式（nature_single / nature_double）
```

覆盖：

```text
火山图
MA 图
PCA
UMAP
marker dotplot
聚类热图
Kaplan-Meier
森林图
箱线图
UpSet
空间转录组
富集点图
```

每个配方包含：

```text
title
chart_type
intent
data_schema
code
packages
style_id
source / license
tested
```

当前：

```text
code 通过 Python compile() 语法检查
tested=false，未真实执行/渲染
```

---

## 4. 检索

```text
pgvector HNSW
pg_trgm title/intent
RRF 融合
```

命令：

```bash
python -m bio_viz.search "单细胞 UMAP 按细胞类型着色" --top-k 5
```

---

## 5. 烟测

```text
12 条人工查询
12 个配方
```

结果：

```text
Hit@1  1.00
Hit@3  1.00
Hit@5  1.00
```

结果文件：

```text
bio_viz/results/eval.json
```

注意：

```text
查询是按配方人工写的
配方少、区分度高
不是开放 benchmark
不能说明真实用户查询也 100%
```

---

## 6. 已知缺口

```text
没有预览图 / 真实数据执行
没有视觉质量评估
没有 20 个配方
没有版本/方法追踪
没有 DSH 工具
没有自动 patch
```

---

## 7. 下一步

```text
1. 配方扩到 20
2. 每个配方加 synthetic data + 渲染预览
3. 加 50 条真实问题
4. 做 DSH bioviz_search / bioviz_render
5. 再评人工偏好与可运行率
```

---

## 8. 结论

```text
独立 scipal_code 建库成功
12 个配方可检索
中文意图 → 配方烟测 12/12
还不能证明真实生信画图质量
不接 DSH、不自动改代码
```
