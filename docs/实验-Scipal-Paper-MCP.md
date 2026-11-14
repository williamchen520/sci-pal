# 实验记录：scipal-paper MCP 插件

> 日期：2026-11-14  
> 状态：MCP server 9 tools；薄转发；DSH 需重启加载  
> 目标：把单篇论文 API 暴露给 DSH

---

## 1. Server

```text
mcp_server/paper_server.py
serverName: scipal-paper
transport: stdio
```

铁律：

```text
不 import SciPal 内部模块
不加载 embedding / reranker
只调 Flask API
stdout 不打印
```

## 2. 工具（9）

```text
paper_health
paper_outline
paper_first_paragraph
paper_analysis
paper_evidence
paper_code_links
paper_code_libraries
paper_modules
paper_data_flow
```

## 3. 鉴权

MCP 进程不硬编码 token，加载：

```text
SCIPAL_API_ENV_FILE=G:/sciPal_deploy/deploy/.env
SCIPAL_CODE_ENV_FILE=G:/runs/code_rag.env
```

`_forward` 自动带：

```text
X-SCIPAL-Internal-Token
```

## 4. 配置

`packages/dsh-scipal/cordis.patch.yml` 新增：

```text
id: mcp-scipal-paper
serverName: scipal-paper
args: D:/sciPal/mcp_server/paper_server.py
SCIPAL_BASE_URL: http://127.0.0.1:5001
failOnStartupError: false
```

## 5. 验证

server 导入：

```text
server scipal-paper
tools 9
```

outline 工具真实调用：

```text
paper_outline(...)
-> 200
-> sections
```

## 6. 边界

```text
DSH 不重启不会出现 mcp__scipal-paper__*
Flask 不重启，新路由可能 404
插件只读，不下载/执行
```

## 7. 下一步

```text
1. 重启 app + DSH
2. 端到端 paper_analysis
3. module purpose
```
