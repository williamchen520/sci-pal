# P3：sentence backend 接入

> 日期：2026-11-11  
> 状态：**已接入 `/api/evidence/search`；句级基线已出**

---

## 1. 改动

```text
services/search/sentence_hybrid.py
  新增 to_evidence_json()
  输出兼容 /api/evidence/search 的 evidence bundle

api_server.py
  新增 get_evidence_retriever()
  SCIPAL_EVIDENCE_BACKEND=sentence（默认）
  unified/legacy 可回退
```

bundle 结构：

```text
evidence[]
  paper_id
  para_id
  text
  highlight[]            <- anchor sentence
  matched_sentences[]
  paragraph_details[]    <- window sentence ids
```

## 2. 排序与上下文边界

```text
排序单位：anchor sentence
窗口：build_context()，逻辑词/边界/1200 字
context_scored = False
窗口不参与 lexical/RRF/rerank
```

## 3. 句级基线

20 题、重建库、sentence backend：

```text
Recall@10 = 0.5500
MRR       = 0.3187
nDCG@10   = 0.3785
```

文件：

```text
eval/results/rebuild_20_sentence.json
```

对照：

```text
paragraph vector          0.6000
paragraph native-FTS RRF  0.7000
sentence hybrid           0.5500
```

句级低于段落级是预期的：段落命中不等于命中句命中。

## 4. 注意

本轮 sentence backend 默认带 cross-encoder rerank；`SCIPAL_RERANK=0` 不会关闭 `SentenceHybridRetriever` 的 reranker。

所以这个 0.55 是：

```text
sentence hybrid + rerank
```

不是 no-rerank 对照。

## 5. 下一步

```text
1. 给 SentenceHybridRetriever 加 rerank 开关
2. 1200 / 600 / 300 字窗口对照
3. 逻辑词开/关对照
4. 指标看 anchor recall + context 覆盖率，不看窗口排序
```


## 6. 生产部署发现

部署 #631 后 `/api/evidence/search` 返回 500：

```text
psycopg.errors.UndefinedTable:
relation "paragraph_embeddings" does not exist
```

原因：

```text
生产 public 仍是恢复后的 3,301 篇快照
该快照没有 paragraph_embeddings
sentence backend 依赖它
```

处理：

```text
evidence_search 增加 sentence -> unified 自动回退
```

边界：

```text
sentence 路径仍默认
embeddings 恢复后自动生效
当前生产实际走 unified fallback
```

这说明 P3 不能只看重建库指标；生产 corpus 的向量表必须先补齐。
