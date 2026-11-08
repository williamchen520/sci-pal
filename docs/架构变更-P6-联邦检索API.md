# 架构变更授权：P6 联邦检索 API / MCP

> 日期：2026-11-08  
> 状态：**待人类批准修改**  
> 规则：`.dsh_rules` 规则 0A  
> 前置：P5 FederatedRetriever

---

## 1. 问题

P5 只有内部类，没有 API / MCP 入口。

现状：

```text
/api/search/hybrid   单库
/api/search/online   在线
MCP search_hybrid    单库
```

没有：

```text
library_scope
main + bench 联邦结果
跨库来源
```

---

## 2. 变更

新增 API：

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

返回：

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

新增 MCP 工具：

```text
search_federated
```

修改 `ARCHITECTURE.json`：

```text
api.endpoints  185 -> 186
路由键         202 -> 204
```

---

## 3. 理由

```text
让联邦检索可被前端和 MCP 使用
quota_per_scope 防止 bench 被 main 分数完全压住
library_scope 为 P6 的 own scope 留接口
```

---

## 4. 影响

```text
新增只读路由
不改数据库
不改现有 /api/search/hybrid
MCP 工具数 +1
ARCHITECTURE.json 受 arch-guard 保护
```

风险：

```text
main/bench 原始分不可比
quota 只是保底，不是分数校准
own 仍返回空
```

---

## 5. 迁移

```text
无数据库迁移
部署后路由自动可用
MCP 需要重载 server
```

回滚：

```text
删除 /api/search/federated
删除 search_federated
恢复 ARCHITECTURE.json
```

---

## 6. 验证

```text
tests/test_federated_retriever.py   5 passed
tests/test_federated_routes.py      4 passed
scripts/validate_arch.py            204/204 OK
```

部署后：

```text
GET /api/search/federated?q=cancer&library_scope=main,bench
quota=0 -> 全 main
quota=1 -> 至少 1 条 bench
```

---

## 7. 需要批准

```text
1. 新增 /api/search/federated
2. 新增 MCP search_federated
3. ARCHITECTURE.json 185->186 / 202->204
4. 接受 main/bench 分数不可比
5. 接受 own 仍为空
```

批准后提交并合并。
