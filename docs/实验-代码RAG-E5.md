# 实验记录：code-rag E5 真实 DSH 会话 pilot

> 日期：2026-11-13  
> 状态：**6 题 pilot；B1/C1 都 6/6，未分出差异**  
> 数据：`eval/code_rag_stack/results/e5_dsh_pilot.json`

---

## 1. 设计

6 题：

```text
scanpy    3
rnaseq    3
```

两条臂：

```text
B1  DSH 原生 grep/glob/read/pwsh
    禁止 mcp__scipal-code__*
    禁止查询 scipal_code

C1  mcp__scipal-code__code_search
    code_trace（如需）
    read 实际文件
```

约束：

```text
同一仓库/commit
最多 5 次工具调用
不告诉 expected
返回 path + symbol + confidence
```

## 2. 结果

| 臂 | File 正确 | Symbol 正确 |
|---|---:|---:|
| B1 | 6/6 | 6/6 |
| C1 | 6/6 | 6/6 |

```text
B1 file_accuracy   1.000
B1 symbol_accuracy 1.000
C1 file_accuracy   1.000
C1 symbol_accuracy 1.000
```

## 3. 这说明什么

```text
不能说明 code RAG 更好
只能说明这 6 题太容易
```

题目特点：

```text
query 和 symbol 高度同名
目标文件唯一
没有版本歧义
没有跨文件数据流
没有 config/错误
```

B1 用 3–5 次 grep/read 就能找到；  
C1 用一次 code_search 也能找到。

## 4. 观察

```text
C1 在 STAR_ALIGN 上 code_trace 返回 0 边
但文件读取仍能确认答案
```

说明：

```text
trace 不是万能
最终仍要 read 文件
```

B1 的优势：

```text
不用索引
直接读最新文件
```

C1 的优势：

```text
精确符号候选更快
少几次 grep
```

## 5. 结论

```text
pilot 通过协议
但没有区分度
不能据此下结论
```

不能写：

```text
code RAG 优于 DSH
```

## 6. 下一步

扩到 30 题，必须加难：

```text
跨文件调用链
config override
版本/API 迁移
报错/测试定位
同名 symbol 多文件
```

否则会继续得到 6/6 vs 6/6。

当前：
```text
E5 pilot 完成
E5 full 未完成
```

## 7. 硬题 pilot（6 题）

在易题 6/6 之后，加 6 道硬题：

```text
_numeric helper / view copy
deprecated read wrapper
config override
STAR/Sentieon/Parabricks dispatch
FastQC raw before trim
```

结果：

| 臂 | File 正确 | Symbol 正确 |
|---|---:|---:|
| B1 | 5/6 | 5/6 |
| C1 | 6/6 | 6/6 |

唯一分差：

```text
h01 numeric helper
  B1: axis_mul_or_truediv / _utils/__init__.py
  C1: _normalize_total_helper / _normalization.py
```

解释：

```text
B1 找到更底层的数组运算
C1 找到 normalize_total 的直接 helper
```

但这只是 1 道题：

```text
不能证明 code RAG 更好
```

仍需 30 题完整对照。

## 8. 硬题扩到 12（仍不是 30）

新增 6 题：

```text
calculate_qc_metrics
filter_cells
_pca_compat_sparse
fastp config
MultiQC config
PREPARE_GENOME_REFERENCES
```

结果：

| 臂 | File 正确 | Symbol 正确 |
|---|---:|---:|
| B1 | 11/12 | 11/12 |
| C1 | 12/12 | 12/12 |

新增 6 题两边全对。

唯一分差仍是：

```text
h01 numeric helper
  B1: axis_mul_or_truediv
  C1: _normalize_total_helper
```

修正 gold：

```text
h11 改为 assets/multiqc_config.yml
因为两边都正确指向报告配置文件
```

结论：

```text
12 题不能证明 code RAG 更好
只能说明 h01 这类“直接 caller vs 底层 callee”题有区分潜力
```

还剩 18 题才到 30。

## 9. 30 题硬题完成

结果：

| 臂 | File 正确 | Symbol 正确 |
|---|---:|---:|
| B1 | 29/30 | 29/30 |
| C1 | 30/30 | 30/30 |

B1 唯一错误：

```text
h01 numeric helper
  B1: axis_mul_or_truediv / _utils/__init__.py
  C1: _normalize_total_helper / _normalization.py
```

但 C1 有协议偏差：

```text
e02 C1 使用 grep 兜底
e05 C1 使用 grep 兜底
```

原因：

```text
code index 没有把 tests/ 排在前面
C1 最终靠 grep 才找到
```

所以：

```text
C1 30/30 不能全部算 code_search 的功劳
纯 C1：28/28
```

这不是小问题：

```text
代码 RAG 对测试定位的覆盖不足
真实 DSH 会话里会退化成 grep
```

## 10. 当前结论

```text
30 题硬集已完成
B1 29/30
C1 30/30（2 题 grep 兜底）
```

能说明：

```text
在 h01 这类跨文件 helper 题上
code_search 有优势
```

不能说明：

```text
code RAG 全面优于 DSH
测试定位已被 code_search 覆盖
```

下一步：

```text
补测试文件索引/权重
或把 C1 改成 C3（允许 grep）重新定义
```

## 11. A 项：修 test 权重后的纯检索

改动：

```text
query 明确问 test/error 时
tests/ 不再 *0.55，而是 *1.10
非 test 问题仍降权
symbol 候选 500 -> 2000
```

e02/e05 纯 code_search：

```text
e02 test_regress_out_view     top1
e05 test_score_genes_sparse   top1
```

30 题纯 code_search top-10 复测：

```text
file_correct   29/30
symbol_correct 23/30
file_accuracy  0.967
symbol_accuracy 0.767
```

失败项：

```text
h03  read     -> wrapper
h06  workflow -> FASTQC
h11  assets   -> conf/modules/multiqc.config
v01  write    -> write_h5ad
v05  read_params -> settings
v06  write_params -> settings
m05  write    -> write_sparse_npz
```

结论：

```text
C1 的 30/30 不是纯 code_search
它用了 read/grep 兜底
纯检索 file 29/30，symbol 23/30
```

这比“30/30”更诚实，也更有用。

下一步：

```text
修 wrapper/write/params 符号排序
或正式定义 C3 = search + read/grep
```

## 12. C3 定义与重分类

正式定义：

```text
C1  code_search only
C2  code_search + code_trace
C3  code_search + trace + read/grep fallback
```

30 题原始结果被错误标成 C1；实际用了 read/grep，现重分类为：

```text
C3  30/30
```

纯检索 C1：

```text
file   29/30
symbol 23/30
```

最终口径：

| 臂 | File | Symbol |
|---|---:|---:|
| B1 | 29/30 | 29/30 |
| C1 pure | 29/30 | 23/30 |
| C3 | 30/30 | 30/30 |

不能再说：

```text
C1 30/30
code_search 30/30
```

能说：

```text
C3（带 read/grep）30/30
C1 pure 文件 29/30、符号 23/30
```

## 13. 下一步

```text
修 C1 符号排序
  wrapper / write / read_params / settings
```

如果修不动：

```text
C1 只用于文件定位
符号定位交给 C3/read
```

## 14. 决策：C1 只做文件级

```text
C1 = file retrieval
C3 = symbol retrieval
```

数据：

```text
C1 file   29/30
C1 symbol 23/30
C3 file   30/30
C3 symbol 30/30
```

尝试符号 boost 后：

```text
file 26/30
symbol 22/30
```

所以回退，不保留。

后续验收：

```text
文件定位：C1
符号定位：C3
```

不再把 C1 的 29/30 写成“符号 29/30”。

## 15. C3 证据包工具

新增：

```text
mcp__scipal-code__code_context
```

返回：

```text
目标 unit
+ 目标文件 import
+ 直接邻居
+ edges
```

用途：

```text
C3 = search + context + read
```

不改变 C1/C3 指标。

DSH 需重启后才会出现第 4 个 code 工具（总数 39）。
