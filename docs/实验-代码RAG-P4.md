# 实验记录：code-rag P4 DSH MCP

> 日期：2026-11-12  
> 状态：**MCP server 与 bundle 已加；未重启 DSH 做 GUI 验证**  
> 模块：`mcp_server/code_server.py`

---

## 1. 工具

```text
code_search(query, library_id, top_k, snapshot_id)
code_status(library_id)
code_trace(unit_id, library_id, direction, max_hops, max_nodes)
```

全部只读。

## 2. 服务

```text
serverName  scipal-code
transport   stdio
entry       mcp_server/code_server.py
```

不 import Flask，不连文献 API。

## 3. Bundle

`packages/dsh-scipal/cordis.patch.yml` 新增：

```text
mcp-scipal-code
serverName: scipal-code
SCIPAL_CODE_ENV_FILE: G:/runs/code_rag.env
failOnStartupError: false
```

DSN 不进 YAML；由本地 env 文件注入。

## 4. 工具 smoke

直接调用（不经过 DSH GUI）：

### code_status

```text
library_id lib_2c5709b07c77
```

### code_search

```text
query "normalize total counts"
top1 normalize_total
path src/scanpy/preprocessing/_normalization.py
```

### code_trace

```text
unit normalize_total
direction out
edges 9
```

调用链目标多为 `unresolved:`，因为 P2 还没有符号绑定。

## 5. 测试

```text
tests.test_code_rag_trace 2 passed
```

## 6. 尚未完成

```text
DSH 未重启，GUI 里还未验证 mcp__scipal-code__*
没有 code_render / bioviz_render
code_trace 的 calls 仍是 unresolved
没有 UI「我的代码库」
```

## 7. 下一步

```text
1. 重启 DSH，确认 38 个工具
2. 在 DSH 里跑 code_search / code_trace
3. 再决定 code_trace 的符号绑定
```
