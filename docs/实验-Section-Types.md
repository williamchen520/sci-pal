# 实验记录：Outline Section Types

> 日期：2026-11-14  
> 状态：outline 增加 section_type（heuristic）  
> 目标：让 scipal-paper 不必自己猜 Results/Methods

---

## 1. 字段

`paper_outline` 每条新增：

```text
section_type
section_type_source = heuristic
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
abstract       1
results        8
captions       2
discussion     1
methods       21
back_matter    7
references     1
```

## 4. 边界说明

```text
这是输出层启发式
不是 PDF parser 的正式标签
abstract 文本仍可能落在 front_matter
Methods 可能包含 Discussion 后的非方法段落
```

## 5. 测试

```text
outline normalization
section_type field
Results/Methods fallback
```

```text
test_paper_reader 6 passed
```

## 6. 下一步

```text
1. 把 section_type 用于 paper_first 的默认 section
2. parser 正式分类
3. 消除 abstract/front_matter 混淆
```
