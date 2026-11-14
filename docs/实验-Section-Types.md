# 实验记录：Outline Section Types

> 日期：2026-11-14  
> 状态：outline 增加 section_type（heuristic）  
> 目标：让 scipal-paper 不必自己猜 Results/Methods

---

## 1. 字段

`paper_outline` 每条新增：

```text
section_type
section_type_source = annotation | heuristic
```

类型：

```text
front_matter
abstract
results
methods
discussion
back_matter
references
caption
```

## 2. 边界

```text
abstract_end   title/abstract 结束 sequence
discussion_seq Discussion 起点
back_seq       availability/references 起点
```

分类：

```text
< discussion 且 <= abstract_end -> front_matter
< discussion 且 > abstract_end  -> results
> discussion 且 < back           -> methods
>= back                          -> back_matter
```

## 3. HCC 实测

```text
sections 43

front_matter   2
abstract       0
results        8
captions       2
discussion     1
methods       21
back_matter   17
references     1
```

## 4. 持久化

迁移：

```text
deploy/sql/038_paragraph_section_type.sql
```

回填：

```text
scripts/backfill_section_types.py
```

命令：

```powershell
python scripts/backfill_section_types.py --paper-id ...
```

回填后：

```text
HCC LAM     43 sections，section_type_source=stored
HCC Genomic 42 sections，section_type_source=stored

Reporting summary 归为 back_matter，不再误判 abstract。
```

## 5. 边界说明

```text
这是输出层启发式
不是 PDF parser 的正式标签
abstract 文本仍可能落在 front_matter
Methods 可能包含 Discussion 后的非方法段落
```

## 6. 测试

```text
outline normalization
section_type field
Results/Methods fallback
```

```text
test_paper_reader 6 passed
```

## 7. 下一步

```text
1. 把 section_type 用于 paper_first 的默认 section
2. parser 正式分类
3. 消除 abstract/front_matter 混淆
```
