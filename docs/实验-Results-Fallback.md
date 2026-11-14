# 实验记录：Results Section Fallback

> 日期：2026-11-14  
> 状态：PDF body 标签下可按标题边界回退 Results  
> 目标：不让 `section=Results` 因 parser 标签缺失而直接为空

---

## 1. 问题

PDF parser 把正文标成：

```text
section_level1 = body
section_level2 = 实际小标题
```

`section_level1='results'` 只有 figure caption，导致：

```text
paper_first_paragraph(section="Results")
-> None
```

## 2. Fallback

仅当 `section=Results` 且正常查询为空时：

```text
body
  AND section_level2 非空
  AND section_level2 != paper.title
  AND 排除 article/abstract/availability/references...
  AND sequence < Discussion 起点
```

返回行带：

```text
section_fallback = body_headings
```

## 3. HCC 实测

```text
first  para_0013
title  Establish a single-cell atlas...
count  29
range  para_0013 .. para_0048
```

## 4. 边界

```text
这是启发式
不是 parser 的正式 section 标签
没有 Discussion 时可能包含 Methods
只对 Results 启用
```

## 5. 测试

```text
normal section filter
Results body fallback
empty first
```

```text
test_paper_reader 5 passed
```

## 6. 路由

```text
json_routes=267
app_routes=267
```

## 7. 下一步

```text
1. 重启 app
2. DSH 验证 section=Results
3. parser 正式 section 分类
```
