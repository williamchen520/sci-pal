# 实验记录：SciPal 服务持久化

> 日期：2026-11-13  
> 状态：**Task Scheduler + Startup 已生效**  
> 目标：DSH 重启不影响 app / code API

---

## 1. 问题

之前 app 和 code API 用 DSH background job 启动，DSH 重启会把它们一起杀掉。

`Start-Process` 仍在 DSH Job Object 内，也会被杀。

## 2. 方案

Task Scheduler 运行 `cmd.exe`，cmd 前台等待 Python 服务：

```text
SciPalAppCmd
SciPalCodeApiCmd
```

脚本：

```text
G:\runs\start_scipal_app.cmd
G:\runs\start_code_api.cmd
```

关键：

```text
cmd -> python -> 前台阻塞
Task Scheduler 任务持续 Running
父进程树不经过 DSH
```

## 3. 防重复

cmd 开头：

```bat
netstat -ano | findstr /R /C:":5001 .*LISTENING" >nul
if not errorlevel 1 exit /b 0
```

code API 对应 5010。  
重复运行不会起第二份。

## 4. 登录自启

当前用户 Startup：

```text
SciPalApp.vbs
SciPalCodeApi.vbs
```

以隐藏窗口调用 cmd；登录后自动恢复。

## 5. 验证

进程树：

```text
python api_server.py
  parent cmd.exe
  grandparent svchost.exe
```

```text
python -m code_rag.api
  parent cmd.exe
  grandparent svchost.exe
```

Task：

```text
SciPalAppCmd      Running
SciPalCodeApiCmd  Running
Last Result       267009
```

活查询：

```text
rag_query evidence_search
-> literature
-> ev_12c617ba19af
```

## 6. 边界

```text
不是 Windows Service
依赖当前用户登录会话
任务是一次性任务 + Startup 自启
```

服务器长期部署仍建议 NSSM / Windows Service / systemd。

## 7. 结论

```text
DSH 重启不再带走 app/code API
```
