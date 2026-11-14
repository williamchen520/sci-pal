# H0 计划表：HTML Batch CLI

> 阶段：H0  
> 状态：已完成  
> 依赖：N0 ImportSession  
> 目标：manifest + CLI + sha256 + 去重 + 顺序处理 + JSON 报告

---

## 1. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| H0-1 | 输入 | JSON manifest |
| H0-2 | 文件 | 本地 staged_path |
| H0-3 | hash | sha256 |
| H0-4 | 去重 | content_hash |
| H0-5 | 处理 | 顺序，避免 PDF/模型并发 |
| H0-6 | 输出 | JSON report |
| H0-7 | 不做 | 自动抓取、headless、PDF fallback |

---

## 2. manifest

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

## 3. CLI

```powershell
python scripts/import_html_batch.py `
  --manifest docs/html_batch.json `
  --limit 20 `
  --report docs/html_batch_report.json
```

`--dry-run` 只校验，不写库。

---

## 4. 行为

```text
读取 manifest
校验 library_id / items
检查文件存在
计算 sha256
查询 import_items 是否已 built
  -> duplicate：跳过
  -> 新文件：创建 ImportSession
逐篇 PaperLaneAdapter(build=True)
写 JSON report
```

---

## 5. 验收结果

```text
total 2
duplicate 1
built 1
paper paper_import_ae63f39672ad
paragraphs 178
sentences 692
```

## 6. 验收

```text
1. manifest 缺失字段拒绝
2. 文件不存在拒绝
3. sha256 稳定
4. 重复 hash 跳过
5. 单篇失败不影响整批
6. report 有 status/paper_id/error
7. dry-run 不写库
```

---

## 7. 不在 H0

```text
自动发现 OA 链接
Nature/Cell adapter
HTML 质量门禁
PDF fallback
前端上传
```
