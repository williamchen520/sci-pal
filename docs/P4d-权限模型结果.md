# P4d 权限模型结果

> 日期：2026-11-08  
> 状态：**app 已移除 superuser 连接；scipal 降为 break-glass**

---

## 1. 角色

```text
scipal_main_reader     只读主库
scipal_tenant_writer   租户读写、主库只读
scipal_ingest          main papers / ingest 写
scipal_admin           身份面 / 迁移，非 superuser
scipal                 break-glass owner
```

---

## 2. 应用连接

```text
SCIPAL_PG_DSN              tenant_writer
SCIPAL_PG_MAIN_READ_DSN    main_reader
SCIPAL_PG_INGEST_DSN       ingest
SCIPAL_PG_ADMIN_DSN        admin
SCIPAL_PG_OWNER_DSN        admin（兼容位，不再是 superuser）
```

---

## 3. 权限

```text
ingest
  INSERT/UPDATE/DELETE main content
  catalog.works / library_main.documents
  无 tenant 写

admin
  身份面 / 迁移
  非 superuser

tenant_writer
  public 只读
  tenant 读写
```

---

## 4. 验证

```text
ingest current_user       scipal_ingest
ingest insert papers      成功
admin current_user        scipal_admin
admin rolsuper            false
admin insert papers       成功（通过 owner membership）
A 组 smoke 31 条          0 个 5xx
```

运行态：

```text
scipal_main_reader     4
scipal_tenant_writer   3
scipal_admin           2
```

没有 app 的 `scipal` 连接。

---

## 5. 边界

```text
scipal 仍在数据库中
但已移出应用 .env 的日常连接
只作为 break-glass
```

---

## 6. 下一步

```text
1. 轮换 scipal 密码，离线保存
2. 给开发者单独只读 prod DSN
3. 开发库 owner 与生产 admin 分离
4. 最后决定 public 是否对 admin 也只读
```
