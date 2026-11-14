# 方案表：HTML-first 批量入库

> 日期：2026-11-14  
> 状态：执行中  
> 当前阶段：H2  
> 决策：OA 文献优先 JATS/HTML，PDF 兜底

---

## 1. 目标

```text
DOI / PMCID / URL
  -> 解析 OA 来源
  -> 优先 JATS/PMC
  -> 其次出版社 HTML
  -> 质量门禁
  -> 失败 fallback PDF
```

HTML 是主力，因为：

```text
结构好
速度快
无 Docling 成本
```

---

## 2. 来源优先级

```text
1. PMC JATS XML
2. PMC HTML
3. 出版社 OA HTML
4. 出版社 PDF
```

HTML 质量通过时，不跑 PDF。

---

## 3. 阶段

| 阶段 | 目标 | 状态 | 计划表 | 验收 |
|---|---|---|---|---|
| H0 | HTML batch CLI + manifest | done | `H0-html-batch.md/.json` | manifest/CLI/hash/report |
| H1 | Nature / PMC adapter 固化 | done | `H1-nature-pmc-adapter.md/.json` | fixture 解析 |
| H2 | HTML 质量门禁 | planned | `H2-html-quality-gate.md/.json` | title/sections/paragraphs |
| H3 | 失败 fallback PDF | planned | `H3-pdf-fallback.md/.json` | HTML 失败才 PDF |
| H4 | Cell / JS 站点适配 | planned | `H4-cell-js-adapter.md/.json` | 403/JS 处理 |

---

## 4. H0 范围

```text
manifest 读取
文件校验
sha256
content_hash 去重
ImportSession
顺序处理
JSON 报告
```

不做：

```text
自动检索 OA 链接
headless browser
Cell adapter
PDF fallback
前端上传
```

---

## 5. manifest

```json
{
  "tenant_id": "default",
  "library_id": "lib_default",
  "items": [
    {
      "source_url": "https://...",
      "staged_path": "documents/html_batch/001.html",
      "doi": "10.1038/..."
    }
  ]
}
```

---

## 6. 执行门禁

```text
H0 完成后
  -> 用 Nature HTML 样本跑通
  -> 报告 duplicate / built / failed
  -> 再进入 H1
```
