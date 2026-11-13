# 案例：HCC 多组学分子分型论文（HTML + Zenodo）

> 日期：2026-11-13  
> 状态：HTML/代码获取成功；代码未入 RAG  
> 目的：验证“OA HTML 优先于 PDF”的获取路线

---

## 1. 论文

标题：

> Integrated genomic analyses identify oncogenic pathway interplay in hepatocarcinogenesis defining specific molecular subtypes

- DOI: `10.1038/s41467-026-73212-y`
- 期刊：Nature Communications
- 类型：OA HTML
- HTML 大小：约 720 KB
- HTML 可提取：title / abstract / sections / code availability

### 一句话

整合 529 例 HCC 的基因组、转录组、表观组、蛋白组，提出 9 个稳健分子亚型，并在 807 例外部队列验证。

---

## 2. 主要结论

```text
529 HCC 主队列
807 外部验证
9 个分子亚型
```

常见亚型：

```text
CTNNB1 ex3 / APC   25%
TP53               21%
AXIN1 / IRF2       11%
```

少见亚型：

```text
TP53 + CTNNB1 ex3  6%
BAP1               6%
CCNA2 / E1         6%
HNF1A              1%
```

免疫相关：

```text
U-Hot              17%
U-Interm           8%
```

机制：

```text
AXIN1 / TP53 改变 β-catenin / p53 活性
BAP1 缺失功能性失活 TP53
TP53 + CTNNB1 ex3 高侵袭、预后差
```

---

## 3. HTML 获取验证

```text
https://link-hkg.springer.com/article/10.1038/s41467-026-73212-y
-> 200
-> 720,196 bytes
```

可直接解析：

```text
citation_title
citation_doi
abstract
section headings
Code availability
```

Code availability：

```text
https://doi.org/10.5281/zenodo.17236540
```

比 PDF 断行拼 URL 稳定。

---

## 4. 代码

Zenodo：

```text
DOI 10.5281/zenodo.17236540
license GPL-3.0-or-later
6 个 R 文件
```

文件：

```text
Figure1.R   12,926
Figure2.R   54,237
figure3.R   41,496
figure4.R   27,181
figure5.R   16,698
figure6.R   56,184
```

许可证：

```text
GPL-3.0-or-later
```

因此：

```text
可阅读/学习方法
默认不复制进我们的项目
需要 clean-room 重写
```

---

## 5. 模块

| 文件 | 功能 |
|---|---|
| `Figure1.R` | 9 个分子亚型的 tSNE 分布、临床注释 |
| `Figure2.R` | TP53 score heatmap/boxplot |
| `figure3.R` | CTNNB1 score heatmap/boxplot |
| `figure4.R` | OS/DSS 生存分析（LICA-FR 等） |
| `figure5.R` | CIN score、免疫浸润 |
| `figure6.R` | 性别/年龄/肿瘤大小/AFP 等临床特征 |

---

## 6. 数据流

```text
multi-omics matrix
  + clinical annotation
  + molecular group labels
        │
        ▼
Figure1  tSNE / group distribution / clinical annotation
        │
        ├── Figure2  TP53 score
        ├── figure3 CTNNB1 score
        ├── figure4 survival
        ├── figure5 CIN / immune
        └── figure6 clinical features
```

这是一套 **以注释表和 score 为核心的图件脚本**，不是完整分析 pipeline：

```text
输入多为 readxl 读取的表格
大量硬编码路径
没有函数封装
没有 tests
没有数据
```

---

## 7. 当前 RAG 状态

```text
HTML 已获取
代码已下载
R parser 未实现
code RAG 未入库
```

不能声称：

```text
代码已解析入库
```

---

## 8. 设计结论

```text
OA HTML 优先
Zenodo API 直接取文件和 license
PDF 仅作页面/图表/补充材料
```

第二篇正好证明：

```text
HTML 比 PDF 更适合抽 Code availability
Zenodo 比 GitHub zip 更适合拿 license/checksum
```
