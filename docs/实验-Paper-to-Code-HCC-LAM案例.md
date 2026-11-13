# 案例：HCC 新辅助免疫治疗 LAM 论文 → 代码模块与数据流

> 日期：2026-11-13  
> 状态：PDF 已解析/已补 embedding；R 代码未入 code RAG  
> 结论：文献可读，代码可解释；当前不能声称“代码已解析入库”

---

## 1. 论文

标题：

> Integrated single-cell multi-omics characterization reveals lipid-associated macrophage-mediated immunosuppression in neoadjuvant immunotherapy of hepatocellular carcinoma

- DOI: `10.1038/s41467-026-75949-y`
- 期刊：Nature Communications (2026) 17:9381
- 临床试验：NCT06571396
- PDF: `nature_hcc_lipid_macrophage.pdf`
- PDF SHA256: `50227CAA169C3E98328E344B9CA193D007E773EFB9CC621A1929C95AFEB1CF4E`

### 论文一句话

在 14 例 HCC 新辅助 αPD-1 治疗队列 + 60 例公共 HCC 数据构建约 46 万细胞图谱，发现非应答者中富集 `C1QA/FABP1/APOA1` 的脂质相关巨噬细胞（LAM），并展示其免疫抑制功能与可干预的脂质代谢状态。

---

## 2. PDF 入库状态

解析结果：

```text
paper_id          paper_nature_hcc_lipid_macrophage_b3cb651d2d57
paragraphs        112
figures           9
parse_engine      docling
embeddings        112
```

已做：

```text
PDF 放入 documents/
docling 解析
paragraphs 入库
paragraph_embeddings 补 112 条
papers.title 修正为正式标题
```

尚未确认：

```text
解析后主检索入口没有立即返回这篇
可能是 retriever 进程缓存/索引刷新问题
不能把“已解析”说成“已可检索”
```

---

## 3. 文献要点

### 3.1 研究设计

```text
14 例 HCC 新辅助 αPD-1 治疗
  + 60 例公共 HCC scRNA-seq
= 74 例患者，约 460,000 细胞
```

其中本队列：

```text
14 例，约 120,000 细胞
```

### 3.2 主要发现

```text
非应答者富集 LAM
LAM 标志：C1QA, FABP1, APOA1
LAM 脂质代谢状态升高
LAM 与免疫抑制/治疗抵抗相关
lycopene / chiglitazar 可调节 LAM 脂质状态
```

### 3.3 方法模块

```text
scRNA-seq 整合
Harmony 去批次
UMAP / 聚类 / 注释
inferCNV 恶性细胞识别
Monocle 轨迹
CellChat 配体-受体
CellCall / TF 分析
SCENIC 调控子
scMetabolism 代谢
cNMF 恶性细胞程序
空间转录组验证
```

### 3.4 结论边界

```text
主要是观察性/关联性证据
公共数据背景异质
体外/体内功能实验支持 LAM 免疫抑制
不等于已证明临床可靶向
```

---

## 4. 代码仓库

- GitHub: <https://github.com/Macr0phage/scRNA-seq-of-HCC-immunotherapy>
- 默认分支：`main`
- commit：`6de260e6f63efe8d93f2d4f58eba91d9641e5642`
- 大小：约 16 KB
- 文件：`Figure.1.R` … `Figure.7.R`, `README.md`
- License: **无 LICENSE**

这意味着：

```text
可以阅读/解释
不能默认复制进我们的项目
不能按 MIT/Apache 方式复用
```

---

## 5. 代码结构

```text
Figure.1.R   构建 75 样本图谱，Harmony/UMAP/聚类，CellChat，NMF
Figure.2.R   HCC 上皮细胞亚群，inferCNV，CNV score，cNMF
Figure.3.R   T/NK 亚群，Monocle，CD4/CD8 DEG，GO
Figure.4.R   髓系亚群，Monocle 状态，DEG，KEGG
Figure.5.R   HCC_FA/MacroLA CellChat，CellCall TF/GSEA
Figure.6.R   空间 P9T/P10T，SCENIC，regulon AUC
Figure.7.R   Responder/Non-responder CellChat 对比
```

---

## 6. 各模块功能

### Figure.1 — 主图谱

输入：

```text
14 例本项目 scRNA-seq
61 例公共 HCC 数据（脚本注释 61，正文 60）
```

流程：

```text
merge
JoinLayers
percent.mt QC
NormalizeData / HVG / ScaleData
PCA
Harmony(orig.ident)
UMAP
FindNeighbors / FindClusters
MajorCellType 注释
```

输出：

```text
Total single-cell atlas.rds
Our single-cell atlas.rds
```

附加：

```text
CellChat MainCellType
NMF outgoing patterns
```

### Figure.2 — 恶性 HCC 细胞

输入：

```text
Our single-cell atlas.rds
MainCellType == HCC
```

流程：

```text
HCC 亚群重聚类
inferCNV
CNV 打分
Aneuploid 恶性细胞筛选
二次聚类
cNMF（Python）
```

输出：

```text
cnvscore.csv
infercnv_result/
恶性 HCC 亚群
```

### Figure.3 — T/NK

输入：

```text
Total single-cell atlas.rds
```

流程：

```text
T/NK  subset
Harmony / cluster
Monocle CD8
Monocle CD4
Responder vs Non-responder DEG
GO enrichment
```

### Figure.4 — 髓系

输入：

```text
Total single-cell atlas.rds
```

流程：

```text
Myeloid subset
Harmony / cluster
Monocle states
state DEG
KEGG enrichment
```

### Figure.5 — LAM 通讯

输入：

```text
Our single-cell atlas.rds
```

流程：

```text
CellChat: HCC_FA ↔ MacroLA
bubble plot
Myeloid subset
CellCall: MacroLA TF / GSEA
PPARD
```

### Figure.6 — 空间 + SCENIC

输入：

```text
P9T_Spatial.rds
P10T_Spatial.rds
Our single-cell atlas.rds
```

流程：

```text
SpatialDimPlot / SpatialFeaturePlot
APOA1 / FABP1 / C1QA
Myeloid subset
R 导出 scenic.data.csv
Python pyscenic grn/ctx/aucell
R 读 aucell.loom
regulon AUC by Response
```

这是一个典型的 **R + Python 混合模块**。

### Figure.7 — 应答者 vs 非应答者通讯

输入：

```text
Our single-cell atlas.rds
Response == Responder / Non-responder
```

流程：

```text
分别构建 CellChat
mergeCellChat
diff interaction
outgoing/incoming strength
pathway heatmap
SPP1 / APOA hierarchy
```

---

## 7. 数据流

```text
raw scRNA / public datasets
        │
        ▼
Figure.1  merge + QC + Harmony + cluster
        │
        ├── Total atlas.rds
        └── Our atlas.rds
                 │
     ┌───────────┼────────────┬────────────┐
     ▼           ▼            ▼            ▼
 Figure.2     Figure.3    Figure.4     Figure.5
 HCC/inferCNV T/NK         Myeloid      LAM CellChat
     │           │            │            │
     └───────────┴────────────┴────────────┘
                       │
                       ▼
             Figure.6 空间/SCENIC
                       │
                       ▼
             Figure.7 R vs NR 通讯
```

---

## 8. 代码质量问题

```text
没有函数封装
没有 tests
没有 set.seed
大量 rm(list=ls())
依赖 .rds 中间文件
输入数据未随仓库提供
Figure.6 混入 Python 代码但没有 .py 文件
没有 LICENSE
```

所以：

```text
不能直接运行
不能直接复制
只能作为方法/模块参考
```

---

## 9. 当前 code RAG 状态

```text
仓库已下载
代码未入 code RAG
原因：R parser 未实现
```

现有解析器：

```text
Python     tree-sitter
Nextflow   block scanner
R          none
```

这正是设计 `Language Provider` 要补的缺口。

---

## 10. 下一步

```text
1. 重启/刷新文献 retriever，让新 paper 可检索
2. 实现 R parser（函数/脚本/Rmd）
3. 按 Figure 模块建立 per-paper code library
4. 先解释模块，不复制代码
5. 若要复刻，先选一个小目标（如 Figure.1 QC/Harmony）
```

---

## 11. 结论

```text
文献：已解析，有 embedding，但检索入口尚未确认
代码：已下载，无 license，R parser 缺失，未入库
解释：可以按 Figure 脚本说明模块和数据流
复刻：只能做方法级/小目标，不能声称整篇复现
```
