# H4 计划表：Cell / JS 页面适配

> 阶段：H4  
> 状态：已完成  
> 依赖：H2/H3  
> 目标：识别 Cell 403/Cloudflare/JS 页面，能解析的 Cell HTML 用专用 adapter；不能解析的明确失败，不绕过付费墙。

---

## 1. 决策

| 编号 | 决策 | 结论 |
|---|---|---|
| H4-1 | Cell 403 | 标记 blocked，不解析挑战页 |
| H4-2 | Cloudflare | 标记 blocked |
| H4-3 | JS 空壳 | 标记 js_required |
| H4-4 | 付费墙 | 不绕过 |
| H4-5 | 默认 headless | 不启用 |
| H4-6 | fallback | 有 PDF 走 H3 |
| H4-7 | 可用 HTML | Cell DOM adapter |

---

## 2. 访问分类

```text
ok
blocked
js_required
paywalled
empty
```

标记：

```text
Just a moment
cf-chl
Attention Required
enable JavaScript
subscribe to continue
```

---

## 3. Cell adapter

```text
title      h1 / meta citation_title
abstract   div.abstract / section.abstract
sections   section / div.section
```

---

## 4. 行为

```text
fetch
  -> ok        -> parse
  -> blocked   -> no parse; fallback PDF if provided
  -> js_required -> no parse; fallback PDF if provided
  -> paywalled -> no parse
```

---

## 5. 验收结果

```text
Cell fixture: sections + abstract
403 -> blocked
Cloudflare -> blocked
JS -> js_required
paywall -> paywalled
6 tests passed
```

## 6. 验收

```text
1. 403 -> blocked
2. Cloudflare marker -> blocked
3. JS marker -> js_required
4. Cell fixture -> sections
5. 不把挑战页当正文
6. 无 PDF 时明确失败
```

---

## 7. 不在 H4

```text
headless browser 默认化
付费墙绕过
自动发现 PMC 替代页
```
