# P4e 开发者权限与 break-glass

> 日期：2026-11-08  
> 状态：**superuser 已移出应用；密码轮换完成**

---

## 1. 角色

| 角色 | 用途 | 属性 |
|---|---|---|
| `scipal_main_reader` | 生产只读 | 无 superuser |
| `scipal_tenant_writer` | 租户读写 | 无 superuser |
| `scipal_ingest` | main papers/ingest 写 | 无 superuser |
| `scipal_admin` | 身份/迁移 | 无 superuser |
| `scipal` | break-glass | superuser |

---

## 2. 应用连接

```text
SCIPAL_PG_DSN              tenant_writer
SCIPAL_PG_MAIN_READ_DSN    main_reader
SCIPAL_PG_INGEST_DSN       ingest
SCIPAL_PG_ADMIN_DSN        admin
SCIPAL_PG_OWNER_DSN        admin（兼容位）
SCIPAL_PG_DEV_READ_DSN     main_reader（开发者）
```

应用不持有 `scipal` 密码。

---

## 3. break-glass

密码文件：

```text
G:\sciPal_deploy\secrets\scipal_breakglass.txt
```

ACL：

```text
仅当前 Windows 用户可读写
不进入 git
不进入 .env
```

使用原则：

```text
只在迁移失败/恢复/紧急修复时使用
用完轮换
```

---

## 4. 开发者权限

```text
生产：main_reader，只读
开发：开发库 owner（建议独立库）
迁移：scipal_admin / 离线 break-glass
```

不允许：

```text
用 scipal 日常查库
把 break-glass 密码放进 .env
让 app 使用 superuser
```

---

## 5. 当前边界

```text
app                    reader / tenant / ingest / admin
public 主数据           ingest 可写
public 身份面           admin 可写
public 租户业务表        tenant 写租户副本
```

---

## 6. 未完成

```text
开发库尚未独立
public 对 admin 仍可写
```

---

## 7. 结论

```text
开发者权限 != 应用权限
开发者权限 != 生产 superuser
```

生产 superuser 现在是离线 break-glass，不再是日常连接。
