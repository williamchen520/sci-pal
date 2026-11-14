# 实验记录：Paper Module Map

> 日期：2026-11-14  
> 状态：从已绑定 code library 汇总模块；不生成 LLM 说明  
> 目标：给 `scipal-paper` 提供 file/module 级视图

---

## 1. 服务

```text
services/papers/modules.py
GET /api/papers/<paper_id>/modules
```

返回：

```text
path
language
unit_count
symbols
edges {imports, calls}
```

## 2. HCC 实测

```text
status   ok
modules  7
```

| module | units | symbols | imports |
|---|---:|---|---:|
| Figure.1.R | 1 | Figure.1.R | 12 |
| Figure.2.R | 3 | Figure.2.R, new_function1, new_function2 | 23 |
| Figure.3.R | 1 | Figure.3.R | 12 |
| Figure.4.R | 1 | Figure.4.R | 17 |
| Figure.5.R | 1 | Figure.5.R | 19 |
| Figure.6.R | 1 | Figure.6.R | 17 |
| Figure.7.R | 1 | Figure.7.R | 17 |

## 3. 解释

这 7 个脚本主要是顶层分析脚本：

```text
file unit
```

Figure.2 有两个函数单元，所以是 3 个 unit。

`unit_count` 不等于“业务模块数”；它反映 parser 看到的单元。

## 4. 不做什么

```text
不生成 LLM 模块说明
不猜 purpose
不把 file unit 当函数
```

`purpose` 留给 scipal-paper/LLM 基于代码与论文生成，并必须标 inferred。

## 5. 测试

```text
unbound -> status unbound
bound -> modules 1, imports 12
```

```text
test_paper_modules 2 passed
```

## 6. 路由

```text
json_routes=265
app_routes=265
OK
```

## 7. 下一步

```text
1. purpose 生成（标 inferred）
2. data flow edges
3. Rmd/mixed parser
```
