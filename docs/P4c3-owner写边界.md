# P4c3 owner 写边界

> 日期：2026-11-08  
> 状态：**owner 使用已白名单化；public 仍由 owner 管理面可写**

---

## 1. 允许使用 owner 的模块

```text
services/db/pg_pool.py          定义
services/papers/pg_writes.py    main papers 写入
services/papers/pg_links.py     main 图链接
build_db/import_jats_pg.py      main JATS 入库
services/search/ingest.py       main 向量/入库
services/trust/retraction.py    main paper_flags
services/tenancy/service.py     身份面 users/workspaces
```

原因：

```text
main library 是权威主库
ingest / migration / identity 是管理面
```

---

## 2. 不允许使用 owner

其他业务模块必须：

```text
默认 tenant_writer
+ search_path = lib_ws_default
```

P4c3 修复：

```text
review notifications  -> 租户 webhook
risk_of_bias          -> 租户表
review_generator      -> main_reader（原来用 owner 做只读）
```

---

## 3. 审计

脚本：

```text
scripts/audit_owner_writes.py
```

结果：

```text
OWNER_BOUNDARY_OK
```

规则：

```text
白名单外出现 owner_connection 即失败
```

---

## 4. 回归

```text
A 组 smoke 31 条    0 5xx
B 组 smoke 14 条    0 5xx
/api/health          200
```

---

## 5. 仍然存在的边界

```text
scipal 是 owner + superuser
public 对 owner 仍可写
```

所以：

```text
这不是数据库层“public 只读”
而是“应用默认连接不能写 public，管理面 owner 可以”
```

---

## 6. 下一步

真正 public 只读需要：

```text
1. 新建非 superuser 的 admin/ingest 角色
2. 把 scipal 降级/移出日常连接
3. 只给 admin 授予必要的 public 写
4. tenant_writer 只读 public
5. 迁移脚本使用独立 admin DSN
```

这是最后一个不可逆的数据库权限动作。
