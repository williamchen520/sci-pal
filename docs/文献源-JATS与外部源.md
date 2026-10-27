# 文献源与 JATS 结构化导入

## 两条处理链，不要混用

| 输入 | 链路 | 是否有 bbox |
|---|---|---|
| PDF | Docling + GROBID + MinerU 三引擎流水线 | ✅ PDF 坐标 |
| **JATS XML**（PMC / Europe PMC / PMC OA 包） | `build_db/import_jats.py` 直接按结构入库 | ❌ 无坐标（XML 本身没有页面坐标） |
| arXiv / bioRxiv / medRxiv | 只有 PDF + 元数据 → 走 PDF 流水线 | ✅ |

XML 的结构是**权威的**：`<sec>` 嵌套、`<ref-list>`、`<fig>`、`<table-wrap>`、
`<xref rid="...">`。不需要从文本猜标题，也不需要正则匹配引用标记。

## JATS 导入器

```powershell
python -m build_db.import_jats --file documents_xml/PMC12490799.xml
python -m build_db.import_jats --dir documents_xml --limit 200
python -m build_db.import_jats --dir documents_xml --resume   # 跳过已导入
```

映射关系：

| JATS | 入库 |
|---|---|
| `<sec>` 嵌套 | `sections(parent_id, level, title, seq)`，source=`jats` |
| `<p>` + 祖先标题 | `paragraphs(section_level1/2/3, section_path, section_id)` |
| `<ref-list>/<ref>` | `citations`（ref_id → ref_number，DOI 自动提取） |
| `<fig>` / `<table-wrap>` | `figures` / `tables`（label + caption） |
| `<xref ref-type="bibr|fig|table">` | `sentence_links(source='jats', confidence=1.0)` |

句子在导入时同步切分（无 bbox），xref 按字符偏移落到具体句子。

### 性能坑

`paragraphs_ad` 触发器按 `para_id` 删除 FTS 行，而 FTS 没有该列索引：
删除 12 段要 **6 秒**。导入器在删除旧数据时临时 DROP 该触发器、先批量删段落、
再一次性清 FTS，最后恢复触发器——单篇降到 **0.7 秒**。

## 可下载的文献源

| 源 | 格式 | 全文 | 结构化 | 接入 |
|---|---|---|---|---|
| PMC OA | JATS XML / PDF | ✅ | ✅ | 已有（XML 导入 + PDF 下载） |
| PMC OA 批量包 | tar.gz（XML） | ✅ | ✅ | 可用 `import_jats --dir` 直接导入 |
| Europe PMC | JATS XML / JSON | ✅ OA + 预印本 | ✅ | `services/search/europe_pmc.py` |
| PubMed | JSON/XML 摘要 | ❌ | 部分 | 已有检索 |
| arXiv | Atom XML + PDF | ✅ | ❌ | `services/search/preprint_sources.py` |
| bioRxiv / medRxiv | JSON + PDF | ✅ | ❌ | `services/search/preprint_sources.py` |
| Crossref | JSON | ❌ | 引用列表 | `services/search/metadata_sources.py` |
| OpenAlex | JSON | ❌ | 引用图 | 同上（另有本地快照脚本） |
| Semantic Scholar | JSON | 部分 | 引用/TLDR | 同上 |
| Unpaywall | JSON | OA 链接 | ❌ | 同上（需 email） |
| CORE | JSON | ✅ | ❌ | 同上（需 API key） |
| DOAJ | JSON | ❌ | 元数据 | 同上 |
| Zotero | SQLite/JSON | 元数据 | ❌ | 已有 `import_zotero_metadata.py` |
| protocols.io | JSON | 方法 | ✅ | 已接 |
| ResearchGate / Sci-Hub | — | — | — | 无合法 API，不接 |

## 使用示例

```python
from services.search.europe_pmc import EuropePMCClient

client = EuropePMCClient()
hits = client.search("hepatocellular carcinoma AND OPEN_ACCESS:Y", page_size=10)
client.download_and_import(hits[0]["pmcid"])   # 存 XML 并导入结构化库
```

```python
from services.search.preprint_sources import search_arxiv, fetch_biorxiv, download_pdf

items = search_arxiv("protein language model")
download_pdf(items[0]["pdf_url"], "documents/arxiv_2501.00001.pdf")
# 然后走 PDF 流水线（parse_service / docling）
```

```python
from services.search.metadata_sources import crossref_work, unpaywall

meta = crossref_work("10.1234/test.1")
oa = unpaywall("10.1234/test.1", "you@example.org")
```

## 全量导入结果（2026-10-27）

```
1,633 个 JATS 文件
  36,076 个章节（source=jats，显式父子）
  78,289 个段落
 444,740 条句子
 197,660 条 xref 句级链接（source=jats, confidence=1.0）

库内合计：
  citations 119,389（XML 参考文献已入库）
  figures 9,859 / tables 3,109
  sentences 691,839
  sentence_links：jats 193,324 + regex 4,377
  paper_links 155,353
```

## 批量、预印本与元数据回填

```powershell
# Europe PMC 批量：检索 → OA 全文 XML → 结构化导入
python -m services.search.europe_pmc_batch --query "hepatocellular carcinoma AND OPEN_ACCESS:Y" --max-items 20 --limit 10

# 预印本：下载 PDF + 走三引擎流水线（--no-parse 只下载）
python -m services.search.preprint_ingest --arxiv "protein language model" --max-items 1
python -m services.search.preprint_ingest --biorxiv 10.1101/2025.01.01.000001 --no-parse

# 元数据回填（Crossref 优先，OpenAlex 兜底）
python -m build_db.backfill_metadata --limit 50 --dry-run
python -m build_db.backfill_metadata --limit 50

# XML 图表回退链接（历史数据，新增 jats-regex 0.6）
python -m build_db.backfill_jats_figure_links
```

实测（2026-10-27）：

```
Europe PMC 批量 3 篇 → 99 章节 / 188 段 / 791 句 / 356 条 xref 链接
arXiv 下载+解析 1 篇 → 94 段 / 19 图，元数据补标题与年份
Crossref/OpenAlex 回填两轮共 85 篇；全库 2,118 篇中仅 1 篇缺期刊/年份、0 篇缺 DOI
XML 图表回退 → 652 篇，+3,620 条 jats-regex 链接
```

## 实网验证（2026-10-27）

```
Europe PMC search("hepatocellular carcinoma AND OPEN_ACCESS:Y") -> 5 条
Europe PMC fullTextXML(PMC11649735) -> 225 KB
arXiv search("protein language model") -> 3 条

下载并导入 PMC11649735：
  23 章节 / 23 段 / 273 句 / 183 引用 / 4 图 / 219 条 xref 链接
```

## 测试

```
tests/test_jats_import.py        JATS 解析 + 导入（章节父子、xref 链接、图表/引用）
tests/test_literature_sources.py Europe PMC / arXiv / bioRxiv / Crossref / Unpaywall（mock HTTP）
```
