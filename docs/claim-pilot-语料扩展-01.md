# Claim 试点语料扩展 v1

> 日期：2026-10-31  
> 从 20 篇扩展到 30 篇 HCC 语料  
> 目标：寻找 TACE 三联、dTACE、ICI rechallenge、SBRT 的直接反例

---

## 1. 扩展结果

```text
原 corpus: 20
新增:      10
现 corpus: 30
```

新增论文全部来自本地 `papers` 表，均已有句子级数据。

| paper_id | 主题 |
|---|---|
| paper_PMC12807518_6dfefde2 | 系统治疗后病理完全缓解 / 可行切除 |
| paper_PMC13621873_801b0f7d_xml | 个体化治疗决策与预后 |
| paper_PMC13630903_07ba59c9_xml | 真实世界治疗格局与结局 |
| paper_PMC13626788_82c7332e_xml | 不可切除/晚期 HCC 系统治疗范式 |
| paper_PMC13615818_420937c7_xml | 肠道菌群与 HCC |
| paper_PMC13632115_f52f450b_xml | TACE + TKI ± PD-1 复发 HCC |
| paper_PMC13623354_0f50f62a_xml | 晚期 HCC 多模式治疗病例 |
| paper_watch_pmc13661018 | 转化切除病例 |
| paper_PMC13629315_20962d7f_xml | IL-32 / NET / PVTT / 放疗抵抗 |
| paper_PMC13632189_982d7b11_xml | VETC 与早期复发 |

---

## 2. 扩展后检索

对 3 个 claim 跑反对方向 Top 3：

### TACE + 靶向 + PD-1

```text
Top 1/2: meta-analysis 总览/结果（semantic）
Top 3:   SBRT/ICI（fts）
refutes: 0
```

### dTACE + HAIC + 靶向 + PD-1

```text
Top 1: 影像响应示例
Top 2: “first investigation” 声明
Top 3: 影像图注
refutes: 0
```

### HCC TIME 免疫抑制

```text
Top 1: 单细胞队列方法
Top 2: SPP1+ TAM / exhausted T / Treg
Top 3: PVTT scRNA-seq
refutes: 0
```

---

## 3. 结论

### 3.1 扩展没有带来直接反例

新增 10 篇后：

```text
refutes 仍为 0
```

返回结果更多是：

- 方法；
- 队列描述；
- 支持性结果；
- 影像/图注。

### 3.2 本地语料的结构性缺口

本地库以“阳性结果/机制/方法”论文为主，缺少：

- 阴性随机对照；
- TACE 三联失败研究；
- dTACE 与 HAIC 头对头；
- ICI rechallenge 失败队列；
- SBRT + ICI 阴性验证。

### 3.3 不能把“扩展语料”当成“找到反例”

当前只能写：

> 在 30 篇本地语料中，未发现直接反例。

不能写：

> 该 claim 已被证明。

---

## 4. 在线候选

已识别但尚未完成入库：

| PMC | 主题 |
|---|---|
| PMC13036683 | LEAP-012 评论 |
| PMC12771288 | LEAP-012 / EMERALD-1 对 HCC 管理的影响 |
| PMC8940827 | LEAP-012 研究设计 |
| PMID 39798578 | LEAP-012 主研究（无 PMC 全文） |
| PMID 37871608 | IMbrave050 主研究（无 PMC 全文） |

在线 ingest 任务当前为 `queued`，没有完成；不能计入 corpus。

---

## 5. 下一步

1. 完成 LEAP-012 / IMbrave050 相关全文入库；
2. 找 3–5 篇明确的阴性/失败研究；
3. 再做一次反对检索；
4. 如果仍无 refutes，明确写“当前证据未发现直接反例”。

不要把“语料变大”误写成“论证变强”。
