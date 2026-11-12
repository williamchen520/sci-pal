"""Curated BioViz recipes (phase 0/1 seed data)."""

RECIPES = [
    {
        "recipe_id": "viz_volcano",
        "title": "Publication-quality volcano plot",
        "chart_type": "volcano",
        "intent": "差异表达火山图，标注显著基因，色盲友好，适合单栏",
        "data_schema": "DataFrame with columns: gene, log2fc, pvalue, padj",
        "packages": [["matplotlib", ">=3.8"], ["numpy", ">=1.26"], ["pandas", ">=2.0"]],
        "style_id": "nature_single",
        "code": """import numpy as np
import matplotlib.pyplot as plt

df["neglog10"] = -np.log10(df["pvalue"].clip(lower=1e-300))
df["sig"] = np.where((df["log2fc"].abs() >= 1) & (df["padj"] < 0.05), "sig", "ns")
fig, ax = plt.subplots(figsize=(3.5, 3.2))
ax.scatter(df.loc[df.sig == "ns", "log2fc"], df.loc[df.sig == "ns", "neglog10"],
           s=8, c="#BDBDBD", alpha=0.7, linewidths=0)
ax.scatter(df.loc[df.sig == "sig", "log2fc"], df.loc[df.sig == "sig", "neglog10"],
           s=10, c="#D55E00", alpha=0.9, linewidths=0)
ax.axvline(-1, ls="--", lw=0.6, c="#666666")
ax.axvline(1, ls="--", lw=0.6, c="#666666")
ax.axhline(-np.log10(0.05), ls="--", lw=0.6, c="#666666")
for _, row in df.nlargest(5, "neglog10").iterrows():
    ax.annotate(row["gene"], (row["log2fc"], row["neglog10"]), fontsize=6)
ax.set_xlabel("log2 fold change")
ax.set_ylabel("-log10 P")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("volcano.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_ma",
        "title": "MA plot for differential expression",
        "chart_type": "ma",
        "intent": "MA 图，展示表达均值与 log2 fold change，适合 RNA-seq",
        "data_schema": "DataFrame with columns: gene, baseMean, log2fc, padj",
        "packages": [["matplotlib", ">=3.8"], ["numpy", ">=1.26"]],
        "style_id": "nature_single",
        "code": """import numpy as np
import matplotlib.pyplot as plt

df["A"] = np.log2(df["baseMean"].clip(lower=1))
df["sig"] = df["padj"] < 0.05
fig, ax = plt.subplots(figsize=(3.5, 3.2))
ax.scatter(df.loc[~df.sig, "A"], df.loc[~df.sig, "log2fc"], s=7, c="#BDBDBD", linewidths=0)
ax.scatter(df.loc[df.sig, "A"], df.loc[df.sig, "log2fc"], s=8, c="#0072B2", linewidths=0)
ax.axhline(0, lw=0.6, c="#444444")
ax.set_xlabel("log2 mean expression")
ax.set_ylabel("log2 fold change")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("ma.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_pca",
        "title": "PCA scatter with explained variance",
        "chart_type": "pca",
        "intent": "PCA 降维散点图，显示样本分组和解释方差",
        "data_schema": "DataFrame with numeric feature columns + group column",
        "packages": [["scikit-learn", ">=1.3"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import matplotlib.pyplot as plt
from sklearn.decomposition import PCA

features = [c for c in df.columns if c != "group"]
pca = PCA(n_components=2, random_state=0)
coords = pca.fit_transform(df[features].to_numpy())
fig, ax = plt.subplots(figsize=(3.5, 3.2))
for group, part in df.assign(PC1=coords[:, 0], PC2=coords[:, 1]).groupby("group"):
    ax.scatter(part["PC1"], part["PC2"], s=18, label=group, alpha=0.9)
ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")
ax.legend(frameon=False, fontsize=6)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("pca.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_umap",
        "title": "Scanpy UMAP colored by cell type",
        "chart_type": "umap",
        "intent": "单细胞 UMAP，按细胞类型着色，点小、图例清晰",
        "data_schema": "AnnData with obsm['X_umap'] and obs['cell_type']",
        "packages": [["scanpy", ">=1.10"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_double",
        "code": """import scanpy as sc
import matplotlib.pyplot as plt

sc.pl.umap(
    adata,
    color="cell_type",
    frameon=False,
    size=6,
    legend_loc="on data",
    legend_fontsize=6,
    show=False,
)
fig = plt.gcf()
fig.set_size_inches(6.5, 4.0)
fig.savefig("umap.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_dotplot",
        "title": "Marker gene dot plot",
        "chart_type": "dotplot",
        "intent": "单细胞 marker 基因点图，展示表达比例和平均表达",
        "data_schema": "AnnData with obs['cell_type'], var_names marker genes",
        "packages": [["scanpy", ">=1.10"]],
        "style_id": "nature_double",
        "code": """import scanpy as sc

sc.pl.dotplot(
    adata,
    var_names=marker_genes,
    groupby="cell_type",
    standard_scale="var",
    show=False,
    figsize=(7, 3),
)
""",
    },
    {
        "recipe_id": "viz_heatmap",
        "title": "Clustered heatmap with z-score",
        "chart_type": "heatmap",
        "intent": "聚类热图，按行 z-score，色盲友好发散色",
        "data_schema": "DataFrame genes x samples, numeric",
        "packages": [["seaborn", ">=0.13"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_double",
        "code": """import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import zscore

z = df.apply(zscore, axis=1)
g = sns.clustermap(
    z,
    cmap="RdBu_r",
    center=0,
    vmin=-2, vmax=2,
    linewidths=0,
    figsize=(7, 5),
    cbar_kws={"label": "z-score"},
)
g.ax_heatmap.set_xlabel("")
g.ax_heatmap.set_ylabel("")
g.fig.savefig("heatmap.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_survival",
        "title": "Kaplan-Meier survival curves",
        "chart_type": "survival",
        "intent": "生存曲线，显示风险人数和 log-rank p 值",
        "data_schema": "DataFrame with time, event, group",
        "packages": [["lifelines", ">=0.30"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test

fig, ax = plt.subplots(figsize=(3.5, 3.2))
for group, part in df.groupby("group"):
    km = KaplanMeierFitter()
    km.fit(part["time"], part["event"], label=group)
    km.plot_survival_function(ax=ax, ci_show=False, lw=1.2)
groups = list(df["group"].unique())
if len(groups) == 2:
    a, b = (df[df.group == g] for g in groups)
    p = logrank_test(a.time, b.time, a.event, b.event).p_value
    ax.text(0.05, 0.05, f"log-rank P={p:.3g}", transform=ax.transAxes, fontsize=6)
ax.set_xlabel("Time")
ax.set_ylabel("Survival probability")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_forest",
        "title": "Forest plot for hazard ratios",
        "chart_type": "forest",
        "intent": "森林图，展示 HR/OR 和置信区间，零线参考",
        "data_schema": "DataFrame with term, estimate, ci_low, ci_high",
        "packages": [["matplotlib", ">=3.8"], ["numpy", ">=1.26"]],
        "style_id": "nature_single",
        "code": """import numpy as np
import matplotlib.pyplot as plt

y = np.arange(len(df))[::-1]
fig, ax = plt.subplots(figsize=(3.5, max(3.0, 0.28 * len(df))))
ax.errorbar(df["estimate"], y, xerr=[df["estimate"] - df["ci_low"], df["ci_high"] - df["estimate"]],
            fmt="o", color="#0072B2", ecolor="#555555", capsize=2, ms=4)
ax.axvline(1, ls="--", lw=0.7, c="#999999")
ax.set_yticks(y)
ax.set_yticklabels(df["term"], fontsize=6)
ax.set_xlabel("Hazard ratio (95% CI)")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_boxplot",
        "title": "Boxplot with individual points and statistics",
        "chart_type": "boxplot",
        "intent": "分组箱线图叠加散点，显示分布和显著性",
        "data_schema": "DataFrame with group and value",
        "packages": [["seaborn", ">=0.13"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import seaborn as sns
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(3.5, 3.2))
sns.boxplot(data=df, x="group", y="value", width=0.55, fliersize=0,
            color="#E6E6E6", linewidth=0.8, ax=ax)
sns.stripplot(data=df, x="group", y="value", size=3, alpha=0.7,
              jitter=0.18, color="#0072B2", ax=ax)
ax.set_xlabel("")
ax.set_ylabel("Value")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_upset",
        "title": "UpSet plot for overlapping gene sets",
        "chart_type": "upset",
        "intent": "多集合交集 UpSet 图，替代 Venn 图",
        "data_schema": "DataFrame boolean columns for set membership",
        "packages": [["upsetplot", ">=0.9"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_double",
        "code": """import matplotlib.pyplot as plt
from upsetplot import from_memberships, plot

memberships = df.apply(lambda row: [c for c in df.columns if row[c]], axis=1)
data = from_memberships(memberships)
plot(data, show_counts=True, sort_by="cardinality")
fig = plt.gcf()
fig.set_size_inches(6.5, 4.0)
fig.savefig("upset.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_spatial",
        "title": "Spatial transcriptomics scatter",
        "chart_type": "spatial",
        "intent": "空间转录组切片散点图，按细胞类型/基因着色",
        "data_schema": "AnnData with obsm['spatial'] and obs['cell_type']",
        "packages": [["squidpy", ">=1.5"], ["scanpy", ">=1.10"]],
        "style_id": "nature_double",
        "code": """import squidpy as sq
import matplotlib.pyplot as plt

sq.pl.spatial_scatter(
    adata,
    color="cell_type",
    shape=None,
    size=1.2,
    img=False,
    frameon=False,
    legend_loc="right margin",
)
fig = plt.gcf()
fig.set_size_inches(6.5, 4.5)
fig.savefig("spatial.pdf", dpi=300, bbox_inches="tight")
""",
    },
    {
        "recipe_id": "viz_enrichment",
        "title": "Enrichment dot plot",
        "chart_type": "enrichment",
        "intent": "富集分析点图，展示 gene ratio、p 值和通路",
        "data_schema": "DataFrame with term, gene_ratio, pvalue, count",
        "packages": [["matplotlib", ">=3.8"], ["seaborn", ">=0.13"]],
        "style_id": "nature_single",
        "code": """import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

top = df.nsmallest(15, "pvalue").copy()
top["neglog10"] = -np.log10(top["pvalue"].clip(lower=1e-300))
fig, ax = plt.subplots(figsize=(4.2, 3.8))
sns.scatterplot(data=top, x="gene_ratio", y="term", size="count",
                hue="neglog10", palette="viridis", sizes=(20, 120),
                edgecolor="white", linewidth=0.4, ax=ax)
ax.set_xlabel("Gene ratio")
ax.set_ylabel("")
ax.legend(frameon=False, fontsize=6, bbox_to_anchor=(1.0, 1.0))
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
]

STYLES = [
    {
        "style_id": "nature_single",
        "name": "Nature single column",
        "spec": {
            "width_mm": 89,
            "dpi": 300,
            "font_family": "Arial",
            "font_size_pt": 7,
            "palette": "Okabe-Ito",
            "line_width_pt": 0.8,
            "save_formats": ["pdf", "png"],
        },
    },
    {
        "style_id": "nature_double",
        "name": "Nature double column",
        "spec": {
            "width_mm": 183,
            "dpi": 300,
            "font_family": "Arial",
            "font_size_pt": 8,
            "palette": "Okabe-Ito",
            "line_width_pt": 0.9,
            "save_formats": ["pdf", "png"],
        },
    },
]


RECIPES.extend([
    {
        "recipe_id": "viz_violin",
        "title": "Violin plot with individual points",
        "chart_type": "violin",
        "intent": "分组小提琴图叠加散点，展示分布形状和样本量",
        "data_schema": "DataFrame with group and value",
        "packages": [["seaborn", ">=0.13"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import seaborn as sns
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(3.5, 3.2))
sns.violinplot(data=df, x="group", y="value", inner=None, cut=0,
               color="#D9D9D9", linewidth=0.7, ax=ax)
sns.stripplot(data=df, x="group", y="value", size=3, alpha=0.7,
              jitter=0.18, color="#0072B2", ax=ax)
ax.set_xlabel("")
ax.set_ylabel("Value")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_line",
        "title": "Time-course line plot with error band",
        "chart_type": "line",
        "intent": "时间序列折线图，按组分色并显示标准差带",
        "data_schema": "DataFrame with time, value, group",
        "packages": [["seaborn", ">=0.13"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import seaborn as sns
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(3.5, 3.2))
sns.lineplot(data=df, x="time", y="value", hue="group",
             errorbar="sd", marker="o", ms=3, lw=1.1, ax=ax)
ax.set_xlabel("Time")
ax.set_ylabel("Value")
ax.legend(frameon=False, fontsize=6)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_bar_error",
        "title": "Bar chart with error bars",
        "chart_type": "bar",
        "intent": "分组柱状图叠加误差线，适合均值比较",
        "data_schema": "DataFrame with group, mean, sd",
        "packages": [["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(3.5, 3.2))
ax.bar(df["group"], df["mean"], yerr=df["sd"], capsize=3,
       color="#D9D9D9", edgecolor="#333333", linewidth=0.7)
ax.set_xlabel("")
ax.set_ylabel("Mean")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_scatter_reg",
        "title": "Scatter plot with regression line",
        "chart_type": "scatter",
        "intent": "散点图加回归线和置信带，展示连续变量关系",
        "data_schema": "DataFrame with x and y",
        "packages": [["seaborn", ">=0.13"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import seaborn as sns
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(3.5, 3.2))
sns.regplot(data=df, x="x", y="y", scatter_kws={"s": 8, "alpha": 0.6},
            line_kws={"lw": 1.0, "color": "#D55E00"}, ax=ax)
ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_roc",
        "title": "ROC curve with AUC",
        "chart_type": "roc",
        "intent": "ROC 曲线，显示 AUC，适合分类模型评估",
        "data_schema": "DataFrame or arrays y_true, y_score",
        "packages": [["scikit-learn", ">=1.3"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score, roc_curve

fpr, tpr, _ = roc_curve(y_true, y_score)
auc = roc_auc_score(y_true, y_score)
fig, ax = plt.subplots(figsize=(3.5, 3.2))
ax.plot(fpr, tpr, lw=1.2, color="#0072B2", label=f"AUC={auc:.3f}")
ax.plot([0, 1], [0, 1], ls="--", lw=0.7, c="#999999")
ax.set_xlabel("False positive rate")
ax.set_ylabel("True positive rate")
ax.legend(frameon=False, fontsize=6)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_confusion",
        "title": "Confusion matrix heatmap",
        "chart_type": "confusion",
        "intent": "混淆矩阵，显示分类错误分布",
        "data_schema": "y_true, y_pred labels",
        "packages": [["scikit-learn", ">=1.3"], ["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import matplotlib.pyplot as plt
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

cm = confusion_matrix(y_true, y_pred, labels=labels)
disp = ConfusionMatrixDisplay(cm, display_labels=labels)
disp.plot(cmap="Blues", values_format="d", colorbar=False)
fig = plt.gcf()
fig.set_size_inches(3.5, 3.2)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_manhattan",
        "title": "Manhattan plot for GWAS",
        "chart_type": "manhattan",
        "intent": "GWAS Manhattan 图，按染色体着色并标显著位点",
        "data_schema": "DataFrame with chrom, pos, pvalue",
        "packages": [["matplotlib", ">=3.8"], ["numpy", ">=1.26"]],
        "style_id": "nature_double",
        "code": """import numpy as np
import matplotlib.pyplot as plt

df = df.sort_values(["chrom", "pos"])
df["neglog10"] = -np.log10(df["pvalue"].clip(lower=1e-300))
colors = np.where(df["chrom"].astype(str).str.extract(r"(\\d+)")[0].astype(int) % 2 == 0,
                  "#0072B2", "#999999")
fig, ax = plt.subplots(figsize=(7, 3))
ax.scatter(np.arange(len(df)), df["neglog10"], c=colors, s=5, linewidths=0)
ax.axhline(-np.log10(5e-8), ls="--", lw=0.6, c="#D55E00")
ax.set_xlabel("Chromosome")
ax.set_ylabel("-log10 P")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
    {
        "recipe_id": "viz_waterfall",
        "title": "Waterfall plot for ranked effects",
        "chart_type": "waterfall",
        "intent": "瀑布图，按效应大小排序展示个体/基因变化",
        "data_schema": "DataFrame with sample, effect, group",
        "packages": [["matplotlib", ">=3.8"]],
        "style_id": "nature_single",
        "code": """import matplotlib.pyplot as plt

df = df.sort_values("effect", ascending=False)
colors = ["#D55E00" if v > 0 else "#0072B2" for v in df["effect"]]
fig, ax = plt.subplots(figsize=(3.5, 3.2))
ax.bar(range(len(df)), df["effect"], color=colors, width=0.85)
ax.axhline(0, lw=0.6, c="#333333")
ax.set_xlabel("Samples (ranked)")
ax.set_ylabel("Effect")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
""",
    },
])
