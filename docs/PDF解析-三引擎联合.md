# PDF 三引擎联合解析（Docling + GROBID + MinerU）

> 代码：`build_db/parsers/pipeline.py`（编排）、`mineru_parser.py`（4.x 适配）、
> `parser_orchestrator.py`（兼容壳，委托 pipeline）
> 状态：P1 骨架完成；MinerU 已打通；GROBID 待部署

## 分工

| 引擎 | 职责 | 不做什么 |
|---|---|---|
| Docling | 正文、章节层级、图表、表格（数字版 PDF 主解析） | 元数据、结构化引用 |
| GROBID | 页眉元数据（标题/作者/期刊/DOI/年/摘要）、结构化参考文献 | 正文、图表 |
| MinerU | OCR/复杂版式，质量门不通过时的正文兜底 | 引用、元数据 |

XML（PMC）走独立结构化导入，不参与此流水线。

## 质量门与 provenance

```
chars/page < 800 或 paragraphs/page < 2 或 sections < 1
    → 触发 MinerU，按 quality_score 择优，记录 decision
```

每次解析写 `parse_provenance`：

```
text_engine / meta_engine / refs_engine / tables_engine / decision / metrics
```

`papers.parse_engine` 记录组合（如 `docling+grobid`）。

## A/B 实测（2026-10-27，数字版 PDF）

| PDF | 引擎 | 页 | 段 | 字符 | 字符/页 | 段/页 | 图 | 耗时 |
|---|---|---|---|---|---|---|---|---|
| PMC13612245 | Docling | 2 | 29 | 12,830 | 6,415 | 14.5 | 2 | 16.7s |
| PMC13612245 | MinerU | 2 | 47 | 13,457 | 6,728 | 23.5 | 1 | 3.5s |
| PMC13613046 | Docling | 13 | 124 | 59,067 | 4,544 | 9.54 | 17 | 7.6s |
| PMC13613046 | MinerU | 13 | 223 | 74,126 | 5,702 | 17.15 | 3 | 64s |

观察：

- 数字版 PDF 两者都过门（800 字符/页），MinerU 文本召回更高但**图更少、长文慢**（64s vs 7.6s）；
- 两者引用均为 0 → 引用必须靠 GROBID；
- 暂定阈值：`char/page 800`、`paragraphs/page 2`、`sections 1`；等扫描件样本再校准。

## MinerU 4.x 接入（已打通）

```powershell
# 1) 下载 basic 模型（一次性，约 1 GB）
mineru-models-download --tier basic --source modelscope

# 2) 常驻解析服务
mineru-api --tier basic --port 8000

# 3) CLI 指向本地服务
mineru config set parse_server.local.mode self_hosted
mineru config set parse_server.local.self_hosted_url http://127.0.0.1:8000
```

适配器：`MinerUParser` 调 `mineru parse <pdf> --pages all --json`，
把返回的 Markdown（含 `<!-- page n of m -->` 与 `#` 标题）转成段落/图；
服务不可用时返回 stub，质量门保证 stub 不会顶掉 Docling。

## GROBID（待部署）

无 Docker；方案：Java 17 + GROBID 0.9.1 发行包，常驻 8070。
部署后由 pipeline 自动探测并接管元数据/引用，provenance 记为 `meta_engine=grobid`。
