# PDF ä¸‰å¼•æ“Žè”åˆè§£æžï¼ˆDocling + GROBID + MinerUï¼‰

> ä»£ç ï¼š`build_db/parsers/pipeline.py`ï¼ˆç¼–æŽ’ï¼‰ã€`mineru_parser.py`ï¼ˆ4.x é€‚é…ï¼‰ã€
> `parser_orchestrator.py`ï¼ˆå…¼å®¹å£³ï¼Œå§”æ‰˜ pipelineï¼‰
> çŠ¶æ€ï¼šP1 éª¨æž¶å®Œæˆï¼›MinerU å·²æ‰“é€šï¼›GROBID å¾…éƒ¨ç½²

## åˆ†å·¥

| å¼•æ“Ž | èŒè´£ | ä¸åšä»€ä¹ˆ |
|---|---|---|
| Docling | æ­£æ–‡ã€ç« èŠ‚å±‚çº§ã€å›¾è¡¨ã€è¡¨æ ¼ï¼ˆæ•°å­—ç‰ˆ PDF ä¸»è§£æžï¼‰ | å…ƒæ•°æ®ã€ç»“æž„åŒ–å¼•ç”¨ |
| GROBID | é¡µçœ‰å…ƒæ•°æ®ï¼ˆæ ‡é¢˜/ä½œè€…/æœŸåˆŠ/DOI/å¹´/æ‘˜è¦ï¼‰ã€ç»“æž„åŒ–å‚è€ƒæ–‡çŒ® | æ­£æ–‡ã€å›¾è¡¨ |
| MinerU | OCR/å¤æ‚ç‰ˆå¼ï¼Œè´¨é‡é—¨ä¸é€šè¿‡æ—¶çš„æ­£æ–‡å…œåº• | å¼•ç”¨ã€å…ƒæ•°æ® |

XMLï¼ˆPMCï¼‰èµ°ç‹¬ç«‹ç»“æž„åŒ–å¯¼å…¥ï¼Œä¸å‚ä¸Žæ­¤æµæ°´çº¿ã€‚

## è´¨é‡é—¨ä¸Ž provenance

```
chars/page < 800 æˆ– paragraphs/page < 2 æˆ– sections < 1
    â†’ è§¦å‘ MinerUï¼ŒæŒ‰ quality_score æ‹©ä¼˜ï¼Œè®°å½• decision
```

æ¯æ¬¡è§£æžå†™ `parse_provenance`ï¼š

```
text_engine / meta_engine / refs_engine / tables_engine / decision / metrics
```

`papers.parse_engine` è®°å½•ç»„åˆï¼ˆå¦‚ `docling+grobid`ï¼‰ã€‚

## A/B å®žæµ‹ï¼ˆ2026-10-27ï¼Œæ•°å­—ç‰ˆ PDFï¼‰

| PDF | å¼•æ“Ž | é¡µ | æ®µ | å­—ç¬¦ | å­—ç¬¦/é¡µ | æ®µ/é¡µ | å›¾ | è€—æ—¶ |
|---|---|---|---|---|---|---|---|---|
| PMC13612245 | Docling | 2 | 29 | 12,830 | 6,415 | 14.5 | 2 | 16.7s |
| PMC13612245 | MinerU | 2 | 47 | 13,457 | 6,728 | 23.5 | 1 | 3.5s |
| PMC13613046 | Docling | 13 | 124 | 59,067 | 4,544 | 9.54 | 17 | 7.6s |
| PMC13613046 | MinerU | 13 | 223 | 74,126 | 5,702 | 17.15 | 3 | 64s |

è§‚å¯Ÿï¼š

- æ•°å­—ç‰ˆ PDF ä¸¤è€…éƒ½è¿‡é—¨ï¼ˆ800 å­—ç¬¦/é¡µï¼‰ï¼ŒMinerU æ–‡æœ¬å¬å›žæ›´é«˜ä½†**å›¾æ›´å°‘ã€é•¿æ–‡æ…¢**ï¼ˆ64s vs 7.6sï¼‰ï¼›
- ä¸¤è€…å¼•ç”¨å‡ä¸º 0 â†’ å¼•ç”¨å¿…é¡»é  GROBIDï¼›
- æš‚å®šé˜ˆå€¼ï¼š`char/page 800`ã€`paragraphs/page 2`ã€`sections 1`ï¼›ç­‰æ‰«æä»¶æ ·æœ¬å†æ ¡å‡†ã€‚

## MinerU 4.x æŽ¥å…¥ï¼ˆå·²æ‰“é€šï¼‰

```powershell
# 1) ä¸‹è½½ basic æ¨¡åž‹ï¼ˆä¸€æ¬¡æ€§ï¼Œçº¦ 1 GBï¼‰
mineru-models-download --tier basic --source modelscope

# 2) å¸¸é©»è§£æžæœåŠ¡
mineru-api --tier basic --port 8000

# 3) CLI æŒ‡å‘æœ¬åœ°æœåŠ¡
mineru config set parse_server.local.mode self_hosted
mineru config set parse_server.local.self_hosted_url http://127.0.0.1:8000
```

é€‚é…å™¨ï¼š`MinerUParser` è°ƒ `mineru parse <pdf> --pages all --json`ï¼Œ
æŠŠè¿”å›žçš„ Markdownï¼ˆå« `<!-- page n of m -->` ä¸Ž `#` æ ‡é¢˜ï¼‰è½¬æˆæ®µè½/å›¾ï¼›
æœåŠ¡ä¸å¯ç”¨æ—¶è¿”å›ž stubï¼Œè´¨é‡é—¨ä¿è¯ stub ä¸ä¼šé¡¶æŽ‰ Doclingã€‚

## GROBIDï¼ˆå·²ç”¨ Docker CRF é•œåƒæ‰“é€šï¼‰

```powershell
docker run -d --rm --name grobid -p 8070:8070 lfoppiano/grobid:latest-crf
# isalive â†’ true åŽï¼Œpipeline è‡ªåŠ¨æŽ¥ç®¡å…ƒæ•°æ®/å¼•ç”¨
```

é•œåƒä½“ç§¯ï¼ˆé‡è¦ï¼‰ï¼š

| é•œåƒ | ä¸‹è½½/ç£ç›˜ | è¯´æ˜Ž |
|---|---|---|
| `lfoppiano/grobid:latest-crf` | ~0.5 GB ä¸‹è½½ / 1.7 GB ç£ç›˜ | æ—¥å¸¸æ‰¹é‡è§£æžï¼ˆå¿«ã€çœå†…å­˜ï¼‰ |
| `grobid/grobid:0.9.1-full` | 13.8 GB ä¸‹è½½ / **37.4 GB ç£ç›˜** | éš¾ä¾‹è§£æžï¼ˆDeep Learningï¼Œæ…¢çº¦ 1.8xï¼‰ |

å®žæµ‹ï¼ˆPMC13613046ï¼Œ13 é¡µï¼‰ï¼šDocling å¼•ç”¨ 0 â†’ GROBID **60 æ¡å¼•ç”¨ + 89 ä¸ªæ­£æ–‡å¼•ç”¨é“¾æŽ¥**ï¼Œ
å¹¶è¡¥é½æ ‡é¢˜/ä½œè€…/DOIï¼›`provenance = text:docling, meta:grobid, refs:grobid`ã€‚
åŒä¸€ç¯‡ CRF 72sã€Full 132sï¼Œè¾“å‡ºä¸€è‡´ã€‚

### æŒ‰ä»»åŠ¡åˆ‡æ¢ CRF / Full

ä¸¤ä¸ªå®¹å™¨å¯ä»¥åŒæ—¶è·‘ï¼Œpipeline æŒ‰ `grobid_mode` é€‰ç«¯ç‚¹ï¼š

```powershell
# CRF å¸¸é©» 8070ï¼ˆé»˜è®¤ï¼‰
docker run -d --rm --name grobid-crf -p 8070:8070 lfoppiano/grobid:latest-crf
# Full å¸¸é©» 8071ï¼ˆå¯é€‰ï¼‰
docker run -d --rm --name grobid-full -p 8071:8070 grobid/grobid:0.9.1-full
```

```powershell
SCIPAL_GROBID_URL=http://127.0.0.1:8070         # auto / crf
SCIPAL_GROBID_URL_FULL=http://127.0.0.1:8071    # fullï¼ˆæœªè®¾åˆ™å›žé€€ CRFï¼‰
```

`POST /api/papers/parse` ä¸Ž `/api/papers/parse_async` æ”¯æŒè¯·æ±‚ä½“ï¼š

```json
{"filename": "paper.pdf", "grobid": "full"}   // auto | crf | full
```

> è§£æžå…¥å£å·²ç»Ÿä¸€åˆ° `build_db/parse_service.py`ï¼ˆ`parse_and_store` / å•æŠŠè§£æžé” /
> `PARSE_MAX_CONCURRENT`ï¼‰ï¼Œè·¯ç”±å±‚ä¸å†æŒæœ‰è§£æžå®žçŽ°ã€‚

> Docker Desktop æ•°æ®ç›˜åœ¨ `D:\DockerDesktopWSL\disk\docker_data.vhdx`ï¼›
> vhdx ä¸ä¼šè‡ªåŠ¨æ”¶ç¼©ï¼Œåˆ é•œåƒåŽéœ€ `wsl --shutdown` + `diskpart compact vdisk`ï¼ˆæˆ– Docker Desktop çš„ Clean/Purgeï¼‰ã€‚

