# P4c 撤销 public 写结果

> 日期：2026-11-08  
> 状态：**默认连接已切 tenant_writer；旧 public 写模块显式走 owner**  
> 前置：P4c 授权

---

## 1. 当前连接

```text
SCIPAL_PG_DSN              tenant_writer
SCIPAL_PG_OWNER_DSN        owner（scipal）
SCIPAL_PG_MAIN_READ_DSN    main_reader
SCIPAL_PG_TENANT_WRITE_DSN tenant_writer
```

---

## 2. 写入边界

默认连接：

```text
SELECT public      允许
INSERT public      拒绝
业务写             租户 schema
```

显式 owner：

```text
papers / ingest
build_db
systematic
references
tenancy
protocols
review tasks / notifications
paper links / trust flags
```

---

## 3. 验证

```text
tenant_writer:
  INSERT public.papers    permission denied
  INSERT tenant.tasks     成功

systematic:
  create_project         成功
  清理                   成功

A 组 smoke 31 条          0 个 5xx
/api/health               200
```

---

## 4. 解释

这**不是**“public 完全不可写”。

而是：

```text
应用默认连接不能写 public
只有显式 owner 模块可以写 public
```

这是从“全站 owner”到“最小 owner”的中间态。

---

## 5. 未完成

```text
systematic / references / tenancy 仍写 public
protocols / review tasks 仍写 public
tenant_writer 还没有完全替代 owner
public 写权限没有在数据库层对 owner 撤销
```

---

## 6. 回滚

```text
SCIPAL_PG_DSN 恢复为 SCIPAL_PG_OWNER_DSN
重启 app / watch-cron
```

不需要回滚租户数据。

---

## 7. 结论

```text
P4c 第一部分完成
默认 app 连接已受数据库角色约束
剩余 public 写模块需要逐个迁移或继续显式 owner
```
