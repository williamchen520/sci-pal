# 实验记录：HTML 论文解析器

> 日期：2026-11-13  
> 状态：HTML parser + CLI 可用；尚未写入 corpus DB

---

## 1. 实现

```text
services/papers/html_parser.py
scripts/parse_html_paper.py
```

输出：

```text
title
doi
journal
published
authors
license
abstract
sections
figures
code_links
data_links
repo_links
content_hash
warnings
```

## 2. 真实页面验证

输入：

```text
https://doi.org/10.1038/s41467-026-73212-y
HTML 720,196 bytes
```

输出：

```text
title       Integrated genomic analyses identify ...
doi         10.1038/s41467-026-73212-y
sections    17
figures     7
code_links  1
warnings    0
```

Code availability 提取：

```text
https://doi.org/10.5281/zenodo.17236540
```

正文还提取到：

```text
https://github.com/genome/bam-readcount
```

## 3. 解析结构

```text
<section data-title="...">
  <h2>...</h2>
  <p>...</p>
  <figure><figcaption>...</figcaption></figure>
</section>
```

## 4. 边界

```text
sections 目前包含 References/Author information 等
还没有过滤成“正文 section”
还没有写入 papers/paragraphs
还没有 JATS XML parser
还没有 HTML -> paper_sources 注册
```

## 5. 测试

```text
metadata + abstract + sections
figures + code links
content hash stable
```

```text
tests.test_html_parser 3 passed
```

## 6. 下一步

```text
1. section 过滤（正文/方法/结果）
2. paper_sources 入库
3. HTML -> paragraphs -> embeddings
4. JATS XML parser
```

HTML 解析本身不是难点；难点是**入库后与 PDF/PMID 去重并建立同一 paper_id**。
