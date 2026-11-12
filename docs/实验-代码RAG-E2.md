# 实验记录：code-rag E2 DSH-like 对照

> 日期：2026-11-13  
> 状态：**B1 grep+read 与 C1 code_search 已跑；不是完整 DSH 会话**  
> 数据：30 题，`eval/code_rag_stack/results/e2_dsh.json`

---

## 1. 本轮做了什么

```text
B1：git grep -c + read 前 3 个文件
C1：code_search top-10
```

工具调用与延迟写入 JSONL。

## 2. 为什么不是完整 DSH

```text
DSH 原生 grep 是 ripgrep
本次自动化用 git grep
没有多轮模型
没有 LSP
没有子 agent
```

所以：

```text
这是 grep-equivalent 基线
不是 B2 DSH 全工具
```

## 3. 结果

| 指标 | B1 git grep+read | C1 code_search |
|---|---:|---:|
| File Hit@1 | 0.133 | **0.700** |
| File Hit@3 | 0.467 | **0.967** |
| File Hit@5 | 0.467 | **1.000** |
| Symbol Hit@1 | — | **0.767** |
| Symbol Hit@5 | — | **1.000** |
| MRR | 0.311 | **0.831** |
| nDCG@10 | 0.365 | **0.874** |
| p50 latency | 629 ms | 1,079 ms |

## 4. 和 E0 lexical baseline 的差异

E0 baseline：

```text
按 file unit 文本 token 计数 + path 加权
Hit@1 0.300
```

E2 git grep：

```text
按匹配行数排序
Hit@1 0.133
```

说明：

```text
“grep baseline”不是一个东西
排序策略会显著改变结果
```

所以不能拿一个弱 grep 基线证明 RAG 很强。  
E2 只说明：

```text
在“按匹配行数排序”的 grep 下
code_search 明显更好
```

## 5. 延迟

```text
B1 p50 629 ms
C1 p50 1,079 ms
```

C1 慢约 1.7 倍，主要来自 embedding + 向量检索。  
对 30 题来说可接受，但还没有和 DSH 多轮成本比。

## 6. Gate 状态

```text
G0 L0        PASS（E0）
G1 L1        PASS vs grep-equivalent
G2 @5        PASS
G3 L2        未跑
G4 L3        未跑
G5 L4        未跑
G6 L5        未跑
```

## 7. 下一步 E3

```text
L2 上下文完整性
  20 题
  import_recall
  symbol_closure
  version_match
```

然后才做 L3/L4：

```text
compile_pass
test_pass@1
```

完整 DSH 对照（B2）必须在有 LSP/多轮实际会话时单独跑，不能由本脚本冒充。
