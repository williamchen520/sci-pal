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

## GROBID（已用 Docker CRF 镜像打通）

```powershell
docker run -d --rm --name grobid -p 8070:8070 lfoppiano/grobid:latest-crf
# isalive → true 后，pipeline 自动接管元数据/引用
```

镜像体积（重要）：

| 镜像 | 下载/磁盘 | 说明 |
|---|---|---|
| `lfoppiano/grobid:latest-crf` | ~0.5 GB 下载 / 1.7 GB 磁盘 | 日常批量解析（快、省内存） |
| `grobid/grobid:0.9.1-full` | 13.8 GB 下载 / **37.4 GB 磁盘** | 难例解析（Deep Learning，慢约 1.8x） |

实测（PMC13613046，13 页）：Docling 引用 0 → GROBID **60 条引用 + 89 个正文引用链接**，
并补齐标题/作者/DOI；`provenance = text:docling, meta:grobid, refs:grobid`。
同一篇 CRF 72s、Full 132s，输出一致。

### 按任务切换 CRF / Full

两个容器可以同时跑，pipeline 按 `grobid_mode` 选端点：

```powershell
# CRF 常驻 8070（默认）
docker run -d --rm --name grobid-crf -p 8070:8070 lfoppiano/grobid:latest-crf
# Full 常驻 8071（可选）
docker run -d --rm --name grobid-full -p 8071:8070 grobid/grobid:0.9.1-full
```

```powershell
SCIPAL_GROBID_URL=http://127.0.0.1:8070         # auto / crf
SCIPAL_GROBID_URL_FULL=http://127.0.0.1:8071    # full（未设则回退 CRF）
```

`POST /api/papers/parse` 与 `/api/papers/parse_async` 支持请求体：

```json
{"filename": "paper.pdf", "grobid": "full"}   // auto | crf | full
```

> 解析入口已统一到 `build_db/parse_service.py`（`parse_and_store` / 单把解析锁 /
> `PARSE_MAX_CONCURRENT`），路由层不再持有解析实现。

> Docker Desktop 数据盘在 `D:\DockerDesktopWSL\disk\docker_data.vhdx`；
> vhdx 不会自动收缩，删镜像后需 `wsl --shutdown` + `diskpart compact vdisk`（或 Docker Desktop 的 Clean/Purge）。

## 服务启动与开机自启

四个服务（GROBID CRF 8070、GROBID Full 8071、MinerU API 8000、MinerU server）用脚本统一拉起：

```powershell
# 检查 + 只补缺失的服务
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_parser_services.ps1

# 只看状态，不起服务
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_parser_services.ps1 -CheckOnly

# 不起 37 GB 的 Full（省内存）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_parser_services.ps1 -SkipFull
```

- 脚本幂等：健康检查通过就不动，失败才启动；
- GROBID 容器带 `--restart unless-stopped`，Docker Desktop 启动后自动恢复；
- MinerU 需要 **两个进程**：`mineru-api`（8000）+ `mineru server`（文档中心），缺一个 CLI 会回退 stub。

### MinerU 模型固定位置

模型实际落盘在 `MINERU_HOME`（默认 `~/.mineru`）。已固定到：

```powershell
setx MINERU_HOME D:\mineru_home        # 876 MB：Layout / MFR / OCR / Table
```

`scripts/start_parser_services.ps1` 会显式设置该变量；Flask 也需带 `MINERU_HOME` 启动，
否则子进程会回落到 `~/.mineru`。同理，`mineru-models-download` 只在升级模型时执行一次。

### 开机自启

管理员权限不足时无法创建计划任务，改用当前用户的启动项（无需管理员）：

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SciPalParserServices.vbs
```

VBS 以隐藏窗口调用上面的脚本；若后续拿到管理员权限，可改注册计划任务：

```powershell
schtasks /create /tn SciPalParserServices /sc onlogon /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"D:\sciPal\scripts\start_parser_services.ps1\""
```

## 结构 v2：章节树 / 句子树 / 句级 bbox / 文章图谱

Schema 迁移（幂等）：

```powershell
python -m build_db.structure_v2
```

新增/补充：

| 表 | 关键字段 |
|---|---|
| `sections` | section_id, parent_id, level, title, seq, page, bbox |
| `paragraphs` | + section_id, section_path(JSON) |
| `sentences` | + page, bbox, section_id, char_start, char_end |
| `citations` | + page, bbox |
| `tables` | + page, bbox |
| `citation_mentions` | 正文引用出现位置（ref_number/page/bbox/context） |
| `sentence_links` | + page, bbox, source, confidence |
| `paper_links` | 统一文章间关系（cites/similar/mentions，含 target_doi/置信度） |

构建步骤（按论文粒度，可增量跑）：

```powershell
python -m build_db.sentence_geometry --paper-id <id>   # 句子切分 + bbox
python -m build_db.build_sections_tree --paper-id <id> # 章节树 + 段落绑定
python -m build_db.rebuild_sentence_links --paper-id <id>  # 句子↔引用/图表
python -m build_db.sync_paper_links                    # 汇总文章图谱
```

几何来源：

- 段落 bbox：Docling `chunk.meta.doc_items[*].prov` 并集；
- 句子 bbox：PyMuPDF `search_for(sentence)`（限制在段落 rect 内），失败回退段落 bbox；
- 引用 bbox：GROBID `coords="page,x,y,w,h"`（bottom-left，落库前转 top-left）；
- MinerU 只给文本，无 bbox；扫描件句子暂回退段落 bbox。

样例实测（PMC13612245，2 页）：

```
段落 29/29 有 bbox，28/29 有 section_path
句子 127/127 有 bbox（55 条回退段落 bbox）
章节 8 个，29 段落全部绑定
引用 mention 8/8 带 page
句子↔引用 7 条（GROBID 位置优先）
```

全量回填结果（2026-10-27）：

```
章节：43,033 个，覆盖 2,076 篇；段落绑定 145,315 / 147,910（98.2%）
句子：248,179 条；PDF 的 82 篇重建后 61,739 句，其中 58,648 条带 bbox（95%）
句子链接：引用 3,649 / 图 118 / 表 257
文章图谱：47,382 条（cites 36,950、similar 6,798）；cites 多为外部 DOI
```

MinerU 旧数据的段落没有 page/bbox；`sentence_geometry` 对这类句子按全文逐页
`search_for` 定位，13,551 句补出 10,460 条 bbox，剩余是无文本层/扫描件。

性能注意：`paragraphs_au` 触发器会在每次 UPDATE 时重建 FTS，且 DELETE 无
`para_id` 索引（全表扫描）。`build_sections_tree` 在批量更新期间临时 DROP
该触发器、同一事务内恢复；未处理时单篇 549 段要 3 分钟以上，处理后 0.2 秒。

已知限制：

- XML 论文没有坐标，句子 bbox 为空；
- MinerU 兜底路径没有 bbox；
- 文章图谱的 cites 大多是外部文献（target_doi），本地互引很少；
- GROBID 句级位置只对“新解析”的 PDF 生效（`citation_mentions`），旧数据未回填。

