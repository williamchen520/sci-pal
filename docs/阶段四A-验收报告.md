# 阶段四-A 验收报告（服务常驻守护）

> 验收对象：CodeBuddy 提交 `f017b54`
> 「V33.17: 阶段四A 新增 SciPal 服务常驻守护（watchdog + 自启脚本 + 工具侧提示）」
> 验收人：WorkBuddy　验收时间：2026-10-24 16:30 – 16:36
> 结论：**功能闭环成立，予以通过**；另发现 4 项缺陷需修复（2 项必修、2 项建议）。

---

## 一、交付物核对

| 文件 | 大小 | 状态 |
|---|---|---|
| `scripts/sciPal_watchdog.py` | 7,860 B / 232 行 | ✅ 存在且可运行 |
| `scripts/install_autostart.ps1` | 2,230 B / 63 行 | ✅ 存在（纯 ASCII，未实装） |
| `scripts/uninstall_autostart.ps1` | 1,140 B / 37 行 | ✅ 存在 |
| `mcp_server/scipal_server.py` | +10 行（L3 提示文案） | ✅ 已按工单落地 |

`git show --stat f017b54` 确认 4 个文件全部入提交。L3 文案已改为指向 watchdog 脚本 +
「可能正在预热，等 30–45 秒后重试」，并明确注释「绝不在工具调用内同步等待服务启动」。

---

## 二、实测结果（全部通过）

### 1. 幂等性 —— 服务存活时不得重复拉起 ✅
```
[16:30:51] SciPal API 已在运行（http://127.0.0.1:5000），无需拉起   RC=0，耗时 2s
```
未产生任何新进程。

### 2. `--once` 拉起并计时 ✅
```
[16:31:21] SciPal API 未运行，正在拉起 api_server.py ...
[16:31:21] 已拉起 api_server.py（日志：D:\sciPal\logs\sciPal_api.log）
[16:31:52] 服务已就绪，实际耗时 31.3s（冷启动通常 30–45s）
```
31.3 秒就绪，与文档记录的 30–45 秒冷启动窗口一致。

### 3. 常驻守护自愈 —— 运行中杀掉服务 ✅
```
[16:32:01] watchdog 常驻启动：每 10s 探测 .../api/health（PID 3900）
[16:32:04] 服务不通 → 已拉起 → 进入 60s 冷却期
[16:32:16] 冷却期内（剩 48s），暂不重复拉起
[16:32:28] 冷却期内（剩 36s），暂不重复拉起
[16:32:38] 服务已恢复（http://127.0.0.1:5000）
   —— 以上为「启动即不通」场景，34s 恢复

[16:33:48] 人为 kill api_server（父 22828 + 子 21776）
[16:33:51] 服务不通 → 已拉起 → 进入 60s 冷却期        ← 检测延迟 3 秒（要求 ≤15s）
[16:34:26] 服务已恢复                                   ← 32s 恢复
```
检测延迟 **3 秒**（远优于 ≤15 秒要求）；冷却期内只报告、不重复拉起；恢复后日志安静
（存活时不重复拉起）。

### 4. 绕代理探测 ✅
`probe()` 使用 `urllib.request.build_opener(ProxyHandler({}))`。本机 `http_proxy`
存在时仍正确判定，未出现「服务活着被误判为没起」。

### 5. 回归检查 ✅

| 检查项 | 结果 | 基线 |
|---|---|---|
| `mcp_server/selftest.py` | **PASS**（5 工具齐全，health 返回真实响应） | PASS |
| `self_check.py` | 通过 **110** / 失败 **1** / 警告 2 / 跳过 8 / 总计 **121** | 110/1/121 |

**与基线完全一致，无回归。** 唯一失败项仍是历史遗留的
`abstracts.db: no such table: abstracts`（阶段四-A 未触碰，不在本次范围）。

---

## 三、发现的缺陷（按优先级）

### 🔴 P1（必修）`--once` 拉起的服务会随启动它的终端会话结束被回收

**证据**：`--once` 于 16:31:21 拉起、16:31:52 报「已就绪」，但该 Bash 调用结束后
进程即消失 —— 16:32:04 daemon 首轮探测时服务已死（进程列表中已无 api_server）。

**影响**：
- `--once` 的定位（「手工拉一次」）在交互式终端里**不成立**：拉起 → 报成功 → 会话结束即失效。
- L3 错误文案建议用户执行 `python scripts/sciPal_watchdog.py --once`，
  用户会得到「看着成功、实际活不下来」的结果。**这条提示当前是有误导性的。**

**原因**：`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` 不等于
`CREATE_BREAKAWAY_FROM_JOB`。子进程仍被父进程的 Job Object 捕获，终端会话结束即被回收。
（本项目此前已多次踩到「服务随 Bash 调用结束被杀」，本次是同一机制的又一例证。）

**修法建议**（任选，推荐 a+c）：
- a. `--once` 输出末尾追加提示：「本方式拉起的服务会随终端退出被回收；需要持久运行请执行
  `scripts/install_autostart.ps1` 安装计划任务」。
- b. 补 `CREATE_BREAKAWAY_FROM_JOB`（`0x01000000`）到 `creationflags`，并验证是否真能脱离。
- c. L3 文案把「安装计划任务」置于「跑 `--once`」之前，作为首选方案。

> 注：**daemon 模式不受此问题影响** —— 由 `run_in_background` 或计划任务启动时，
> 只要 daemon 自身存活，它拉起的服务就存活（已实测验证）。

---

### 🔴 P2（必修）自启计划任务有两个硬伤

**2a. `/RL HIGHEST` 需要管理员权限。**
非管理员执行会直接失败；而 watchdog 只是起本地 Flask，**不需要提权**。

**2b. `schtasks /Create` 默认带 3 天执行时限（ExecutionTimeLimit = P3D）。**
watchdog 是 `while True` 常驻循环，**运行满 3 天会被计划任务强制终止**，守护静默失效。

**修法建议**：
- `/RL` 改为 `LIMITED`（或直接省略）。
- 3 天限制无法用 `schtasks /Create` 的开关关闭，需改用 XML 导入或
  `Register-ScheduledTask` + `-Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero))`。
  即 XML 中设置 `<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>`。

---

### 🟡 P3（建议）锁文件只存 PID，PID 复用会导致守护静默拒启动

**证据**：`logs/sciPal_watchdog.lock` 内 PID `23148` —— 用 WMI 查询时该 PID
已被**完全无关的进程**（一个 `WorkBuddy.exe` renderer）占用。

**风险**：`acquire_lock()` 用 `tasklist` 只判断「该 PID 是否存在」。一旦陈旧锁里的
PID 被系统复用给任意进程，`pid_alive()` 返回 True，新 watchdog 会打印
「已有 watchdog 实例在运行」并退出 —— **守护彻底失效且不报错**。

**修法建议**：锁文件改为存 `PID + 进程创建时间`（用 WMI `CreationDate` 比对），
或校验该 PID 的命令行含 `sciPal_watchdog.py`；至少在日志里打印 holder 的进程名以便诊断。

---

### 🟡 P4（小）安装脚本可用性

- `install_autostart.ps1` 硬编码 `$ProjectRoot = "D:\sciPal"`（项目移动即失效）。
- `Read-Host` 会阻塞非交互执行 → 建议加 `-Force` 开关跳过确认。

---

## 四、验收期间新抓到的既有问题（属阶段四-B，本次不修）

`logs/sciPal_api.log` 启动段实拍：
```
🧪 Sci-Pal API V25.17 — http://0.0.0.0:5000
⚠️  数据库迁移跳过（不影响运行）: name 'sqlite3' is not defined
```
- banner 显示 **V25.17**，`/api/health` 返回 **V25.14**，而 `VERSION` 是 **V33.17**
  → 三处版本指针不一致（无守卫，全靠手改）。
- `run_db_migrations()` 缺少 `import sqlite3`（`api_server.py:1963` 处直接 `sqlite3.connect`）
  → 数据库迁移长期被跳过。这两项已列入阶段四-B。

---

## 五、当前环境状态（供后续操作参考）

- Flask 服务：**在线**（由本次验收启动的 daemon PID 3900 守护）。
- 该 daemon 是验收期间用后台任务起的，**会随本次会话结束被回收** —— 这正是 P1 的同一机制。
  需要真正持久运行，请执行 `scripts/install_autostart.ps1`（修完 P2 后再装更稳妥）。
- `~/.dsh/profiles/desktop/cordis.patch.yml` 本次未改动。
