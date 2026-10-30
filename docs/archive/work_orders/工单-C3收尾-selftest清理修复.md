# 工单 · C-3 收尾：selftest 清理静默失败（D-2）

> 派单方：WorkBuddy ｜ 执行方：CodeBuddy ｜ 生成时间：2026-10-25 10:55
> 前置：C-3 已验收（`dev` `294deb1`，18 工具在线）
> 范围极小：**只改 `mcp_server/selftest.py`**。允许改测试代码，**不许改业务代码**。

---

## 一、问题（我已复跑确认，不是推测）

C-3 的 selftest 跑出这样一段，**两条都记 PASS，但清理根本没发生**：

```text
[PASS] ask_question        耗时=0.05s task_id=b17b9323-...
[INFO] 已请求取消 b17b9323-...: Unknown tool: cancel_review_task
[PASS] agentic_search      耗时=0.08s task_id=a859a9a4-...
[INFO] 已请求取消 a859a9a4-...: Unknown tool: cancel_review_task
```

原因：`cancel_review_task` 这个工具只存在于 **`scipal-generate`**，而这两条断言跑在
**`scipal-search`** 的会话里（`mcp_server/selftest.py:81` / `:231-248`），
所以 `session.call_tool("cancel_review_task", ...)` 必然返回 `Unknown tool`。

更糟的是**失败被当成信息打印掉了**：`call_tool` 返回的是「错误结果」而不是抛异常，
所以 `except` 分支不会走，代码只打了 `[INFO] 已请求取消 …: Unknown tool: …`，
看起来像成功。实测后果：selftest 结束后有一个 `qa_ask` 任务仍在跑
（`GET /api/review/running_task` 返回 `running`，我用 curl 手工取消的）。

**这不是纯测试问题**，它暴露了两件事：
1. 测试的清理逻辑**依赖被测量的工具面**，工具不在本 server 就静默失败；
2. 这个仓库有「失败不报警」的坏习惯（C-1 的 `except: pass` 也是同类），必须掐掉。

---

## 二、修复要求（按建议方案 2）

### T-1 清理改走 HTTP，不走 MCP 工具

`selftest.py` 已有 `_base_url()` 与 `_flask_running()`。清理改成直接对 Flask 发
`POST {base}/api/review/cancel/<task_id>`（用标准库 `urllib.request`，**记得
`ProxyHandler({})` 绕开本机代理** —— 看门狗里就是这么写的，照抄）。

理由：清理是**测试的副作用处理**，不应该依赖「被测工具是否在当前 server 暴露」。
顺带解决跨 server 分工带来的尴尬（提交在 search、取消在 generate）。

### T-2 清理失败必须可见，不许静默

- 成功（HTTP 200 `{"success": true}`）→ `[INFO] 已取消 <task_id>`
- **404 `Task not found or already finished`** → 视为正常（任务已经跑完了），打 `[INFO] 任务已结束，无需取消`
- 其它任何情况（连不上 / 5xx / `Unknown tool` 之类）→ 打 **`[WARN]`**，并且
  **在最终汇总里体现**（例如汇总行多一句 `leftover_tasks=N`）

### T-3 收尾自检：跑完确认没有遗留任务

`main()` 结束时（在所有 server 测完之后）调一次
`GET {base}/api/review/running_task`：

- 返回 `{"running": false}` → `[OK] 无遗留任务`
- 返回 `running: true` → 打出**遗留任务的 task_id / task_type / progress**，
  并在汇总里标 `[WARN] 有 N 个任务仍在运行（可能是取消未生效）`

**不要**因此让整个 selftest 失败（任务可能刚好还在收尾）；但**必须让它在输出里显眼**。

### T-4 顺手：`except: pass` 类坏习惯排查

`grep -n "except: *pass\|except Exception: *pass" mcp_server/*.py`
若有命中，改成打印 `[WARN]` 后再继续。结果贴进交付报告。

---

## 三、硬要求

1. **只改 `mcp_server/selftest.py`**（T-4 也只改 `mcp_server/*.py` 里的 pass 分支）。
2. **不许改** `api_server.py` / `services/**` / 三个 `*_server.py` 的工具定义。
3. 不许 `git add -A`（仓库里有别人的 `_test_v3317b.py`）。
4. 提交前缀 `V33.17: C-3 收尾 —— `，**不要自己 push**。

---

## 四、验收判据（WorkBuddy 会独立复跑）

| 判据 | 期望 |
|---|---|
| 断言总数不变 | 仍是 **25**，全 PASS / exit 0（本次不新增断言） |
| 清理真发生 | 跑完后 `GET /api/review/running_task` 返回 `running: false`，或输出里明确标出遗留并给 task_id |
| 失败可见 | 输出里不再出现 `[INFO] 已请求取消 …: Unknown tool`；异常走 `[WARN]` |
| 汇总有遗留计数 | 汇总块里能看到 leftover 相关信息 |
| `except: pass` | `grep` 结果贴出来，命中的都改成 `[WARN]` 输出 |

---

## 五、交付报告必须回答

1. 改完后跑一次完整 selftest，把**尾部 15 行**（含汇总与遗留检查）贴出来。
2. 跑完后 `GET /api/review/running_task` 的原始返回是什么？
3. `grep -n "except: *pass" mcp_server/*.py` 的输出是什么？改了几处？
4. 你用的 HTTP 清理是怎么绕代理的？贴那几行。
