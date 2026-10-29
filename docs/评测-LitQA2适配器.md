# 外部评测：LitQA2 适配器

> 状态：20 题 smoke 完成，样本过小，暂不作为主评测。

## 1. 数据

来源：LAB-Bench

```
G:\runs\LAB-Bench\LitQA2\litqa-v2-public.jsonl
199 题
```

字段：

- `question`
- `ideal`
- `distractors`
- `sources`（DOI）
- `key-passage`

## 2. 接入流程

1. DOI → Europe PMC 搜索；
2. 取 PMCID；
3. 下载 `fullTextXML`；
4. `build_db.jats_parser.parse_jats` 解析；
5. 建独立 `data/benchmark_litqa2.db`；
6. 摘要/章节/段落/句子入库；
7. 用 `key-passage` 定位 gold 段落/句子；
8. 建 Chroma；
9. `HybridSearch` 向量 + FTS + RRF 检索。

## 3. 20 题结果

| 阶段 | 数量 |
|---|---|
| 题目 | 20 |
| 成功下载并解析 | 13 |
| key-passage 定位成功 | 12 |
| 可评测 | 12 |

检索：

| 指标 | 值 |
|---|---|
| doc_recall@10 | 1.00 |
| sentence_recall@10 | 1.00 |

## 4. 解释

- 1.00 只代表 **12 个已映射题**；
- 样本太小，不能作为主评测结论；
- 7 题无法获取全文（无 PMCID/非开放获取）；
- 1 题全文可获取但 `key-passage` 仍无法定位。

## 5. 阻碍

1. 全文获取受开放获取限制；
2. `key-passage` 与 XML 文本存在格式差异（空格、连字符、引用标记）；
3. 20 题映射率 60%（12/20），仍偏低。

## 6. 建议

1. 做 key-passage 归一化匹配：
   - 去引用标记；
   - 统一连字符/空格；
   - 子串失败时用 token overlap 选最佳段落；
2. 只对能获取 XML 的题目做评测；
3. 扩到 199 题前先提高映射率；
4. 映射失败的题单独列出，不混入指标。

## 7. 产物

- `eval/litqa2_benchmark.py`
- `data/benchmark_litqa2.db`（不提交）
- `eval/results/litqa2_smoke_20.json`

## 8. 复现

```powershell
python -m eval.litqa2_benchmark --build --limit 20
```
