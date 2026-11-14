# H3 计划表：HTML 失败后 PDF Fallback

> 阶段：H3  
> 状态：已完成  
> 依赖：H2  
> 目标：HTML 解析或质量门禁失败时，若显式提供 PDF，则回退 PDF；否则 quarantine。

---

## 1. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| H3-1 | fallback 触发 | HTML parse/quality 失败 |
| H3-2 | fallback 条件 | 显式 `pdf_staged_path` |
| H3-3 | 无 PDF | 保持 quarantine |
| H3-4 | 来源记录 | parsed_json.fallback_from=html |
| H3-5 | 不重复 build | 成功 PDF 后不再 build HTML |
| H3-6 | 不自动抓 PDF | 只使用 staged 文件 |

---

## 2. 数据

```text
import_items.fallback_path
```

manifest：

```json
{
  "staged_path": "bad.html",
  "pdf_staged_path": "paper.pdf"
}
```

---

## 3. 行为

```text
HTML
  -> parse
  -> quality
  -> failed
       -> fallback_path exists?
            yes -> PDF build
            no  -> quarantine
```

---

## 4. 验收结果

```text
bad HTML + PDF -> built
fallback_from=html
3 tests passed
```

## 5. 验收

```text
1. 坏 HTML + PDF -> built
2. 坏 HTML + 无 PDF -> quarantined
3. fallback 后 parsed_json 记录 fallback_from
4. 不重复 build HTML
5. 正常 HTML 不触发 PDF
```

---

## 6. 不在 H3

```text
自动搜索 PDF
headless browser
Cell/JS（H4）
```
