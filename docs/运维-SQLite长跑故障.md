# 运维主线：SQLite 长跑后句柄失效

> 日期：2026-11-03  
> 状态：**A 方案已验证通过**  
> 触发：连续两次长 eval 后出现 `unable to open database file`

## 1. 现象

```text
长 eval 运行 40–60 分钟后：
  容器内 sqlite3.connect('/app/data/research.db') 成功
  第一条 SELECT 报：
    sqlite3.OperationalError: unable to open database file

宿主机同文件：
  读写正常，papers=3313

容器内：
  /app/data/research.db 存在，1.8GB，权限 777
  /app/data 可写，临时 SQLite 探测库可创建
  重启 deploy-app-1 后立即恢复
```

## 2. 时间线

```text
第一次：96 题 eval 约 40 分钟后，flags_for_papers 500
        重启 app 恢复
第二次：96 题 eval 结束后再次出现
        重启 app 恢复
```

两次都不是 sufficiency/检索逻辑错误；是数据层访问故障。

## 3. 当前证据

```text
SQLite journal_mode = wal
数据目录是 Windows NTFS bind mount -> Docker Desktop
容器内 fd 数量正常（约 31）
宿主机 DB 读写正常
容器内临时 SQLite 正常
只有 research.db 在长跑后无法打开
```

## 4. 根因候选（按可能性）

### A. 宿主机 eval 持有 SQLite 连接过久

`eval/retrieval_eval.py` 当前：

```text
打开 section_conn
整个 96 题期间不关闭
只做 SELECT 映射
```

可能触发 Windows bind mount / WAL 的跨 OS 锁状态，容器端后续连接失败。

### B. Docker Desktop bind mount 句柄老化

```text
Windows NTFS -> Docker Desktop VM
长时间大量读写后，容器内路径句柄失效
重启容器重建挂载后恢复
```

### C. 应用内全局 SQLite 连接失效

```text
HybridSearch.conn 长期持有
Chroma / FTS / flags 查询共享同一文件
单连接坏掉后，新连接也受影响
```

## 5. 方案

### A. eval 不再持有宿主机 SQLite 长连接（优先）

```text
section_of / paragraph_of 改用 PostgreSQL
或每次查询打开/关闭 SQLite
96 题全程不保持宿主机 SQLite 连接
验收：连续 96 题后容器仍能 SELECT papers
```

### B. 数据目录迁到 Docker named volume（彻底）

```text
data/ 从 Windows bind mount 迁到 Linux volume
优点：消除跨 OS 锁
代价：迁移 1.8GB DB + Chroma + 备份；宿主机 eval 访问方式变化
```

### C. 应用层重连 + 健康检查（缓解）

```text
DB 操作捕获 unable to open database file -> 重连重试
/api/health 增加 SELECT 1，失败返回 503
不解决挂载层问题，只缩短故障窗口
```

### D. 运行时全部走 PostgreSQL（长期）

```text
SQLite 只保留 FTS/legacy
减少运行时对 bind mount SQLite 的依赖
```

## 6. 决策建议

```text
先做 A（低成本、可判定）
A 成功 -> 说明 eval 长连接是触发条件
A 失败 -> 直接做 B（named volume），不再重启试错
C 作为并行缓解
D 作为长期架构方向
```

## 7. A 方案验证（2026-11-03）

改动：

```text
eval/retrieval_eval.py
  --pg-dsn 用 PG 做 sentence -> section/paragraph 映射
  无 PG 时每次查询打开/关闭 SQLite
  不再持有宿主机 SQLite 长连接
```

完整 96 题使用 PG 映射：

```text
recall@10   0.6615
refusal     1.00
```

跑完后容器检查：

```text
papers 3313
paper_flags 0
/api/health 200
app healthy
未重启
```

结论：

```text
宿主机 eval 的长期 SQLite 连接是触发条件
A 方案消除了长跑后重启
```

## 8. 停止条件

```text
不再用“重启 app”作为修复
同一方向连续两次负结果 -> 停下来讨论
```

## 8. 当前影响

```text
生产 app 已重启，健康
长 eval 期间可能出现 500
需要人工重启才能恢复
```
