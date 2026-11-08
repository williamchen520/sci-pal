# P4f 独立开发库结果

> 日期：2026-11-08  
> 状态：**scipal_dev 已建；开发 owner 与生产 admin 分离**

---

## 1. 开发库

```text
database   scipal_dev
owner      scipal_dev_owner
tables     122
rows       0
extension  vector
```

只复制 schema，不复制生产数据。

---

## 2. 角色

```text
scipal_dev_owner
  LOGIN
  database owner
  可 DDL
  只访问 scipal_dev
```

生产：

```text
scipal_admin
scipal_ingest
scipal_tenant_writer
scipal_main_reader
scipal（break-glass）
```

---

## 3. DSN

```text
SCIPAL_PG_DEV_OWNER_DSN -> scipal_dev
SCIPAL_PG_DEV_READ_DSN   -> main_reader（生产只读）
```

`SCIPAL_PG_DEV_OWNER_DSN` 不进入 app，只给开发/测试。

---

## 4. 验证

```text
scipal_dev tables     122
scipal_dev papers       0
current_user          scipal_dev_owner
CREATE/DROP table     成功
```

---

## 5. 当前权限

```text
生产 app              tenant_writer / main_reader / ingest / admin
开发                   dev_owner（scipal_dev）
生产排障               main_reader
迁移                   admin
紧急                   break-glass
```

---

## 6. 未完成

```text
scipal_dev 还没有种子数据
public 对 admin 仍可写
```

---

## 7. 结论

```text
开发者不再需要生产 admin 来跑本地代码
开发库 owner 与生产权限分离
```
