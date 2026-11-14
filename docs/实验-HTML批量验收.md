# 实验记录：HTML-first 批量入库验收

> 日期：2026-11-14  
> 范围：H0–H4  
> 状态：通过  
> 结论：HTML batch 可用；Cell/JS 明确分类；PDF fallback 可用

---

## 1. 验收批次

```text
manifest   G:\runs\h5\manifest.json
items      3

good.html  Nature OA HTML
bad.html   低质量 HTML + PDF fallback
low.html   低质量 HTML，无 PDF
```

## 2. 结果

```text
total       3
duplicate   1
built       1
quarantined 1
failed      0
```

明细：

```text
good.html  duplicate（此前已 built）
bad.html   built（fallback_from=html）
           paper_PMC13612245_af789a81be08
low.html   quarantined
           title missing or too short
           abstract too short
           too few sections
           too few paragraphs
```

## 3. 验证点

```text
hash 去重              通过
HTML parse             通过
HTML quality gate      通过
PDF fallback           通过
fallback_from 记录     通过
低质量 quarantine      通过
单篇失败不阻塞整批     通过
```

## 4. Cell / JS 访问层

```text
403                    -> blocked
Just a moment/cf-chl   -> blocked
enable JavaScript      -> js_required
subscribe to continue  -> paywalled
```

不解析挑战页，不绕过付费墙。

## 5. 测试

```text
test_html_batch       4
test_html_quality     6
test_html_adapters    3
test_html_access      6
test_import_fallback  3
```

## 6. 尚未做

```text
真实 Cell HTML 抓取（当前 403）
自动发现 PMC 替代页
headless browser
自动 OA URL 发现
前端批量上传
```

## 7. 真实 OA 批量

Nature：

```text
2 items
2 built
0 failed

paper_import_9da1e0ffb60a
  Single cell proteomic analysis...   272 paras / 820 sentences
paper_import_106459887625
  Molecularly defined cellular atlas... 294 paras / 1049 sentences
```

PMC：

```text
PMC12816625
paper_import_15c6a0f864b0
  Single cell proteomic analysis...     27 paras / 133 sentences
```

PMC 页面段落更粗（PMC 原生段落），但内容完整；H1 PMC adapter 已修：

```text
只取 main article > section.body 的直接子 section
忽略外层 Abstract 干扰
```

## 8. 前端上传

```text
POST /api/imports/upload
  -> 201
  -> staging file
  -> ImportSession queued
  -> 不自动 build
```

页面：

```text
frontend/imports.html
```

## 9. 结论

```text
H0  batch CLI              done
H1  Nature/PMC adapters     done
H2  quality gate            done
H3  PDF fallback            done
H4  Cell/JS access          done

HTML-first 批量入库可用；
Cell 需要 PMC/PDF 替代路径。
```
