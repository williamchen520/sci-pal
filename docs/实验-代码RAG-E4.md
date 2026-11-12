# 实验记录：code-rag E4 编译 / 执行（部分）

> 日期：2026-11-13  
> 状态：**compile 已跑；test_pass@1 因环境未安装，不伪造**  
> 数据：`eval/code_rag_stack/results/e4_compile.json`

---

## 1. 范围

10 个 Python 题：

```text
normalize_total
read_10x_h5
highly_variable_genes
neighbors
umap
leiden
score_genes
pca
regress_out
rank_genes_groups
```

每题的 top1 unit 取完整源码，执行：

```python
compile(textwrap.dedent(unit_text), symbol, "exec")
```

## 2. 结果

```text
cases 10
unit_compile_pass 1.000
retrieval_top1    0.700
task_compile_pass 0.700
```

解释：

```text
unit_compile_pass=1.0：检索到的 unit 都能 compile
task_compile_pass=0.7：top1 命中且能 compile 的题
```

top1 错的题：

```text
neighbors -> tests/test_metrics.py:test_graph_metrics_w_constant_values
rank_genes_groups -> ci/scripts/low-vers.py:groups
```

## 3. test_pass@1 未跑

主 venv：

```text
scanpy False
anndata False
pytest False
```

隔离安装：

```text
G:/venvs/scanpy-eval-pkgs
```

pip 安装长时间无落地文件，已停止。

所以：

```text
test_pass@1 = null
不是 0
不是 1
是未测
```

不能把 `compile_pass=1.0` 写成“能跑”。

## 4. Gate

```text
G4 compile_pass ≥0.95   PASS（unit-level）
G5 test_pass@1 ≥0.80    NOT RUN
```

且：

```text
task_compile_pass=0.70
```

说明检索错时，编译通过不代表任务正确。

## 5. 结论

```text
E4 只完成 L3
L4 未完成
```

要跑 L4，需要：

```text
独立 scanpy 评测环境
pytest
测试数据 fixture
不污染主 venv
```

## 6. 下一步

```text
1. 建独立 scanpy 环境（venv/conda/容器）
2. 只跑 5 个 fixture 稳定的测试
3. test_pass@1 单独报
```

如果环境无法稳定复现：

```text
L4 不做
不把 Pass@1 当卖点
```
