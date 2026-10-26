# scipal-guard 质量评估

> 脚本：`scripts/eval_guard.py`（可复现，三个场景）
> 运行：`venv_sciPal_py312\Scripts\python.exe scripts\eval_guard.py`
> 词表：PubTator3 1,829 + HGNC 45,277，共 47,106 条

## 结果

| 场景 | checked | unknown | 比例 | 结论 |
|---|---|---|---|---|
| A 真实综述片段 | 8 | 0 | 0% | 无误报 |
| B 掺入 3 个编造基因 | 6 | 3 | 50% | FOOBARZ9 / XYZQ1 / ZZZZ8 全部抓到 |
| C 方法/技术密集 | 3 | 0 | 0% | CRISPR 落入 `corpus`，不判 |

场景 B 的 3 个 unknown 全部是人为编造，没有把真基因误判；场景 C 里 CRISPR、Western blot、qPCR、flow cytometry 没有被判 unknown。

## 关键结论

1. **实体校验可靠**：真基因落到 HGNC/MeSH 标准 ID（TLR4 → HGNC:11850、NLRP3 → HGNC:16400、EGFR → HGNC:3236、STAT3 → HGNC:11364）。
2. **方法类不误报**：CRISPR 这类词若在正文出现过，落 `corpus` 而不是 `unknown`，符合“方法不判”的设计。
3. **block 阈值**：正常综述 unknown 通常是 0；编造比例 50% 的文本会被 `SCIPAL_GUARD_MAX_UNKNOWN=0.05` 拦下。**默认已是 `block`**（2026-10-26 起），需要放宽时显式设 `SCIPAL_GUARD_MODE=warn`。

## 已知边界

- 词表只覆盖 476 篇论文的**标题+摘要**，正文术语靠 `paragraphs_fts` 兜底；
- 只判实体，不判方法/技术/主题短语；
- PubTator 偶尔给出较泛的 MeSH 条目（如 `chronic`、`tissue injury`），会显示为 curated，属于“真实但泛”的匹配，不算错误；
- 缩写未定义检查只对全大写 token 生效，且被词表/FTS 命中会放行。

## 建议

- 默认 `SCIPAL_GUARD_MODE=block`（阈值 5%）：unknown 超限的综述不会进入 store/export；
- 只想告警时设 `SCIPAL_GUARD_MODE=warn`，完全关闭设 `off`；
- 若出现误报，把词加入 `services/quality/lexicon.py` 的 `BROAD_TERMS` 或 `COMMON_WORDS`，而不是放宽阈值。
