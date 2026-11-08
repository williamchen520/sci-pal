# P4a 租户隔离结果

> 日期：2026-11-08  
> 状态：**角色与 schema 完成；应用连接未切换**  
> 前置：P4 授权审查

---

## 1. 已创建

```text
角色
  scipal_main_reader     NOLOGIN
  scipal_tenant_writer   NOLOGIN

schema
  lib_ws_default
```

权限：

```text
scipal_main_reader
  SELECT public / catalog / library_main / library_bench
  无写权限

scipal_tenant_writer
  USAGE + CREATE on lib_ws_default
  SELECT catalog
  无 public 写权限
```

---

## 2. SET ROLE 验证

```text
SET ROLE scipal_main_reader;
  SELECT count(*) FROM public.papers;   10102  成功
  INSERT INTO public.papers;            拒绝
```

```text
SET ROLE scipal_tenant_writer;
  CREATE TABLE lib_ws_default.p4_probe; 成功
  DROP TABLE lib_ws_default.p4_probe;   成功
  SELECT count(*) FROM catalog.works;   10119  成功
  INSERT INTO public.papers;            拒绝
```

---

## 3. 当前状态

```text
应用 DSN          仍是 scipal
P4a 边界          已建立
P4b 切换          未做
```

P4a 没有改：

```text
public 数据
API
应用连接
```

---

## 4. 回滚

```sql
DROP SCHEMA IF EXISTS lib_ws_default CASCADE;
DROP ROLE IF EXISTS scipal_tenant_writer;
DROP ROLE IF EXISTS scipal_main_reader;
```

---

## 5. 结论

```text
数据库级只读边界成立
租户 schema 写边界成立
但应用还没使用这两个角色
```

P4b 需要：

```text
1. 为角色配置登录凭据
2. 应用拆分 main_reader / tenant_writer 连接
3. 主库写路径改走租户/受控写入
4. 回归
```
