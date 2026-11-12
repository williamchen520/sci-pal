# Phase C 可复现 Manifest

> 日期：2026-11-12  
> 代码 commit：`22155b534826d8f30186e9fa1dfe93993c95279e`  
> 机器可读：[eval/manifests/phase_c_manifest.json](../eval/manifests/phase_c_manifest.json)

---

## 1. 固定内容

Manifest 记录：

```text
git commit
Python 版本
embedding / reranker 模型
数据文件 SHA256
结果文件 SHA256
复现命令
已知缺口
```

---

## 2. 数据

| 文件 | 大小 | SHA256（前 16） |
|---|---:|---|
| `data/benchmark_scifact.db` | 48,320,512 | `ace1afead4e0d4f2` |
| `eval/gold/scifact_300.jsonl` | 90,649 | `efe689041fb01fba` |

数据规模：

```text
papers       5,183
sentences   45,051
claims        505
```

---

## 3. 模型

```text
BAAI/bge-base-en-v1.5     768 维
BAAI/bge-reranker-base    cross-encoder
BAAI/bge-small-en-v1.5    384 维（PaperQA dense 烟测）
```

模型路径在本机 `G:\models\`，不提交仓库。

---

## 4. 复现命令

```bash
# 300 claims, 120 words, S/C2/C3
python -m eval.scifact_phase_c \
  --limit 300 --chunk-words 120 --include-sentence \
  --output eval/results/scifact_phase_c_300_120_S.json

# 全量严格映射 501
python -m eval.scifact_phase_c \
  --limit 0 --chunk-words 120 --include-sentence \
  --output eval/results/scifact_phase_c_501_120_strict.json

# paired bootstrap
python -m eval.scifact_phase_c_stats \
  --input eval/results/scifact_phase_c_501_120_strict.json

# BM25 / Dense / Hybrid
python -m eval.scifact_systems \
  --limit 0 --chunk-words 120 \
  --output eval/results/scifact_systems_501.json
```

---

## 5. 结果文件

```text
eval/results/scifact_phase_c_20.json
eval/results/scifact_phase_c_20_120.json
eval/results/scifact_phase_c_300_500.json
eval/results/scifact_phase_c_300_120.json
eval/results/scifact_phase_c_300_200.json
eval/results/scifact_phase_c_300_120_S.json
eval/results/scifact_phase_c_300_120_rerank.json
eval/results/scifact_phase_c_501_120_strict.json
eval/results/scifact_phase_c_20_C3.json
eval/results/scifact_systems_300.json
eval/results/scifact_systems_501.json
```

每个文件的 SHA256 在 JSON manifest 中。

---

## 6. 已知缺口

```text
全量 505 中 4 条 claim 的最后一帧缺失：
624 / 751 / 815 / 816
全量实验只保留 501 条，不伪造
C3 全量运行超时，只有 20 条烟测
PaperQA2 dense 是采样 paper-level，不可与 F0 比较
```

---

## 7. 结论

```text
Phase C 结论固定：
F0 / Dense 检索基线
B 上下文层
C/S/C2/C3/rerank/hybrid 不进入主线
```

Manifest 用于：

```text
复现
审计
后续系统层对比
失败案例分析
```

不再改 Phase C 方法或参数。
