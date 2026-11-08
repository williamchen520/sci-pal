# P6 联邦检索 API / MCP 结果

> 日期：2026-11-08  
> 状态：**API 已上线；MCP 工具已注册**

---

## 1. API

```text
GET/POST /api/search/federated
```

参数：

```text
q
top_k
library_scope=own,main,bench
per_scope_k
quota_per_scope
```

响应：

```text
query
library_scope
total
results[]
  identity / work_id / paper_id / title / doi
  score / text
  libraries[]
  provenance[]
```

---

## 2. 上线验证

```text
status 200
total  5
scopes ['main','bench']
libraries:
  main
  bench
  main
  main
  main
```

命令：

```text
GET /api/search/federated
  ?q=cancer
  &top_k=5
  &library_scope=main,bench
  &quota_per_scope=1
```

---

## 3. quota

```text
quota=0  全部 main
quota=1  至少 1 条 bench
```

bench 不再被 main 分数完全压住。

---

## 4. 架构

```text
api.endpoints  185 -> 186
路由键         202 -> 204
validate_arch  204/204 OK
```

---

## 5. MCP

新增：

```text
search_federated
```

调用：

```text
POST /api/search/federated
```

---

## 6. 已知边界

```text
main/bench 原始 ts_rank 仍不可直接比较
quota 只是保底，不是分数校准
own scope 仍返回空
```

---

## 7. 验证

```text
FederatedRetriever    5 passed
Federated routes      4 passed
/api/search/federated 200
A 组 smoke            无新增 5xx
```
