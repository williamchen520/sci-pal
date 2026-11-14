# 实验记录：Rmd/Quarto 与 mixed repo

> 日期：2026-11-14  
> 状态：Rmd/Quarto chunk 解析 + `--language auto` 可用  
> 边界：chunk 是单元，不做跨语言调用图

---

## 1. Rmd/Quarto

```text
```{r setup}
...
```

```{python label=plot}
...
```
```

输出：

```text
file unit
chunk unit
  symbol_name = label
  text = chunk body
  inner function unit
    parent_unit_id = chunk unit
```

支持 label：

```text
```{r setup}
```{r label=foo}
```{python #bar}
```

## 2. mixed repo

```text
--language auto
```

按文件判断：

```text
.py    python
.R/.r  r
.Rmd/.qmd rmd
.nf    nextflow
```

同一 snapshot：

```text
code_files.language 按文件记录
```

## 3. 测试

```text
Rmd 2 chunks
setup / plot labels
file_language mapping
```

```text
test_code_rag_r_parser 5 passed
```

## 4. chunk 内函数

R chunk：

```r
norm <- function(x) { x / sum(x) }
```

现在会生成：

```text
chunk setup
  -> function norm
```

Python chunk 同理。

## 5. 边界

```text
跨语言调用不解析
动态 Rmd parameter 不解析
chunk 内 class 只做 parser 支持范围
```

## 6. 下一步

```text
1. chunk 内 function unit
2. mixed cross-language low-confidence
3. module purpose
```
