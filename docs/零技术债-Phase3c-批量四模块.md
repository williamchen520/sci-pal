# 零技术债 Phase 3c：批量四模块

> 日期：2026-11-08  
> 状态：**四个模块的 SQLite fallback 已删除**

---

## 1. auto_merger

```text
sqlite3 -> main_read_connection
AutoMerger(db_path) 兼容参数保留
查询 public.paragraphs
```

测试改为 fake PG，不再建 SQLite。

---

## 2. boilerplate_filter

删除：

```text
sqlite3
DB_PATH
_audit()
__main__ CLI
```

保留纯函数：

```text
is_boilerplate_line
clean_boilerplate
```

---

## 3. reference_filter

删除：

```text
sqlite3
DB_PATH
_audit()
__main__ CLI
```

保留纯函数：

```text
is_reference_entry
```

---

## 4. domain_router

```text
sqlite3 -> main_read_connection
paper_domains / domain_profiles 从 PG 读
db_path 兼容参数保留
```

---

## 5. Allowlist

```text
60 -> 56
SQLITE_ALLOWLIST_OK 56
```

---

## 6. 测试

```text
auto_merger / domain_router / hybrid_filter / search_filters
29 passed
```

---

## 7. 说明

```text
auto_merger 和 domain_router 是活路径
改成 PG 读，不是 no-op
boilerplate/reference 只删离线审计
```
