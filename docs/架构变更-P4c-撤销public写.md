# 架构变更授权：P4c 撤销 public 写权限

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P4 最终切换完成

---

## 1. 问题

现在无法靠一条 `REVOKE` 让 public 只读。

证据：

```text
应用连接角色     scipal
rolsuper         true
public 表 owner  scipal
```

后果：

```text
superuser 绕过权限检查
owner 天然拥有写权限
REVOKE 对 scipal 不生效
```

而且应用仍有以下写 public 的路径：

```text
papers / ingest
build_db 写入
管理员迁移
```

---

## 2. 变更

改哪一层：

```text
权限 + 应用连接
```

新增 DSN：

```text
SCIPAL_PG_DSN              tenant_writer
SCIPAL_PG_OWNER_DSN        owner
SCIPAL_PG_MAIN_READ_DSN    main_reader
```

职责：

```text
tenant_writer
  业务写（reviews/projects/claims/tasks/watch）
  只读 public
  不能写 public

owner
  只用于 papers / ingest / migrations / admin

main_reader
  只读主库
```

需要修改：

```text
services/papers/pg_writes.py
build_db/import_jats_pg.py
build_db/db_writer.py
services/search/ingest.py
迁移/管理脚本
```

这些写 papers 的模块改用 `SCIPAL_PG_OWNER_DSN`。

其余业务写通过：

```text
SCIPAL_PG_DSN=tenant_writer
+ SCIPAL_TENANT_PILOT
```

---

## 3. 理由

```text
只有把应用默认连接换成非 owner
public 写权限才真正无法使用
```

如果只 REVOKE：

```text
应用还是 superuser
约束不存在
```

如果直接切 DSN 不分离 owner：

```text
papers/ingest 立刻失效
```

---

## 4. 影响

读：

```text
tenant_writer 需要 SELECT public / catalog / library_main / library_bench
```

写：

```text
业务 -> tenant schema
papers/ingest -> owner
```

风险：

```text
某些未识别的 public 写路径会失败
需要逐个回归
```

---

## 5. 迁移

步骤：

```text
1. 给 tenant_writer 授 public 只读
2. 新增 SCIPAL_PG_OWNER_DSN
3. papers/ingest 写路径改用 owner
4. 切换 SCIPAL_PG_DSN=tenant_writer
5. 重启 app
6. 回归
```

回滚：

```text
SCIPAL_PG_DSN 恢复 owner
SCIPAL_PG_OWNER_DSN 可保留
```

---

## 6. 验证

```text
tenant_writer:
  SELECT public.papers 成功
  INSERT public.papers 拒绝

papers/ingest:
  用 owner DSN 写入成功

业务:
  reviews/projects/claims/tasks/watch 写租户成功
  public 计数不增长

A/B 组 smoke 无 5xx
```

---

## 7. 需要批准

```text
1. 新增 SCIPAL_PG_OWNER_DSN
2. tenant_writer 授 public 只读
3. papers/ingest 改用 owner
4. 应用默认 DSN 切 tenant_writer
5. 逐个回归 public 写路径
```

批准后先做单端点，不要一次切全站。
