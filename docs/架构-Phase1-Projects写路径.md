# Phase 1：Projects 写路径 PG-primary（第一片）

> 日期：2026-11-02  
> 状态：代码完成，生产 flag 未开启。

## 1. 范围

已迁移：

```text
create_project
update_project
add_member
copy_project
```

未迁移：

```text
experiments / revisions / signatures / audit / access requests
```

## 2. 开关

```text
SCIPAL_PROJECT_WRITE_BACKEND=postgres
默认关闭
```

关闭时：

```text
原 SQLite 写路径不变
```

开启时：

```text
1. 权限检查仍读 SQLite
2. PG 先写 projects / project_members
3. SQLite 再写 mirror
4. PG 失败则抛 ProjectWriteError，不写 SQLite
```

## 3. 为什么是 PG-first

```text
Phase 1 目标是 PG-primary
不能先写 SQLite 再异步复制
否则 PG 失败时会留下无法回放的镜像
```

## 4. 代码

```text
services/projects/pg_writes.py
services/projects/service.py
```

函数：

```text
create_project
update_project
add_member
copy_project
```

## 5. 失败语义

```text
PG 写失败
-> ProjectWriteError
-> 调用方收到错误
-> 不执行 SQLite 写
```

如果 PG 成功、SQLite mirror 失败：

```text
PG 已是权威数据
SQLite 可能出现短暂 drift
需要 health/对账修复
```

这是 PG-primary 的预期取舍，不是静默回退。

## 6. 当前生产

```text
SCIPAL_PROJECT_WRITE_BACKEND 未设置
```

所以生产仍走原 SQLite 写；新代码尚未启用。

回填数据：

```text
projects          1
project_members   2
```

## 7. 测试

```text
tests/test_project_pg_writes.py
tests/test_projects_routes.py
```

覆盖：

```text
flag on/off
create/get
member access
non-owner update
```

## 8. 下一步

```text
Phase 1 第二片：experiments 写路径
  create / update
  revisions
  audit
  signatures
  access requests
```

完成后再考虑开启生产 flag 和 canary。
