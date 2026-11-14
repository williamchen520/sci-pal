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

## 4. 边界

```text
chunk 内函数不二次拆分
R/Python 跨语言调用不解析
动态 Rmd parameter 不解析
```

## 5. 下一步

```text
1. chunk 内 function unit
2. mixed cross-language low-confidence
3. module purpose
```
