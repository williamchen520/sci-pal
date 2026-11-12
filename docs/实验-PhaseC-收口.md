# Phase C 收口记录

> 日期：2026-11-12  
> 状态：**Phase C 结束；F0/Dense 为检索基线，B 为上下文层**  
> 系统层：PaperQA2 / GraphRAG 暂缓，隔离安装未完成

---

## 1. 收口结论

```text
检索基线    F0 / Dense
上下文层    B（±1 句窗）
停止        C / S / C2 / C3 / rerank / hybrid
暂停        A / D / E / GA
```

原因：

```text
B 与 F0 首跳完全相同，只提升 context recall
C 的句界 chunk 不优于 F0
S 纯句检索显著更差
C2/C3 聚合没有救回首跳
rerank 没有提升
BM25 / Hybrid RRF 都低于 Dense
```

---

## 2. 关键数字

### 全量 501 claims，120 词

| 臂 | Hit@10 | Sentence Recall@10 | Context Recall@10 |
|---|---:|---:|---:|
| F0 | 0.948 | 0.916 | 0.916 |
| B | 0.948 | 0.916 | 0.946 |
| C | 0.942 | 0.899 | 0.931 |
| S | 0.838 | 0.703 | 0.819 |
| C2 | 0.916 | 0.854 | 0.890 |

### 系统级 baseline，501 claims

| 系统 | Hit@10 | MRR@10 |
|---|---:|---:|
| BM25 | 0.852 | 0.653 |
| Dense (F0) | **0.948** | **0.741** |
| Hybrid RRF | 0.922 | 0.714 |

### Paired bootstrap（Hit@10 vs F0）

```text
B - F0    0.000  CI [0.000, 0.000]
C - F0   -0.006  CI [-0.022, 0.010]
S - F0   -0.110  CI [-0.142, -0.082]
C2 - F0  -0.032  CI [-0.054, -0.012]
```

---

## 3. 数据状态

```text
SciFact papers       5,183
sentences            45,051
claims                 505
前 300 claims         evidence 100% 映射，Gate 1 通过
全量 505              4 条 claim 有句界缺失
全量实验              501 条严格映射，不伪造
```

缺失 claim：

```text
624 / 751 / 815 / 816
```

要跑全量 505，必须先修 DB 句界或换原始 SciFact abstract 列表。

---

## 4. 产物

```text
eval/scifact_phase_c.py
eval/scifact_units.py
eval/scifact_phase_c_stats.py
eval/scifact_systems.py
tests/test_scifact_phase_c.py
eval/results/scifact_phase_c_*.json
eval/results/scifact_systems_*.json
docs/报告-PhaseC-SciFact.md
docs/实验-PhaseC-SciFact-300.md
```

---

## 5. 系统层尝试与阻塞

尝试：

```text
独立 venv  G:\venvs\paperqa
package    paper-qa==2026.8.12
```

结果：

```text
安装 15+ 分钟未完成
未安装成功
已停止，不污染主 venv
```

已确认：

```text
paper-qa 2026.8.12  Requires-Python >=3.11
依赖 fhlmi / fhaviary / tantivy / pypdf / LLM provider
GraphRAG 3.3.0 依赖 numpy~=2.4 / pandas~=3.0 / pydantic~=2.13
```

结论：

```text
系统层不在当前环境直接跑
PaperQA2 只做隔离环境 50 claims adapted 烟测
GraphRAG 等图索引预算
```

---

## 6. 不做的事

```text
不再调 500/200/120 词
不再做 C 变体
不再做等权 hybrid
不再做小池 rerank
不做 A/D/E/GA
不把 PaperQA2/GraphRAG 装进主 venv
```

---

## 7. 下一步

```text
1. Phase C 结束，不再产生新方法结论
2. 需要系统层时，先解决隔离安装/LLM provider
3. PaperQA2 仅做 50 claims adapted smoke
4. GraphRAG 暂不做
5. 若回到主线，优先整理可复现 manifest 与失败案例
```

当前最稳妥的结论：

```text
F0 / Dense 是可靠检索基线
B 是上下文层，不是召回层
Phase C 的方法探索到此收口
```
