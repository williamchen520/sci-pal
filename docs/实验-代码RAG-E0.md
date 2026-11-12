# 实验记录：code-rag E0 评测脚手架与 L0 审计

> 日期：2026-11-12  
> 状态：**E0 harness 可跑；L0 100%；DSH 对照尚未开始**  
> 代码：`eval/code_rag_stack/`

---

## 1. E0 交付

```text
harness.py
  统一 arm：B1 / C1 / C2
  tool_calls 记录
  latency_ms
  JSONL 日志
  L1 汇总

l0_audit.py
  parse_ok
  span_exact
  delimiter_balance
  parent_ok
```

结果：

```text
eval/code_rag_stack/results/harness.json
eval/code_rag_stack/results/harness.jsonl
eval/code_rag_stack/results/l0.json
```

## 2. L0 发现的问题

第一次审计：

```text
parse_ok 0.757
span_exact 0.762
failure 626
```

原因：

```text
parser 把 docstring 拼到函数体前面
unit 文本不再是合法源码
```

修复：

```text
parse_python 只保留原始 AST span
重新灌入 scanpy / rnaseq
重新 resolve + embedding
```

第二次审计：

```text
total 2,578
parse_ok 1.000
span_exact 1.000
delimiter_balance 1.000
parent_ok 1.000
failure 0
```

说明：

```text
L0 不是“评出来的”
是修出来的
```

## 3. E0 harness 结果

30 题，三臂：

| 指标 | B1 grep+read | C1 code_search | C2 search+trace |
|---|---:|---:|---:|
| File Hit@1 | 0.300 | **0.700** | 0.700 |
| File Hit@3 | 0.600 | **0.967** | 0.967 |
| File Hit@5 | 0.800 | **1.000** | 1.000 |
| Symbol Hit@1 | — | **0.767** | 0.767 |
| Symbol Hit@5 | — | **1.000** | 1.000 |
| MRR | 0.511 | **0.831** | 0.831 |
| nDCG@10 | 0.608 | **0.874** | 0.874 |
| p50 latency | 25.5 ms | 1,020 ms | 2,196 ms |

解释：

```text
C2 不改变检索排名
只增加 trace 调用
所以 p50 从 1.0s 到 2.2s
```

## 4. 这不是 DSH 对照

当前 baseline 是：

```text
grep-like 文件词法扫描
+ read 前 3 个文件
```

不是：

```text
真实 DSH 会话
多轮
LSP
子 agent
```

E0 只证明：

```text
脚手架能计时/记工具/算 L1
```

不证明：

```text
code RAG 已优于 DSH
```

## 5. 当前 Gate

```text
G0 L0        PASS
G1 L1 code>baseline  PASS（但 baseline 是代理）
G2 @5 不降    PASS
G3 L2        未跑
G4 L3        未跑
G5 L4        未跑
G6 L5        未跑
```

## 6. 下一步

```text
E1 已完成（L0）
E2 需要真实 DSH 会话：
  B1 grep+read
  B2 DSH 全工具（LSP 可用才启用）
  C1/C2
```

不能再用 grep-like 代理冒充完整 DSH。
