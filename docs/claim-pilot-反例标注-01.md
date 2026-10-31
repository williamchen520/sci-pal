# Claim 试点反例标注 v1（AI 辅助，待人工复核）

> 日期：2026-10-31  
> 范围：4 个 claim / 20 篇 HCC 免疫治疗论文  
> 性质：AI 辅助的候选标注，不是最终人类裁决  
> 目标：回答“这 20 篇里到底有没有真正的反例？”

---

## 1. 标注规则

- `refutes`：同一人群/干预/终点下，直接否定 claim 或方向相反的数值/结论；
- `underdetermines`：证据不足、限定条件不同、或只削弱普遍性；
- `mentions`：同主题但不支持也不否定。

本轮只发现 `underdetermines`，没有发现可以直接标为 `refutes` 的句子。

---

## 2. 标注结果

| # | claim | sentence | 标签 | 理由 |
|---|---|---|---|---|
| 1 | TACE + 靶向 + PD-1 改善 OS | `paper_PMC13399579_937f5057_xml_para_00013_sent_002` | underdetermines | 讨论 ICI 单药 ORR 有限，不是 TACE 三联 vs TACE 的直接反例 |
| 2 | dTACE + HAIC + 靶向 + PD-1 | `paper_PMC13615806_d62ab6f2_xml_para_00035_sent_001` | underdetermines | MaVI 中 lenvatinib/bevacizumab 三联相对获益不一致，不是 dTACE vs HAIC 的直接反例 |
| 3 | ICI rechallenge | `para_paper_PMC12707946_2d3bcc67_0008_sent_002` | underdetermines | 再挑战方案与患者选择尚无标准，削弱“可行”的普遍性 |
| 4 | ICI rechallenge | `para_paper_PMC12707946_2d3bcc67_0063_sent_002` | underdetermines | 无 ICI rechallenge vs TKI 头对头，证据多为回顾性/真实世界 |
| 5 | SBRT 后 CR watch-and-wait | `paper_PMC13399579_937f5057_xml_para_00091_sent_007` | underdetermines | 作者明确要求更大样本验证，支持“需限定/待验证”而非普遍推荐 |

共：

```text
claims annotated: 4
sentences: 5
refutes: 0
underdetermines: 5
```

---

## 3. 关键结论

### 3.1 没有找到直接反例

在这 20 篇语料中，没有找到：

- 同一人群、同一干预、同一终点下方向相反的结果；
- 直接否定“TACE 三联优于 TACE”的对照研究；
- 直接否定“dTACE 方案优于 HAIC 方案”的对照研究；
- 直接否定“再挑战可能有效”的研究。

### 3.2 找到的是边界证据

5 条证据都在削弱“普遍性”，而不是否定“存在获益”：

- ICI 单药 ORR 有限；
- MaVI 三联方案相对获益不一致；
- 再挑战无标准方案；
- 再挑战无头对头；
- SBRT 经验需更大样本验证。

### 3.3 因此不能升级 claim

- `accepted` claim 仍应保留限定条件；
- `contested` / `underdetermined` 不应因为“找不到反例”而升级；
- 只能记录“当前语料未发现直接反例”。

---

## 4. 对 claim 状态的影响

| claim | 原状态 | 标注后 |
|---|---|---|
| claim_hcc_triple_os | accepted | accepted（加边界证据） |
| claim_hcc_dtace_haic | revised | revised（加边界证据） |
| claim_hcc_ici_rechallenge | contested | contested（加边界证据） |
| claim_sbrt_ici_watch | revised | revised（加边界证据） |

---

## 5. 下一步

1. 人工复核这 5 条标注；
2. 若认可，再把它们作为 `underdetermines` 证据保留；
3. 若发现真正 `refutes`，单独标注并重新裁决；
4. 不要为了“有反例”而把边界证据升级成反例。

---

## 6. 执行

```bash
python scripts/apply_claim_counterexamples.py
```

数据源：

```text
packs/biomed-oncoimmuno/eval/claim_counterexamples.yaml
```

---

## 7. 人工复核

2026-10-31，人工确认：

```text
4 个 claim 的标注全部正确
5 条证据均保留 underdetermines
无 refutes
```

复核结果：

| claim | 状态 | 结论 |
|---|---|---|
| claim_hcc_triple_os | accepted | 保留边界证据 |
| claim_hcc_dtace_haic | revised | 保留边界证据 |
| claim_hcc_ici_rechallenge | contested | 保留边界证据 |
| claim_sbrt_ici_watch | revised | 保留边界证据 |

复核事件已写入 `claim_card_events`：

```bash
python scripts/confirm_claim_annotations.py
```

这轮确认的含义：

> 不是“claim 已被证明”，而是“当前 20 篇语料中确实没有直接反例，只有边界证据”。
