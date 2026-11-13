# 实验记录：R10 Reviewer 权限

> 日期：2026-11-13  
> 状态：**reviewer role + review_evidence 权限通过**  
> 目标：不是所有登录用户都能裁决

---

## 1. 角色

新增：

```text
reviewer
```

权限：

```text
read_workspace
review_evidence
```

| 角色 | review_evidence |
|---|---|
| owner | yes |
| pi | yes |
| reviewer | yes |
| member | no |
| viewer | no |

## 2. workspace scope

`rag_multi_queries` 增加：

```text
workspace_id default ws_default
```

裁决/冲突 API：

```text
get_multi(multi_run_id)
  -> workspace_id
authorize(user_id, workspace_id, "review_evidence")
```

没有权限：

```text
403 reviewer permission required
```

## 3. 人类限制

仍然要求：

```text
human session
internal token 被拒绝
```

所以是双门：

```text
不是 agent
且
有 reviewer 权限
```

## 4. UI

workspace member 角色下拉增加：

```text
reviewer
```

## 5. 测试

```text
reviewer role known
member/viewer cannot review
pi can review
reviewer authorize route
```

```text
10 passed
```

## 6. 边界

```text
没有 reviewer 分组/指派
没有双人独立裁决
没有签名
```

## 7. 下一步

```text
双人 reviewer / kappa
裁决签名
```
