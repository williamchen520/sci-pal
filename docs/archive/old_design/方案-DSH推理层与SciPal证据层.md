# 方案：DSH 作为推理层，SciPal 作为证据层

> 状态：待评审  
> 目标：明确 DSH 与 SciPal 的职责边界，避免“用插件约束 DSH”这种不可靠架构。

## 1. 背景

当前两条路线：

1. SciPal 自己接大模型：可控，但需要 API key / 本地大模型；
2. DSH 承担推理：推理强，但 SciPal 失去最终输出控制。

问题不在于“能不能接”，而在于：

```
谁对最终答案的可信度负责？
```

如果 DSH 是自主 agent，SciPal 插件无法保证它：

- 一定调用 SciPal 工具；
- 一定引用真实 evidence ID；
- 一定在证据不足时拒答；
- 一定不使用参数知识。

所以不能把“约束 DSH”作为架构前提。

## 2. 目标与非目标

### 目标
- DSH 负责推理与编排；
- SciPal 负责检索、证据、引用契约；
- 最终输出可验证、可拒绝、可替换；
- 保留 SciPal 独立部署能力。

### 非目标
- 不试图控制 DSH 的思考过程；
- 不依赖 prompt 保证引用；
- 不把 DSH 当成 OpenAI 兼容 API；
- 不在没有校验的情况下宣称“严格证据回答”。

## 3. 三种架构

### 方案 A：DSH-first

```
DSH agent
  → SciPal tools
  → 直接回答
```

- 优点：体验好、推理强；
- 缺点：SciPal 无法兜底；
- 定位：探索型研究助手。

### 方案 B：SciPal-first

```
SciPal
  → 单次调用 DSH 模型
  → SciPal 校验
  → 最终回答
```

- 优点：引用/拒答可硬保证；
- 缺点：需要 DSH 提供单次模型调用，而不是 agent；
- 定位：正式科研问答、可审计场景。

### 方案 C：Hybrid（推荐）

```
DSH 生成 draft
  → SciPal validate
  → 通过：返回
  → 不通过：拒答 / 重写一次 / 只返回证据
```

- DSH 负责推理；
- SciPal 负责最终闸门；
- 不要求 DSH 被“约束”，只要求输出可被拒绝。

## 4. 决策矩阵

| 维度 | A DSH-first | B SciPal-first | C Hybrid |
|---|---|---|---|
| 推理能力 | 强 | 取决于模型调用 | 强 |
| 引用保证 | 弱 | 强 | 强 |
| 拒答保证 | 弱 | 强 | 强 |
| 实现成本 | 低 | 中 | 中 |
| 可审计 | 弱 | 强 | 强 |
| 适合正式场景 | 否 | 是 | 是 |

## 5. 权威边界

核心原则：

```
DSH 的输出是 draft，不是 final answer
```

SciPal 只对以下内容负责：

- 给了哪些证据；
- 证据 ID 是否真实；
- 回答是否引用真实证据；
- 证据不足时是否拒答。

SciPal 不对以下内容负责：

- DSH 的推理过程；
- DSH 是否使用其他工具；
- DSH 的模型版本与温度。

## 6. 工具契约

### 6.1 Evidence 工具

```json
{
  "query": "...",
  "evidence": [
    {
      "id": "P1",
      "paper_id": "...",
      "paragraph_id": "...",
      "sentence_ids": ["..."],
      "section_path": ["...", "..."],
      "text": "..."
    }
  ],
  "sufficient": false,
  "allowed_citation_ids": ["P1", "P2"],
  "refusal_reason": "insufficient_evidence"
}
```

约束：

- 只返回 SciPal 库内证据；
- ID 稳定；
- `allowed_citation_ids` 与 evidence 一致；
- 注入内容标记为 untrusted。

### 6.2 校验工具

```json
{
  "answer": "...",
  "allowed_ids": ["P1", "P2"],
  "sufficient": false
}
```

返回：

```json
{
  "ok": false,
  "unknown_ids": ["P9"],
  "uncited_claims": ["..."],
  "quote_mismatch": ["..."],
  "refusal_required": true
}
```

## 7. 输出闸门

校验规则：

1. 引用 ID 必须存在；
2. 事实句必须有引用；
3. 引文必须能在 evidence 中找到；
4. `sufficient=false` 且未拒答 → 拒绝；
5. 可选：语义 grounding。

失败处理：

```
拒绝
或 只返回 evidence
或 让 DSH 重写一次
```

## 8. 插件能做什么、不能做什么

### 能做
- 限制工具集合；
- 只暴露受控 evidence；
- 提供 validator；
- 提供 prompt/skill；
- 领域过滤；
- 记录日志。

### 不能保证
- DSH 一定调用 validator；
- DSH 一定不用参数知识；
- DSH 一定引用真实 ID；
- DSH 一定拒答。

因此：

> 插件用于“约束输入 + 提供校验”，不用于“保证输出”。

## 9. 评测

同一套 gold，比较：

| 配置 | 说明 |
|---|---|
| SciPal 本地 QA | 当前基线 |
| DSH-first | 只看 draft |
| Hybrid | DSH draft + SciPal gate |

指标：

- answer coverage；
- citation precision / recall；
- unsupported claim rate；
- refusal accuracy；
- latency；
- tool calls / tokens；
- 人工抽检。

## 10. 分阶段

### P0：工具契约
- `scipal_search_evidence`；
- `scipal_validate_answer`；
- 不接 DSH。

### P1：DSH 只读接入
- DSH 配置 MCP；
- prompt/skill；
- 10 题 smoke test。

### P2：Hybrid 闸门
- DSH draft；
- SciPal 校验；
- 失败拒答/重写。

### P3：评测与决策
- 30/100 题；
- 对比 A/B/C；
- 决定正式模式。

## 11. 风险

- DSH 无输出 hook，Hybrid 只能靠外层包装；
- DSH 多轮调用导致延迟；
- 证据过长挤占上下文；
- 校验误杀正常改写；
- 领域/语料范围不一致；
- 模型版本不可复现。

## 12. 待确认问题

1. DSH 是否提供输出 hook / 单次模型调用？
2. DSH 是否允许限制工具白名单？
3. 正式场景是否要求“硬拒答”？
4. 数据是否允许离开本机？
5. 是否接受“DSH draft + SciPal gate”的产品形态？

## 13. 建议

推荐 **方案 C：Hybrid**。

一句话：

> DSH 负责推理，SciPal 负责证据与闸门；  
> 不追求约束 DSH，只追求输出可验证、可拒绝、可替换。
