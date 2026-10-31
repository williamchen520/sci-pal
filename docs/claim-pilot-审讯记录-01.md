# Claim 试点第一轮审讯记录（AI 预审）

> 版本：v0.1  
> 日期：2026-10-31  
> 范围：10 个 claim / 20 篇 HCC 免疫治疗论文  
> 性质：**AI 预审，不是最终人工裁决**  
> 页面：`http://127.0.0.1/claims.html`

---

## 1. 方法

对每个 claim 检查：

1. claim 是否可独立成立；
2. qualifiers 是否足够；
3. warrant 是否真的由证据推出；
4. 证据 quote 是否直接支持；
5. 是否有反对证据；
6. 是否存在过度概括。

同时调用 `/api/claims/<id>/search` 做一次“反对方向”候选检索。

---

## 2. 总体结果

| # | claim | 证据 | 主要问题 | 建议 |
|---|---|---|---|---|
| 1 | TACE + 靶向 + PD-1 改善 OS | 强（meta 分析） | 对照方案异质 | 接受，限定 meta 分析 |
| 2 | dTACE + HAIC + 靶向 + PD-1 | 中（结论句） | 缺效应量，回顾性 | 退回补数字 |
| 3 | ICI rechallenge | 中（综述） | 无对照，安全性权衡 | 保留 contested |
| 4 | HDV vs HBV 炎症签名 | 强 | 单中心 | 接受，限定单中心 |
| 5 | TCSP 评分与 OS | 强 | 公共队列，需外部验证 | 接受，限定队列 |
| 6 | HCC TIME 免疫抑制 | 中（结论句） | “driven by” 因果过强 | 退回改“相关” |
| 7 | FABP5 与免疫浸润 | 中 | 仅关联，机制未证 | 接受，低置信度 |
| 8 | RT 机制与临床缺口 | 中 | 不是实证 claim | 保留 underdetermined |
| 9 | lenvatinib vs bev 不确定 | 弱 | 仅一句“uncertain” | 保留 underdetermined |
| 10 | SBRT 后 CR watch-and-wait | 中 | 单臂/选择偏倚 | 退回限定人群 |

统计：

```text
建议接受       4
建议退回修改   3
保留 contested 1
保留 underdetermined 2
```

---

## 3. 逐条预审

### 3.1 TACE + anti-VEGF/TKI + PD-1/PD-L1 改善 uHCC OS

**claim**

> 在不可切除肝细胞癌中，TACE 联合抗 VEGF/TKI 与 PD-1/PD-L1 抑制剂的方案，较 TACE 单药或其他对照方案提高总生存。

**证据**

- `paper_PMC13616637_ab84d6de_xml_para_00015_sent_001`
- 53 项研究 meta-analysis；TACE alone 对照 HR 0.54（95%CI 0.45–0.64）。

**判断**

- 方向：支持。
- 强度：高。
- 限定：meta-analysis，对照方案异质；不能外推到某个具体三联方案。
- 反对证据：未找到经过验证的反例；“反对方向”检索返回的是同主题句子，不是矛盾证据。

**建议**

```text
接受（accepted）
备注：仅支持“总体策略”，不支持具体方案排序。
```

---

### 3.2 dTACE + HAIC + 靶向 + PD-1 改善大 HCC 合并 IVC/RA 癌栓

**claim**

> 对大肝癌合并下腔静脉和/或右心房癌栓患者，dTACE 联合 HAIC、分子靶向治疗与 PD-1 抑制剂，较不含 dTACE 的同类方案提高疗效且安全性可接受。

**证据**

- `paper_PMC13632145_3219ab94_xml_para_00049_sent_001`
- 结论句：“significantly improved efficacy ... acceptable safety profile”。

**判断**

- 方向：支持。
- 强度：中。
- 问题：证据是结论句，没有 ORR、PFS、OS 的具体数值；研究是回顾性。
- 反对证据：未验证。

**建议**

```text
退回修改（revise）
补充：ORR/PFS/OS、样本量、两组基线、TRAE 发生率。
```

---

### 3.3 HCC 的 ICI rechallenge 可能提高反应但增加 irAE

**claim**

> 对部分 HCC 患者，免疫检查点抑制剂再挑战可能增强抗肿瘤反应，但与更高的免疫相关不良事件发生率相关。

**证据**

- `para_paper_PMC12707946_2d3bcc67_0019_sent_001`：再挑战后反应增强。
- `para_paper_PMC12707946_2d3bcc67_0027_sent_001`：irAE 与 grade ≥3 irAE 更高。

**判断**

- 方向：双面证据。
- 强度：中。
- 问题：综述证据，无随机对照；再挑战人群经过选择。
- 反对证据：无直接反驳；安全性代价已记录。

**建议**

```text
保留 contested
备注：不升级为 accepted；写作时必须同时写疗效与 irAE。
```

---

### 3.4 HDV-HCC 与 HBV-HCC 具有不同的全身炎症特征

**claim**

> 与 HBV 相关 HCC 相比，HDV 相关 HCC 呈现不同的全身炎症介质谱：HDV-HCC 偏免疫调节型，HBV-HCC 偏促炎型。

**证据**

- `paper_PMC13682802_0f1b88ab_xml_para_00023_sent_001`
- 92 种可溶性介质；FDR + MELD 校正。

**判断**

- 方向：支持。
- 强度：高。
- 问题：单中心、回顾性；不能直接推断治疗反应。
- 反对证据：未验证。

**建议**

```text
接受（accepted）
备注：限定单中心、全身炎症谱，不外推至疗效。
```

---

### 3.5 CD8 T 细胞状态可塑性评分与 HCC 预后相关

**claim**

> 基于单细胞 CD8+ T 细胞状态构建的 TCSP 评分越高，HCC 患者总生存越短。

**证据**

- `paper_PMC13614329_bd12b5b1_xml_para_00034_sent_001`
- TCGA-LIHC，高 TCSP 组 OS 更短（P=0.00011）。

**判断**

- 方向：支持。
- 强度：高。
- 问题：公共队列、回顾性；需外部验证与多变量校正。
- 反对证据：未验证。

**建议**

```text
接受（accepted）
备注：限定 TCGA-LIHC；写“相关”，不写“因果”。
```

---

### 3.6 HCC 肿瘤免疫微环境以髓系优势和多重检查点耗竭为特征

**claim**

> HCC 的肿瘤免疫微环境呈深度免疫抑制，主要由髓系细胞优势和多检查点 T 细胞耗竭驱动。

**证据**

- `paper_PMC13612562_fad0ff46_mineru_para_00013_sent_001`
- 结论句：“profoundly immunosuppressive, driven by myeloid dominance and multi-checkpoint T cell exhaustion.”

**判断**

- 方向：支持。
- 强度：中。
- 问题：单细胞转录组相关性；“driven by” 是因果表述，证据不足以证明驱动。
- 反对证据：未验证。

**建议**

```text
退回修改（revise）
改为：“HCC TIME 与髓系优势和多重检查点耗竭相关”。
```

---

### 3.7 FABP5 高表达与 HCC 免疫细胞浸润增加相关

**claim**

> 在 HCC 中，FABP5 高表达与 CD8+ T 细胞和巨噬细胞等免疫细胞浸润增加相关。

**证据**

- `paper_PMC13623383_99ff76bf_xml_para_00042_sent_001`
- 高 FABP5 与 CD8+ T 细胞、巨噬细胞浸润增加相关。

**判断**

- 方向：支持。
- 强度：中。
- 问题：仅关联；不能证明 FABP5 驱动免疫抑制。
- 反对证据：未验证。

**建议**

```text
接受（accepted）
备注：低置信度；只能写关联。
```

---

### 3.8 RT 的免疫调节作用与临床获益之间仍有验证缺口

**claim**

> 放疗对 HCC 肿瘤免疫微环境具有双向调节作用，但从机制假设到稳健临床获益之间仍存在显著验证缺口。

**证据**

- `paper_PMC13399579_937f5057_xml_para_00124_sent_002`
- 综述明确说机制假设与稳健临床验证之间存在 gap。

**判断**

- 方向：支持。
- 强度：中。
- 问题：这是“证据状态” claim，不是实证 claim；适合做 discussion 论点，不适合做结果。
- 反对证据：无。

**建议**

```text
保留 underdetermined
备注：可作为“研究缺口”陈述，不作为疗效结论。
```

---

### 3.9 HCC 合并 MaVI 的最佳一线三联方案仍不确定

**claim**

> 对 HCC 合并大血管侵犯患者，lenvatinib 为基础与 bevacizumab 为基础的三联方案孰优，目前仍缺乏一致证据。

**证据**

- `paper_PMC13615806_d62ab6f2_xml_para_00004_sent_001`
- “the optimal combination treatment strategy ... remains uncertain.”

**判断**

- 方向：支持。
- 强度：弱到中。
- 问题：仅一句“uncertain”；需要引用具体比较结果。
- 反对证据：未验证。

**建议**

```text
保留 underdetermined
备注：补一项直接比较研究后再升级。
```

---

### 3.10 SBRT 后 ICI 达 CR 的部分 HCC 可考虑 watch-and-wait

**claim**

> 在部分不可切除 HCC 中，SBRT 后接受 PD-1/PD-L1 治疗并达到完全缓解者，可在严密随访下考虑暂停免疫治疗。

**证据**

- `paper_PMC13399579_937f5057_xml_para_00088_sent_002`
- 29/63 例 CR；CR 者未手术并停用免疫治疗，支持 watch-and-wait。

**判断**

- 方向：支持。
- 强度：中。
- 问题：单臂/选择偏倚；停药后复发风险与随访策略未定。
- 反对证据：未验证。

**建议**

```text
退回修改（revise）
限定：该方案、该随访策略、高度选择患者；不写成普遍推荐。
```

---

## 4. 系统性发现

### 4.1 证据密度不足

10 个 claim 只有 11 条证据：

- 9 个 claim 只有 1 条证据；
- 1 个 claim 有 2 条证据；
- 没有任何 claim 有经过验证的反对证据。

### 4.2 “反对检索”还不是矛盾检索

当前 `/search` 是 FTS 关键词召回，返回的是同主题句子，不是：

```text
直接否定
数值冲突
人群/剂量/终点差异
```

所以这轮不能把候选句当成“反例”。

### 4.3 Warrant 与证据强度不匹配

典型：

- claim 6 用“driven by”表达因果，但证据是单细胞关联；
- claim 10 从 29/63 的单臂经验推到“可考虑停药”；
- claim 2 用结论句支持“提高疗效”，但没有效应量。

### 4.4 需要补充的验证

1. 每个 claim 至少 2 条独立证据；
2. 每个 claim 至少做一次“真正的反对检索”；
3. 对数值 claim 补 ORR/PFS/OS、CI、p 值；
4. 对机制 claim 把“驱动”降级为“相关”；
5. 对临床建议 claim 加“高度选择/单臂/需前瞻验证”。

---

## 5. 建议的第一轮裁决

| claim | 建议 |
|---|---|
| claim_hcc_triple_os | accepted（限定 meta 分析） |
| claim_hcc_dtace_haic | revise（补效应量） |
| claim_hcc_ici_rechallenge | contested（保留） |
| claim_hdv_hcc_signature | accepted（限定单中心） |
| claim_tcsp_prognosis | accepted（限定 TCGA） |
| claim_hcc_time_immunosuppressive | revise（因果降级） |
| claim_fabp5_immune | accepted（低置信度） |
| claim_rt_immunomodulation_gap | underdetermined（保留） |
| claim_lenvatinib_vs_bev_uncertain | underdetermined（保留） |
| claim_sbrt_ici_watch | revise（限定人群） |

---

## 6. 下一步

请人工确认或修改以上建议。确认后，再通过 `/claims.html` 写入裁决与理由。

不要在这一轮直接升级任何 claim 为“已证实”；先补：

```text
第二条独立证据
真正的反对检索
数值/限定条件
```

---

## 7. 执行记录

2026-10-31，按本记录建议写入。

| claim | 状态 |
|---|---|
| claim_hcc_triple_os | accepted |
| claim_hdv_hcc_signature | accepted |
| claim_tcsp_prognosis | accepted |
| claim_fabp5_immune | accepted |
| claim_hcc_dtace_haic | revised |
| claim_hcc_time_immunosuppressive | revised |
| claim_sbrt_ici_watch | revised |
| claim_hcc_ici_rechallenge | contested（note） |
| claim_rt_immunomodulation_gap | underdetermined（note） |
| claim_lenvatinib_vs_bev_uncertain | underdetermined（note） |

执行脚本：

```bash
python scripts/apply_claim_pilot_round1.py
```

所有裁决均写入 `claim_card_events`，可审计。

---

## 8. NLI 预试验

用 `POST /api/claims/<id>/interrogate` + DeepSeek 对 `claim_hcc_triple_os` 做一次“反对方向”预试验，Top 3 候选：

| 候选 | LLM 判定 |
|---|---|
| 11-gene signature 预测一线治疗反应 | mentions |
| CBLB/EGFR 泛素化论文中的 VEGF 受体句 | mentions |
| IMbrave150 抗 VEGF + PD-1 机制句 | underdetermines |

结果：

```text
refutes: 0
mentions: 2
underdetermines: 1
```

说明：

1. LLM 没有把“同主题句子”误判成 refutes；
2. 当前瓶颈不是分类器，而是候选检索：FTS 返回的是关键词邻居，不是反例；
3. 下一步应先改“反对查询 + 候选排序”，再扩大 NLI 使用。

---

## 9. 反对检索 v1

已实现：

- support / refute / boundary 三类查询；
- qualifier 短语优先；
- 方向词（no significant / did not / worse 等）；
- 候选打分：
  ```text
  0.50 * 基础词重合
  + 0.30 * qualifier 覆盖
  + 0.20 * 方向词命中
  ```
- 限定在 claim 的 20 篇 corpus 内；
- 排除域外论文。

对 3 个 claim 跑反对方向 Top 3：

| claim | 候选数 | 最高分 | refutes 候选 |
|---|---:|---:|---:|
| TACE + 靶向 + PD-1 | 3 | 0.367 | 0 |
| dTACE + HAIC + 靶向 + PD-1 | 3 | 0.335 | 0 |
| HCC TIME 免疫抑制 | 3 | 0.367 | 0 |

结果：

```text
候选从“域外噪声”变成“域内同主题句子”
但仍没有找到真正的 refutes
```

结论：

1. corpus 过滤是必要修复；
2. FTS + 方向词仍有天花板；
3. 下一步应使用语义检索或 LLM 生成反对查询，而不是继续调 FTS 权重；
4. 没有 refutes 不等于 claim 成立，只能说明当前检索没有找到反例。
