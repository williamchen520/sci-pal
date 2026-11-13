# 实验记录：R12 Reviewer 指派与完成度

> 日期：2026-11-13  
> 状态：**assignment API/UI/完成回写通过**  
> 目标：把“双人裁决”从任意提交变成可指派任务

---

## 1. 数据

```text
rag_review_assignments
  multi_run_id
  rag_id
  reviewer_user_id
  status assigned / completed
  assigned_by
  completed_at
```

唯一键：

```text
(multi_run_id, rag_id, reviewer_user_id)
```

## 2. API

```text
GET  /api/rag/multi/<id>/assignments
POST /api/rag/multi/<id>/assignments
```

指派需要：

```text
human session
workspace manage_members（owner）
```

目标用户必须是：

```text
active
owner / pi / reviewer
```

## 3. 完成回写

reviewer 提交裁决后：

```text
add_adjudication
  -> complete_assignment
```

同理，下一次读取 assignment 时：

```text
status completed
completed_at ...
```

## 4. Live 服务验收

```text
assigned  asg_61fec6a07d64 assigned
completed status completed
completed_at 2026-11-13T09:35:07
```

临时用户和 assignment 已清理。

## 5. UI

evidence 页面每个 group：

```text
已有 reviewer 状态
owner 可指派 reviewer
```

## 6. 测试

```text
assignment list
human required
owner assign
```

```text
tests.test_rag_assignments 3 passed
validate_arch 245/245 OK
```

## 7. 边界

```text
没有“必须两人”强制
没有指派通知
没有签名
```

## 8. 下一步

```text
双人完成度 gate
裁决签名/时间戳
```
