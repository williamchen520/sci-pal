# 工作计划：DSH 适配与插件化

> 状态：待评审  
> 范围：第 5 项（DSH 只读工具、私有/公有入口、静态 token、插件 UI、输出闸门、写操作、离线分发）  
> 前置：第 3 项领域包、第 4 项多用户与数据分级。

## 1. 已确认决策

| 项 | 决策 |
|---|---|
| 第一版 | 只读 MCP |
| DSH UI | 第二阶段 |
| 输出 hook | 有则做，无则不做强保证 |
| 运行位置 | DSH 桌面端为主，服务器端兼容 |
| 私有数据 | 只允许本地/超算模型 |
| 认证 | 静态 token |
| 写操作 | 第二阶段 |
| 离线 bundle | 包含 SciPal + 集成包；DSH 本体视许可 |

## 2. 总体架构

```
DSH 桌面/服务器
   │ HTTPS / MCP
   ├─ scipal-public     data_class=public
   └─ scipal-private    data_class=internal/private/sealed
          │
       SciPal 服务
       ├─ 权限/workspace
       ├─ 数据分级
       ├─ 检索/证据
       ├─ 简报/项目/ELN
       └─ 审计
```

原则：

```
DSH 负责推理与入口
SciPal 负责数据、权限、证据、审计
```

## 3. 两个 MCP 入口

### public

- 只返回 `public`；
- 允许云端 DSH；
- token scope `data_class=public`；
- 不返回 private 元数据。

### private

- 可返回 `internal/private/sealed`；
- 只允许本地/超算模型；
- token scope `data_class=private`；
- 管理员/用户显式授权。

服务端强制，不依赖客户端声明。

## 4. 静态 token

### 生成

- SciPal Web 里生成；
- 绑定 user + workspace + data_class；
- 显示一次，之后只存 hash；
- 可命名、可撤销、可设过期。

### 使用

```http
Authorization: Bearer <token>
```

### scope

```yaml
scopes:
  - evidence:read
  - brief:read
  - project:read
  - answer:validate
```

### 安全

- 必须 TLS；
- token 不进 URL；
- DSH 本地加密保存；
- 定期轮换；
- 撤销立即生效；
- 审计每次调用。

### 限制

静态 token 是长期凭据：

- 泄露风险高于 OAuth；
- 第一版接受；
- 后续可升级 OIDC。

## 5. 只读工具

```text
scipal_search_evidence(query, top_k, data_class)
scipal_get_paper(paper_id)
scipal_get_brief(week)
scipal_get_project(project_id)
scipal_list_protocols(project_id)
scipal_validate_answer(answer, evidence_ids)
```

### search_evidence 返回

```json
{
  "evidence": [
    {
      "id": "P1",
      "paper_id": "...",
      "paragraph_id": "...",
      "sentence_ids": ["..."],
      "text": "...",
      "data_class": "public"
    }
  ],
  "sufficient": false,
  "allowed_citation_ids": ["P1"],
  "refusal_reason": "insufficient_evidence"
}
```

### 约束

- 不返回 token 无权访问的资源；
- 不返回其他 workspace；
- 不返回 private 元数据给 public token；
- 简报只返回本人；
- 项目只返回成员可见元数据；
- ELN 内容按 PI 请求/成员批准。

## 6. DSH 第一版

```
/scipal brief
→ 返回 Web URL
→ DSH 打开
```

- 不做卡片；
- 不做内嵌；
- 不做写操作；
- 只读。

## 7. DSH 第二阶段

- 侧边栏/卡片；
- 证据列表；
- 简报条目；
- 项目入口；
- 实验记录入口；
- 引用点击；
- 可选输出校验。

## 8. 输出闸门

如果 DSH 提供 hook：

```
answer
→ scipal_validate_answer
→ unknown ids
→ uncited claims
→ reject/rewrite
```

如果没有 hook：

```
不承诺最终答案
正式问答走 SciPal-first
```

不通过插件强行拦截 DSH 输出。

## 9. 写操作（第二阶段）

第一批：

```text
create_experiment_draft
add_note
create_brief_draft
link_paper
```

要求：

- 用户显式确认；
- 只写 draft；
- 不签名；
- 不删除；
- 不审批；
- 审计；
- 权限校验；
- 不能绕过 PI/成员规则。

## 10. 私有数据边界

```
public DSH + public token
→ public only

local/HPC DSH + private token
→ internal/private/sealed
```

服务端检查：

- token scope；
- workspace；
- data_class；
- 资源 ACL。

云端 DSH 即使拿到 private token，也应被管理员禁止；  
token 生成时限制 data_class。

## 11. 身份

第一版：

```
SciPal 账号
→ 生成静态 token
→ DSH 配置
```

后续：

```
OIDC / device flow
```

PI/成员权限仍由 SciPal 判定。

## 12. 离线 bundle

```
scipal-offline-<version>.tar.gz
├─ SciPal images
├─ DSH 集成包
├─ MCP 配置
├─ 领域包
├─ 本地模型配置
├─ checksums
└─ signatures
```

DSH 本体：

- 如果许可证允许，打包安装器；
- 否则提供安装说明和校验和；
- 不违反 DSH 分发许可。

## 13. 评测

对比：

| 配置 | 说明 |
|---|---|
| SciPal QA | 基线 |
| DSH + public MCP | 只读 |
| DSH + private MCP | 本地/超算 |
| DSH + validate | 强闸门 |

指标：

- answer coverage；
- citation validity；
- refusal；
- private leak = 0；
- tool latency；
- token 成本。

## 14. 分阶段

### P1：public 只读
- MCP server；
- static token；
- search/get paper；
- URL 简报；
- 审计。

### P2：private 只读
- private MCP；
- data_class；
- 本地/超算 DSH；
- 简报/项目工具。

### P3：DSH UI
- 卡片；
- 侧边栏；
- 引用点击。

### P4：validate hook
- 输出校验；
- 拒绝/重写。

### P5：写操作
- draft 实验/笔记/简报；
- 确认与审计。

### P6：离线 bundle
- 集成包；
- 签名；
- 安装脚本。

## 15. 验收

- public token 无法读 private；
- private token 只能本地/超算；
- 跨 workspace 拒绝；
- 简报只返回本人；
- PI 不能借 DSH 绕过请求；
- token 可撤销；
- 审计完整；
- 无私有数据出网；
- 离线可安装。

## 16. 风险

- 静态 token 泄露；
- DSH 模型位置不可验证；
- 云端 DSH 误用 private token；
- 插件输出无法强制；
- DSH 许可限制分发；
- MCP 协议变化；
- 工具调用放大权限。

## 17. 待确认

1. DSH 是否提供输出 hook？
2. DSH 桌面端是否能配置多个 MCP server？
3. 离线包是否允许包含 DSH 安装器？
4. private token 是否只允许管理员生成？
5. 是否需要 DSH 侧显示“数据等级”标识？
6. 写操作是否需要二次确认 UI？

## 18. 建议

```
P1 public 只读 MCP + URL
P2 private 只读 + 本地/超算
P3 DSH UI
P4 validate hook（有则做）
P5 写操作 draft
P6 离线 bundle
```

一句话：

> DSH 是入口和推理层；SciPal 用 token 和 MCP 控制“能看到什么”，不把权限交给 agent。
