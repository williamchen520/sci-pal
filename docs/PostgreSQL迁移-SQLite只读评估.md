# SQLite 只读评估

日期：2026-11-06

## 1. 目标

判断生产 SQLite 是否可切 `PRAGMA query_only=ON`。

## 2. 观测

重启 app 后：

```text
research.db size        1,837,252,608
research.db mtime       2026-11-06 04:47:37
wal size                0
```

调用读接口：

```text
/api/health
/api/watch/profiles
/api/projects
/api/review-projects
```

再次检查：

```text
research.db size        不变
research.db mtime       不变
wal                     无写入帧
```

## 3. 静态检查

以下模块已 PG 化，但仍有 SQLite fallback/回滚路径：

```text
services/review/notifications.py
services/review/review_repository.py
services/claims/service.py
services/protocols/service.py
services/watch/repo.py
services/watch/runner.py
services/tenancy/service.py
services/search/ingest.py
services/search/online_downloader.py
services/trust/retraction.py
```

生产开关：

```text
SCIPAL_SYSTEMATIC_BACKEND=postgres
SCIPAL_CLAIMS_BACKEND=postgres
SCIPAL_PROTOCOLS_BACKEND=postgres
SCIPAL_WATCH_PG_STORE=1
SCIPAL_TENANCY_PG_ONLY=1
SCIPAL_INGEST_PG_ONLY=1
```

## 4. 结论

```text
当前没有观察到运行时 SQLite 写入
但不能直接 chmod 只读
```

原因：

```text
1. 仍有 fallback 分支
2. 仍有 SQLite 直接连接
3. watch repo 未删除
4. WAL/SHM 需要可写
```

## 5. 建议

先做：

```text
P7a 删除 watch repo SQLite 路径
P7b 清理 SQLite fallback
P7c 统一 sqlite 连接工厂
P7d 再加 query_only 开关
```

不要：

```text
直接 chmod 444
直接 PRAGMA query_only 全局
```

## 6. 当前状态

```text
SQLite 仍可写
生产健康
检索无回退
```
