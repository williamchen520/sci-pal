# 架构变更授权：P4b 应用连接拆分

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P4a 角色/schema 已合并

---

## 1. 问题

P4a 建立了数据库边界，但应用仍用超级用户：

```text
SCIPAL_PG_DSN -> scipal (superuser)
scipal_main_reader   未使用
scipal_tenant_writer 未使用
```

后果：

```text
应用仍可写主库
数据库只读边界只是存在，没有生效
租户写入没有独立连接
```

---

## 2. 变更

改哪一层：

```text
权限 + 应用连接
```

新增连接：

```text
SCIPAL_PG_MAIN_READ_DSN
  scipal_main_reader

SCIPAL_PG_TENANT_WRITE_DSN
  scipal_tenant_writer
```

新增 helper：

```text
services/db/pg_pool.py
  main_read_connection()
  tenant_write_connection()
```

P4b1 切换范围：

```text
search
evidence
papers 读
review 读
bench 读
```

不切换：

```text
projects / experiments 写
reviews / claims 写
tasks / watch / ingest 写
```

说明：

```text
P4b1 先让“读主库”走只读角色
P4b2 再把 workspace 写路径迁到租户 schema
```

---

## 3. 理由

全量切 main_reader 会立刻打断：

```text
项目创建
实验更新
综述保存
claim 裁决
任务状态
入库
```

这些仍写 public。

P4b1 的最小安全收益：

```text
检索/证据/论文读取不可能写主库
主库只读边界开始真正生效
```

---

## 4. 影响

影响模块：

```text
services/db/pg_pool.py
services/search/*
services/review/pg_read / pg_systematic
services/papers/ read path
```

数据：

```text
不迁移数据
不改变现有写路径
```

风险：

```text
读连接权限不足 -> 回退到 owner DSN
配置缺失 -> 启动失败或回退
```

回滚：

```text
删除两个 DSN 环境变量
helper 回退 SCIPAL_PG_DSN
```

---

## 5. 迁移

步骤：

```text
1. 给两个角色设置登录凭据
2. 增加 DSN 环境变量
3. 增加 helper
4. 读路径逐个切换
5. 回归
6. 保留写路径 owner
```

P4b1 不做：

```text
不改 public 写路径
不迁移 workspace 数据
不切 tenant_writer 到现有写接口
```

---

## 6. 验证

```text
main_read DSN:
  SELECT papers 成功
  INSERT papers 拒绝

tenant_write DSN:
  CREATE lib_ws_default 表成功
  INSERT public 拒绝

应用:
  /api/health 200
  A/B 组 smoke 无 5xx
  检索结果与 owner 连接一致
```

---

## 7. 需要批准

```text
1. 新增两个 DSN 环境变量
2. 给 scipal_main_reader / scipal_tenant_writer 配置登录凭据
3. P4b1 只切读路径
4. 写路径暂时保留 owner
```

批准后先建连接 helper + 单端点验证，再批量切读路径。
