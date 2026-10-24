# 阶段四-A 修订验收报告（P1–P4 修复）

> 验收对象：CodeBuddy 针对 [`阶段四A-验收报告.md`](./阶段四A-验收报告.md) 第三节缺陷清单的修复
> 验收人：WorkBuddy　验收时间：2026-10-24 16:46 – 16:57
> 改动文件（**截至验收时尚未提交，工作区 `M` 状态**）：
> `scripts/sciPal_watchdog.py` (+209/-40)、`scripts/install_autostart.ps1` (+87/-35)、
> `mcp_server/scipal_server.py` (+5/-3)

## 结论速览

| 项 | 结论 | 判定依据 |
|---|---|---|
| **P1** `--once` 拉起被会话回收 | ⚠️ **部分通过** | 提示与代码层面已修；**行为层面未修**（实测两次均被回收） |
| **P2** 计划任务提权 + 3 天时限 | ✅ **通过** | 静态审查 + 语法解析 + 逻辑核对（未实装） |
| **P3** 锁 PID 复用误判 | ✅ **通过** | 单元级 6 项 + 端到端陈旧锁接管实测 |
| **P4** 脚本硬编码 + 交互阻塞 | ✅ **通过** | 路径改为推导、新增 `-Force` |
| 回归 | ✅ **无回归** | `selftest.py` PASS；`self_check.py` 110/1/121 与基线一致 |

---

## 一、P1 —— 部分通过（行为层面未修复）

### 已修复的部分 ✅
- `launch()` 新增 `CREATE_BREAKAWAY_FROM_JOB (0x01000000)`，且**失败自动降级**为普通 detached
  （捕获 `OSError`，日志打印 `winerror`）。实测日志均为 `breakaway=已启用`，未触发降级。
- 新增 `ONCE_EPILOGUE`，`run_once()` 的**四条返回路径**（已在运行 / 拉起失败 / 成功 / 超时）全部打印：
  ```
  提示：本方式拉起的服务会随终端退出被回收，持久运行请装计划任务：
        powershell -File scripts/install_autostart.ps1
  ```
- `--once` 的 `--help` 改为「临时应急，非持久」；模块 docstring 新增「⚠️ 重要区别」章节。
- `scipal_server.py` 的 `_not_running_error()` 文案：**「安装计划任务」提到首选**，`--once` 降级为
  「临时应急（服务会随终端退出被回收，非持久）」。→ **上一轮报告的「误导性」问题已消除。**

### 未修复的部分 ❌
**两次实测，`--once` 拉起的服务仍然随前台 Bash 调用结束被回收：**

| 轮次 | 拉起时刻 | 就绪 | 跨调用检查 | 结果 |
|---|---|---|---|---|
| 1 | 16:47:58 | 16:48:30（31.8s） | 16:48:39（隔 9s） | **服务已消失，进程全无** |
| 2 | 16:49:07 | 16:49:39（31.8s） | 16:49:55（隔 8s） | **服务已消失，进程全无** |

尽管日志显示 `breakaway=已启用`（说明 `CreateProcess` 确实接受了该标志、未降级）。

### 原因分析（供后续决策）
`CREATE_BREAKAWAY_FROM_JOB` 只让子进程**脱离 Job Object**，**不改变父子进程链**。
宿主环境（Bash 工具）在调用结束时按**后代进程树**清理，因此仍然会杀到它。
→ 这是**宿主环境的进程回收机制决定的，不是 watchdog 代码能解决的**。
对照组：`run_in_background` 启动的 daemon 拉起的服务**可以存活**（实测存活 12 分钟以上）。

### 处置建议（可视为验收通过的前提）
- 该限制现已被代码与文案**显式声明**（docstring / epilogue / 工具错误文案 / `--help` 四处），
  用户不会再被误导 → **建议按「已知限制」关闭，不再修**。
- 真正持久运行**只能走计划任务**（L1）。若后续要彻底解决，方向是让拉起动作发生在
  **完全独立的会话**（计划任务 / 服务），而非任何终端子进程。

---

## 二、P2 —— 通过 ✅（未实装）

`install_autostart.ps1` 由 `schtasks` 改为 `Register-ScheduledTask`：

| 原缺陷 | 修复 |
|---|---|
| `/RL HIGHEST` 需管理员 | `-RunLevel Limited`（`New-ScheduledTaskPrincipal`） |
| `schtasks` 默认 3 天时限会杀常驻 | `-ExecutionTimeLimit ([TimeSpan]::Zero)` → `PT0S` |
| 硬编码 `D:\sciPal` | 由 `$MyInvocation.MyCommand.Path` 推导（同时修 P4） |
| `Read-Host` 阻塞非交互 | 新增 `param([switch]$Force)`（同时修 P4） |

额外加固：`-AllowStartIfOnBatteries` / `-DontStopIfGoingOnBatteries` / `-StartWhenAvailable` /
`-MultipleInstances IgnoreNew` / `-RestartCount 3` / `-RestartInterval 1m`；注册后**回读并打印**
`RunLevel` 与 `ExecutionTimeLimit` 便于自检；失败时给出 `schtasks` 兜底命令。

- PowerShell 语法解析：**两个脚本均 0 错误**（只解析不执行）。
- ⚠️ **未实际安装计划任务**——那会修改系统状态，需用户决定后自行执行
  （`powershell -File scripts/install_autostart.ps1`）。

---

## 三、P3 —— 通过 ✅（端到端实测）

锁由「纯 PID」升级为 `{"pid": …, "start": …}`，用 ctypes 调 `kernel32.GetProcessTimes`
取进程创建时间（FILETIME）比对。

### 单元级（临时脚本，已删除）
| 场景 | 期望 | 实测 |
|---|---|---|
| A 同 PID + 正确 start | True | **True** |
| B 同 PID + **伪造** start（模拟 PID 复用） | False | **False** ✅ 核心 |
| C 不存在的 PID | False | **False** |
| D 旧格式纯数字锁 | 兼容读出 | **`{'pid':999999,'start':None}`** |
| E start 缺失 → 回退命令行校验（非 watchdog） | False | **False** |
| F JSON 格式 | 正常读出 | **正常** |

### 端到端
1. **第二实例被挡住**：已有 daemon（PID 24312）时再启动 →
   `已有 watchdog 实例在运行（PID 24312），本实例退出以避免重复拉起` ✅
2. **陈旧锁被接管**：写入伪造锁 `{pid: 8556(explorer, 存活), start: 123456(伪造)}` 后启动 →
   ```
   [16:53:25] 发现过期锁（PID 8556 已不存在或已被复用），接管
   [16:53:25] watchdog 常驻启动：每 10s 探测（PID 8280）
   ```
   锁被重写为新实例 JSON ✅ **上一轮 P3 风险已消除**
3. 锁文件实拍（43 字节）：`{"pid": 8280, "start": 134373056049206012}` ✅

---

## 四、P4 —— 通过 ✅
路径由脚本位置推导；`-Force` 开关可用（`-Force` 时跳过确认）。
`uninstall_autostart.ps1` 未改动，语法解析 OK。

---

## 五、回归 ✅
| 检查 | 结果 | 基线 |
|---|---|---|
| `mcp_server/selftest.py` | **PASS**（5 工具齐全，真实 Flask 响应） | PASS |
| `self_check.py` | **通过 110 / 失败 1 / 警告 2 / 跳过 8 / 总计 121** | 110/1/121 |

唯一失败仍是历史遗留 `abstracts.db: no such table: abstracts`。
守护自愈复测：16:54:59 kill → **16:55:05 检测并拉起（6 秒）** → 16:55:39 恢复 ✅

---

## 六、遗留与建议（不阻塞验收）

1. **P1 行为层未修** → 按「已知限制」记录在案（见第一节处置建议）。
2. `launch()` 降级路径存在轻微句柄泄漏：`breakaway` 失败时 `continue` 前未关闭第一次
   `open(API_LOG)` 的句柄。仅在该分支触发（本机未触发），影响很小，可选修。
3. `command_line_has_watchdog()` 会起一次 PowerShell（`timeout=15`），仅在拿不到进程创建时间时
   作为回退；本机未触发，无性能影响。
4. **`install_autostart.ps1` 未实装验证**（需修改系统状态）。建议用户择机执行并回读
   `Get-ScheduledTask` 确认 `RunLevel=Limited`、`ExecutionTimeLimit=PT0S`。
5. 阶段四-B 待修项仍在：版本指针三处不一致（banner `V25.17` / `/api/health` `V25.14` /
   `VERSION` `V33.17`）；`run_db_migrations()` 缺 `import sqlite3`（日志实证「数据库迁移跳过」）。

---

## 七、当前环境状态
- 本次验收启动的守护仍在后台运行（PID 8280），**会随本次会话结束被回收**（P1 同一机制）。
- 三个修改文件**尚未提交**，需 CodeBuddy 或用户点名后提交。
