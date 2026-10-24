# 阶段五-B 验收报告（MCP 服务器按业务流拆分）

> 验收方：WorkBuddy　执行方：CodeBuddy　验收时间：2026-10-24 20:40
> 工单：`docs/工单-阶段五B-服务器拆分.md`（`eac86e2` + `c92ec21`）
> 依据：工单第九节「交接与验收」列的 5 项证据，逐项独立跑过，不采信交付报告自述。

---

## 一、结论速览

**判定：条件通过（代码质量合格，三项缺陷，其中两项已由验收方就地修正，一项待办）**

| 项 | 结论 |
|---|---|
| B-1 `_forward.py` 公共层 | ✅ 逻辑与 `scipal_server.py` 逐字一致，无行为改动 |
| B-2 `search_server.py`（6 工具） | ✅ 参数名与路由逐一核对正确 |
| B-3 `generate_server.py`（6 工具） | ✅ 只读+轮询，未越界做生成 |
| B-4 `selftest.py` | ✅ 3 server / 20 断言 / 20 PASS，逐工具 PASS/FAIL |
| B-5 bundle patch | ✅ 三条全在 `insert:` 块内，env / venv python / failOnStartupError 全对 |
| B-6 文档同步 | ⚠️ **有回归**（见 D-3），已修正 |
| 薄转发铁律 | ✅ 无 `from services`、无项目根 sys.path、无 stdout 打印、未动业务代码 |
| 提交 | ❌ **未提交**（全部留在工作区），见 D-1 |

---

## 二、通过项（独立实测证据）

### 2.1 `precheck_dsh_bundle.py`（我自己跑的，退出码 0）

```
[PASS] 无顶层 - id: 条目（必须包在 insert: 内）
[PASS] insert 块内至少有 1 个条目 —— 共 3 条
[PASS] [mcp-scipalhello]  serverName 合法 —— scipalhello
[PASS] [mcp-scipal-search]  serverName 合法 —— scipal-search
[PASS] [mcp-scipal-generate] serverName 合法 —— scipal-generate
[PASS] 无 serverName 冲突
退出码: 0
```

### 2.2 `mcp_server/selftest.py`（真实起进程 + 真实 HTTP，Flask 在线）

```
[server] scipal (legacy, 回退入口)   5 个工具  5/5 PASS
[server] scipal-search              6 个工具  6/6 PASS
[server] scipal-generate            6 个工具  6/6 PASS
断言总数 20 / PASS 20 / FAIL 0 / RESULT PASS
```

返回码分布合理：`health` 200；`search_hybrid` / `search_online` / `list_saved_outlines` /
`paper_citation_graph` 200；不存在的 id 返 404；空 `pmc_ids` 返 400。
**业务性 400/404 不是失败**，只证明链路通、参数对。

### 2.3 参数名逐条对照（我查的是 `api_server.py` 的 handler，不是文档）

| 工具 | 路由实读参数 | 工具转发 | 结论 |
|---|---|---|---|
| `search_hybrid` | `q` / `top_k` / `use_online` | `q`（对外叫 `query`） | ✅ 映射正确 |
| `search_online` | `q` / `max_results` / `search_pubmed` / `search_pmc` | 一致 | ✅ |
| `download_online_papers` | `pmc_ids`（返回 task_id） | 一致 | ✅ |
| `paper_citation_graph` | `relation` / `direction` / `max_hops`(≤3) / `max_total` | 一致，且做了 `1..3` 钳制 | ✅ |
| `get_abstract`（legacy） | 按 **PMID** 查 | description 已写明 | ✅ |

### 2.4 薄转发铁律

```
grep "from services|import api_server|PROJECT_ROOT" → 仅 _forward.py 注释里出现（非代码）
sys.path.insert → 只在两个 server 文件里插自己的目录（mcp_server/），未注入项目根
grep "print(" → 三个文件零命中（stdio 通道干净）
git status → api_server.py / services/ 零改动
```

---

## 三、缺陷

### D-1 ❌ 未提交（工单第九节明确要求提交）

`git log origin/dev..HEAD` 为空；全部改动留在工作区（5 个 modified + 3 个 untracked）。
按约定（CodeBuddy 提交、用户点名推送），这一项需退回补做，或由用户授权验收方代提。

### D-2 ✅ 已由验收方修正：工具总数写成 17（实际 13）

原始写法在 4 处出现：`cordis.patch.yml:77`、`README.md:101`、`README.md:136`、`INSTALL.md:79`。

**根因**：把 legacy server 的 5 个工具也算进了挂载数 → `5 + 6 + 6 = 17`。
但旧 `mcp-server`（`serverName: scipal`）条目**已按工单删除**，不挂载；真实挂载数 = 哨兵 1 + search 6 + generate 6 = **13**。
`selftest.py` 跑 3 个文件、断言 20 项，**那是自检覆盖，不是挂载数**。

已全部改为 13，并在 INSTALL/README 补了一句「为什么不是 17」，防止下次再算错。

### D-3 ⚠️ 已由验收方修正：`INSTALL.md` 回退成已作废的 `plugin_manager` 路线（回归）

CodeBuddy 重写 `INSTALL.md` 时，把上一轮实测推翻的内容**又写回来了**：

| 丢失的内容 | 现状 |
|---|---|
| 步骤 0.5「Full access ≠ `plugin_manager` 可用」（`tool-plugin-manager` 只在创造模式启用） | 整节消失，`grep "Full access"` = 0 命中 |
| 步骤 0.7「重启验伪」（旧进程残留会把旧 patch 挂成活跃 MCP） | 整节消失 |
| 步骤 1/2 = 桌面插件页填本地目录 → `Installed` → `Enable now`（唯一实测走通的路径） | **被改回** `plugin_manager install_bundle` |

按原样保留会直接误导用户去走一条本机根本走不通的路（实测 `plugin_manager` / `cordis_inspect_*` 全部 `unknown tool`）。
已整段恢复，且保留 CodeBuddy 新写的 4.2 进程数判据 / 4.3 分层诊断（这两节是对的）。

### D-4（nitpick）patch 顶部注释与条目自相矛盾

第 2 条铁律原文写「`failOnStartupError: true`」，但三个条目实际是 `true`（哨兵）/ `false`（两个业务 server）。
照注释改会把哨兵一起拖没。已改为按条目说明取值理由。

---

## 四、验收方复跑的结果（修完之后）

```
precheck_dsh_bundle.py  → 退出码 0，3 条 insert，无 serverName 冲突
grep "17 个"            → 0 命中
selftest.py             → 20/20 PASS（未受文档修改影响）
```

---

## 五、待办（按顺序；第 1–3 项已完成，见第六节）

1. **提交**（D-1）：显式列路径，别 `git add -A`（仓库里有别人的 `_test_v3317b.py`）；
   `tests/backups/` 下两份新备份（`20261024-203750.bak` / `-204144.bak`，均 916 B）按既往惯例一并入库。
2. **用户操作**：完全退出 DSH → 重启（改的是 bundle 层 patch，link 安装不用重装）。
3. **重启后复验（WorkBuddy 接手）**：
   - 进程层：命令行含 `mcp_` 的 `python.exe` 从 **4 → 6**（3 条命令 × 2 层进程）；
   - 工具层：会话里应见 **13 个** `mcp__` 工具；
   - 功能层：`mcp__scipal-search__health` 与 `mcp__scipal-generate__health` 都应 200；
     旧名 `mcp__scipal__*` 应**全部消失**（这是「删旧挂新」是否真正生效的判据）。
4. **阶段五-C（需用户点头）**：异步化端点（`POST /api/review/generate_async` 等 + 写入
   `services/task_manager` 的 job 句柄），把综述生成 / 大纲 / 多跳提问 / 问答
   真正接进 MCP。属**业务代码改动**，不在五-B 范围。

---

## 六、实机验收：**通过**（2026-10-24 21:01，重启后进程层复核）

用户在 DSH 完全重启后（新实例 `DeepSeek Harness.exe` 20:58:54–57 启动）复报工具清单，
验收方独立从进程层核对，三项判据全部命中：

| 判据 | 期望 | 实测 |
|---|---|---|
| 含 `mcp_` 的 `python.exe` 进程数 | 4 → **6** | **6** ✅ |
| 命令构成 | 3 条（哨兵 + search + generate） | `mcp_ping_server.py` / `search_server.py` / `generate_server.py` ✅ |
| 旧 `scipal_server.py` 进程 | 必须为 **0** | **0**（运行态已彻底摘除）✅ |
| 工具数 | **13** | 1 + 6 + 6 = 13 ✅ |
| 旧名 `mcp__scipal__*` | 全部消失 | 全部消失 ✅ |
| 两个新 server 的 `health` | 200 / `status: ok` / V33.17 | 均 200 ✅ |

进程层原始证据（父进程 `24844` = 重启后的 DeepSeek Harness）：

```text
20:59:08  24448  mcp_ping_server.py      PARENT=24844   ← 哨兵
20:59:08  15128  search_server.py        PARENT=24844   ← scipal-search
20:59:08  18256  generate_server.py      PARENT=24844   ← scipal-generate
20:59:09  18524  mcp_ping_server.py      PARENT=24448   ← venv 启动器 fork 的 worker
20:59:09   2364  search_server.py        PARENT=15128
20:59:09  23820  generate_server.py      PARENT=18256
→ 3 条命令 / 6 个 python 进程，无 scipal_server.py
```

**结论：阶段五-B 端到端验收通过。** 「删旧挂新」确实生效 —— 判据不是「新工具出现了」，
而是「旧工具彻底消失且旧进程为 0」，这一点比工具清单更能排除「新旧并存」。

> 一个过程教训：用户第一次反馈「旧工具还在、新工具 0 个」时，验收方查进程发现
> `DeepSeek Harness.exe` 仍是半小时前那批 PID —— **关窗口 ≠ 退出**（Electron 进托盘）。
> 因此「`mcp__scipal__health` 还能调」应直接判为**旧配置仍在运行**，
> 而不是「新配置挂载失败」。
