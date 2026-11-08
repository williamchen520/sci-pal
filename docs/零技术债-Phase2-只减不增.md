# 零技术债 Phase 2：只减不增

> 日期：2026-11-08  
> 状态：**新增 SQLite connect 已可拦截；存量 fallback 未删**

---

## 1. Allowlist

```text
scripts/sqlite_connect_allowlist.txt
62 个现有文件
```

覆盖：

```text
services/
routes/
api_server.py
```

---

## 2. Audit

```bash
python scripts/audit_sqlite.py
```

结果：

```text
SQLITE_ALLOWLIST_OK 62
```

新文件出现：

```text
SQLITE_NEW_CONNECTIONS
```

删除文件后 allowlist 过期：

```text
SQLITE_ALLOWLIST_STALE
```

---

## 3. Hook

`.githooks/pre-commit`

```text
services / routes / api_server.py 有变更
-> audit_sqlite.py
-> 新 connect 直接拒绝提交
```

---

## 4. build_db

`build_db/LEGACY.md` 已存在，补充 runtime guard 说明：

```text
legacy 脚本只能在容器外、维护窗口运行
不能依赖运行时 fallback
```

---

## 5. 当前边界

```text
运行时        SQLite connect 被拒绝
新增代码      不能新增 connect
存量代码      62 个文件仍有 connect
tests/        临时 SQLite 保留
build_db/     离线 legacy
```

---

## 6. 下一步

```text
1. 从 allowlist 挑一个模块删 fallback
2. 更新 allowlist（只减）
3. 跑分组测试
4. 循环直到 0
```
