# 代码 RAG 评测栈与 DSH 对照计划 v1

> 日期：2026-11-12  
> 状态：计划，不写实现  
> 目标：把“检索正确、上下文完整、代码能跑、补丁能过”拆开评  
> 对照：DSH 原生 grep/read/多轮；LSP 可用时单列  
> 不把文献 RAG 的 SciFact 数字拿来横比

---

## 1. 结论先行

```text
代码 RAG 没有一个“总准确率”
必须分五层评
```

```text
L0 结构有效性
L1 检索质量
L2 上下文完整性
L3 编译
L4 执行
L5 补丁
```

三条用户常说的标准，归位如下：

| 说法 | 实际层级 | 性质 |
|---|---|---|
| AST 边界完整率 | L0 | 索引硬门禁 |
| 依赖闭合率 | L2 | 上下文完整性 |
| 编译/执行 Pass@1 | L3/L4 | 生成/修复指标 |

公开工作参考：

- [CodeRAG-Bench](https://arxiv.org/abs/2406.14497)：检索增强代码生成
- [RepoBench](https://arxiv.org/abs/2306.03091)：仓库级检索/补全
- [cAST](https://aclanthology.org/2025.findings-emnlp.430/)：AST 结构化 chunk
- [ASTChunk](https://github.com/yilinjz/astchunk)：AST chunk 工具
- [HumanEval](https://arxiv.org/abs/2107.03374)：pass@k
- [SWE-bench](https://arxiv.org/abs/2310.06770)：resolved

这些项目支持“要按结构切、要能执行”，但没有把三者并列为统一三标准。

---

## 2. L0：结构有效性

### 2.1 指标

| 指标 | 定义 | 门槛 |
|---|---|---:|
| `parse_ok` | parser 无 error 节点 | 100% |
| `span_exact` | unit 起止等于 AST 节点 | ≥99% |
| `delimiter_balance` | 括号/引号/缩进闭合 | 100% |
| `unit_type_ok` | function/class/process/config 正确 | ≥99% |
| `parent_ok` | 父子 unit 关系存在 | ≥99% |

### 2.2 规则

```text
L0 不通过 -> 不进入索引
不参与 L1 排名
```

“半个 if-else 直接 0 分”作为**硬门禁**成立；  
但不要把它叫“检索准确率”。

### 2.3 语言差异

```text
Python      缩进 + AST
C/Java      括号 + AST
YAML        层级 + key block
Nextflow    process/workflow block
```

不能用一个“缩进正确率”跨语言统一。

---

## 3. L1：检索质量

### 3.1 单元

```text
file
symbol（function/class/process）
evidence（path + line + symbol）
```

### 3.2 指标

```text
File Hit@1/3/5
Symbol Hit@1/3/5
Evidence Recall@5/10
MRR
nDCG@10
```

### 3.3 说明

```text
L1 只回答“找没找到”
不回答“代码能不能跑”
```

P6 已做 30 题：

```text
File Hit@1 0.700
File Hit@5 1.000
Symbol Hit@1 0.733
baseline File Hit@1 0.300
```

但 baseline 只是 grep-like 代理，不是完整 DSH 对照。

---

## 4. L2：上下文完整性

### 4.1 指标

```text
import_recall       必要 import 是否齐
symbol_closure      调用符号是否有定义
version_match       版本是否匹配
env_closure         容器/依赖/reference 是否匹配
```

### 4.2 重要边界

```text
不是“每个 chunk 必须带全部 import”
而是“返回的证据包是否闭合”
```

上下文包：

```text
目标 unit
+ 直接依赖
+ 必要 import
+ 版本/环境
```

### 4.3 生信扩展

```text
process input/output
container
reference genome
config
samplesheet
```

### 4.4 门槛

第一版：

```text
import_recall ≥ 0.90
symbol_closure ≥ 0.85
version_match = 1.00（有版本约束时）
```

---

## 5. L3：编译

### 5.1 指标

```text
compile_pass
import_pass
syntax_pass
```

### 5.2 范围

只对**可执行子集**评，不要求全部 recipe/repo 可编译。

```text
Python 单文件/函数
Nextflow -stub / config parse
```

### 5.3 门槛

```text
compile_pass ≥ 0.95
```

失败样本必须保存：

```text
unit_id
command
exit_code
stderr
env_hash
```

---

## 6. L4：执行

### 6.1 指标

```text
test_pass@1
SWE-bench resolved
recipe render_success
```

### 6.2 只对生成/修复任务

```text
检索本身没有 Pass@1
```

Pass@1 需要：

```text
任务
候选代码
测试
环境
```

### 6.3 门槛

```text
执行子集 test_pass@1 ≥ 0.80
```

低于此值：

```text
不把“能跑”作为 code RAG 的卖点
```

---

## 7. L5：补丁

### 7.1 指标

```text
patch_apply
test_pass
regression_pass
```

### 7.2 范围

v1 只做 5 个受控任务，不做自动合并。

```text
RAG 只提供证据
patch 由 DSH/人完成
```

---

## 8. DSH 对照组（不能漏）

### 8.1 先说实话

DSH 当前工具面以：

```text
grep / glob / read
多轮
子 agent
```

为主。  
**LSP 是否可用要按实际工具面记录**；没有 LSP 就不要写成“DSH+LSP”。

### 8.2 对照臂

| 臂 | 工具 | 轮数 | 说明 |
|---|---|---:|---|
| B0 | grep 一次 | 1 | 最弱基线 |
| B1 | grep + read | ≤5 | DSH 原生主基线 |
| B2 | DSH 全工具 | ≤10 | 有 LSP/子 agent 才启用 |
| C1 | code_search 一次 | 1 | RAG 检索 |
| C2 | code_search + code_trace | ≤3 | 图扩展 |
| C3 | code_search + trace + read | ≤5 | 完整证据包 |

### 8.3 控制变量

```text
同一模型
同一 temperature
同一 token/time 上限
同一 repo/commit
同一问题集
同一评分脚本
```

### 8.4 公平性

```text
B1 也允许 read 实际文件
C3 也允许 read 实际文件
差别只在“有没有 code_search/code_trace”
```

不能出现：

```text
RAG 臂可以读文件
DSH 臂只允许 grep 一次
```

### 8.5 分开报

```text
检索：B1 vs C1/C2
端到端回答：B1 vs C3（同一 LLM）
执行：只在 L4 子集报
```

### 8.6 DSH 的优势

```text
当前仓库永远读最新
多轮可追
子 agent 可并行
不需要索引
```

所以评测必须包含：

```text
当前工作区问题
外部 repo 问题
跨文件问题
版本问题
```

否则会低估 DSH。

---

## 9. 问题集

### 9.1 规模

```text
60 题
```

| 类型 | 数量 |
|---|---:|
| 符号定位 | 20 |
| 调用链/数据流 | 15 |
| workflow/config | 10 |
| 版本/API | 8 |
| 报错/测试 | 7 |

### 9.2 来源

```text
30 题：现有 P6
30 题：真实 DSH 会话记录
```

禁止：

```text
全部手写
query 与 symbol 同名
先看检索结果再改题
```

### 9.3 Gold

```text
repo_id
commit_sha
path
symbol
start_line/end_line
expected_relation（可选）
```

---

## 10. 实验阶段

| 阶段 | 工作 | 产出 | 人日 |
|---|---|---|---:|
| E0 | 日志/计时/评分脚手架 | harness | 2 |
| E1 | L0 全量审计 | L0 报告 | 2 |
| E2 | 60 题 L1：B1/C1/C2 | 检索对比 | 4 |
| E3 | L2 上下文闭合 | 20 题报告 | 2 |
| E4 | L3/L4 执行子集 | 10 题报告 | 2 |
| E5 | L5 补丁子集 | 5 题报告 | 2 |
| E6 | 文档/失败案例 | handoff | 1 |
| 合计 |  |  | **15 人日** |

---

## 11. Gate

```text
G0 L0：parse_ok=100%，span_exact≥99%
G1 L1：C1/C2 的 File/Symbol Hit@1 高于 B1 ≥10pp
G2 L1：C2 的 Hit@5 不低于 B1
G3 L2：C3 import_recall≥0.90
G4 L3：compile_pass≥0.95
G5 L4：test_pass@1≥0.80
G6 L5：patch 无回归
```

任何一条失败：

```text
不把 code RAG 放进主路径
保留为手动工具
```

---

## 12. 指标口径

### 12.1 检索

```text
Recall@k = top-k 内有 gold
MRR = 1/首次命中 rank
nDCG = 分级相关性
```

### 12.2 结构

```text
parse_ok_rate
span_exact_rate
delimiter_balance_rate
```

### 12.3 上下文

```text
import_recall
symbol_closure
version_match
```

### 12.4 执行

```text
test_pass@1
resolved
```

---

## 13. 不能做的事

```text
不把 L0 叫“准确率”
不把 L2 叫“召回率”
不把 L4 的 Pass@1 当检索指标
不拿文献 SciFact 数字横比
不把 grep-like 代理说成完整 DSH
不隐藏 DSH 在当前仓库的优势
```

---

## 14. 交付物

```text
eval/code_rag_stack/
  questions.json
  harness.py
  results/
  manifest.json

docs/
  报告-代码RAG评测栈.md
```

---

## 16. 标准不降

评测是给科研决策用的，不是拿来说服别人。

```text
未跑 = 未跑
失败 = 失败
不把 null 写成 0
不把 0 写成“接近通过”
```

E4 当前：

```text
G4 compile PASS
G5 test_pass@1 NOT RUN
```

因此：

```text
不能声称“代码能跑”
不能把 compile 当 Pass@1
L4 未完成前，不进入主路径
```

如果独立环境无法稳定复现：

```text
L4 标记 blocked
不降低 G5
不用“大致能跑”替代
```

## 15. 结论

```text
代码 RAG 的评测不是“一个准确率”
是五层门禁
```

```text
L0 结构
L1 检索
L2 上下文
L3 编译
L4 执行
L5 补丁
```

DSH 对照：

```text
B1 是主基线
LSP 可用才叫 B2
C3 必须和 B1 同预算
```

先跑 L0/L1，再决定是否投入 L3/L4。  
如果 L1 都赢不了 B1，后面的执行评测没有意义。

## 17. 检索边界（A 决策）

```text
C1 = 文件级
C3 = 符号级
```

理由：

```text
C1 30 题 file 29/30
C1 symbol 23/30
手写 boost 后 file 26/30，更差
```

规则：

```text
不把 C1 的 symbol 命中当验收
C1 只报 file Hit@k / MRR
C3 报 file + symbol
```

如果必须用 C1 找符号：

```text
只能作为候选
必须 read 文件确认
```

不能：

```text
为了 30 题手写符号规则
把 C1 说成符号级可用
```
