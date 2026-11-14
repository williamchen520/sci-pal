# 实验记录：Paper Section API

> 日期：2026-11-14  
> 状态：按 section_type 取整节；批量查询  
> 目标：scipal-paper 不必自己拼 outline

---

## 1. API

```text
GET /api/papers/<paper_id>/sections/<section_type>
```

类型：

```text
front_matter / abstract / results / methods
discussion / back_matter / references / caption
```

返回：

```text
paper_id
section_type
status
section_type_source=heuristic
sections[]
  section_path
  first_para_id
  paragraphs[]
```

## 2. MCP

`scipal-paper` 第 11 个工具：

```text
paper_section(paper_id, section_type)
```

## 3. 实现

```text
paper_outline -> matched rows
paper_paragraphs(limit=200) 一次拉全篇
按 _display_section 分组
```

避免每节开一次 DB 连接。

## 4. 测试

```text
unknown type -> 400
not found -> 404
section -> paragraphs
```

```text
test_paper_sections 3 passed
```

## 5. 路由

```text
json_routes=268
app_routes=268
OK
```

## 6. 边界

```text
section_type 是启发式
app 尚未重启加载新路由
```

## 7. 下一步

```text
1. 重启 app/DSH
2. 验证 sections/results 与 sections/methods
3. parser 正式分类
```
