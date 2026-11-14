# H1 计划表：Nature / PMC HTML Adapter

> 阶段：H1  
> 状态：已完成  
> 依赖：H0  
> 目标：Nature 与 PMC 的 section 结构固化，避免通用 `section` 选择器漂移。

---

## 1. 选择器

### Nature

```text
title       h1.c-article-title / meta citation_title
abstract    div#Abs1-content / section[data-title="Abstract"]
sections    section[data-title]
paragraphs  section 直属 p
```

### PMC

```text
title       h1.content-title / meta citation_title
abstract    section.abstract / div.abstract
sections    section / div.sec
paragraphs  直属 p
```

---

## 2. 任务

| 子任务 | 内容 | 产物 | 验收 |
|---|---|---|---|
| H1.1 | publisher detect | `services/papers/html_adapters.py` | nature/pmc/other |
| H1.2 | Nature sections | 同上 | data-title 优先 |
| H1.3 | PMC sections | 同上 | section/div.sec |
| H1.4 | 接入 html_parser | `html_parser.py` | publisher 字段 |
| H1.5 | fixtures | `tests/fixtures/html/` | nature/pmc |
| H1.6 | tests | `tests/test_html_adapters.py` | 结构稳定 |

---

## 3. 验收结果

```text
Nature: 15 sections / abstract 1386 chars
PMC fixture: passed
3 adapter tests passed
```

## 4. 验收

```text
1. nature.com 识别为 nature
2. ncbi/pmc 识别为 pmc
3. Nature 使用 data-title sections
4. PMC 使用 section/div.sec
5. 不改变 generic 行为
6. fixture 测试通过
```

---

## 5. 不在 H1

```text
HTML 质量门禁（H2）
PDF fallback（H3）
Cell/JS（H4）
自动抓取
```
