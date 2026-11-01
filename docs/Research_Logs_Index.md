# Research Logs Index

> Maintained by the project. Add one row for every new research, evaluation, or experiment archive.  
> Convention: create the research document first, then add its relative link here in the same pull request.


---

## ⚠️ 重大决策：OpenAlex 标签暂时采用（2026-11-01）

> **决策人**：项目负责人  
> **状态**：PROVISIONAL — 不是人工 ground truth  
> **范围**：实验与开发使用；生产 domain routing 仍关闭

项目负责人明确：

```text
暂不做 100 篇人工复核，先使用 AI 预标注。
```

这意味着：

```text
OpenAlex primary_topic + auto L1 + AI prelabel
可以作为开发期领域标签使用
但不得声称已通过人工校验
不得据此直接开启生产 domain routing / topic penalty
```

风险：

```text
AI prelabel 是启发式结果
28 条 low-confidence 仍未人工复核
topic 错误可能传导到 coverage audit
```

后续必须：

```text
1. 保留 ai_/human_ 字段区分
2. 在报告里标注 provisional
3. 重新评估前不得删除 human validation 任务
```

---

| Date | Topic | Result | Document |
|---|---|---|---|
| ⚠️ 2026-11-01 | OpenAlex labels provisional | Owner waived human review; AI prelabels accepted for experiments only; not ground truth | [Human validation kit](审计-OpenAlex-100篇人工校验.md) |
| 2026-11-01 | PostgreSQL migration read path | P5 canary 100% PG; 5/20-concurrency checks passed | [PostgreSQL P5 canary](PostgreSQL迁移-P5-读路径Canary.md) |
| 2026-11-01 | Data-tree migration audit | Article→section→paragraph→sentence survived; figures/tables lacked section binding; XML has no PDF coordinates | [Data tree audit](数据树形结构迁移审计.md) |
| 2026-11-01 | Source-aware schema v2 | XML keeps XPath/source_nodes; PDF keeps pages/blocks/bbox; sentence-level FTS | [Schema v2 design](数据重建-schema-v2-按源类型建模.md) |
| 2026-11-01 | P2 XML rebuild | 2,820 papers, 0 failures; paragraphs/sentences matched old source subset | [P2 XML rebuild](数据重建-P2-XML重建.md) |
| 2026-11-01 | P3 PDF rebuild | 83 papers; 61,739 sentences; 1,374 pages; 26,901 blocks; structure zero diff | [P3 PDF rebuild](数据重建-P3-PDF重建.md) |
| 2026-11-01 | P4 sentence FTS | Source-aware sentence search; XML XPath, PDF page/bbox | [P4 sentence FTS](数据重建-P4-句子级FTS.md) |
| 2026-11-01 | P4 sentence FTS evaluation | 20 queries: paragraph 1.0000/.8806/.9097 vs sentence .9000/.6250/.6943; not switched | [P4 sentence FTS evaluation](数据重建-P4-句子级FTS评估.md) |
| 2026-11-01 | RRF / multi-stage pilot | 4-query RRF improved MRR; full 20/50 not reproducible | [P4 RRF experiment](数据重建-P4-RRF实验.md) |
| 2026-11-01 | Reranker single-query profile | worker_start 40.57s; inference 0.667s | [Reranker profile](数据重建-P4-Reranker-Profile.md) |
| 2026-11-01 | Warm reranker service | HTTP `/score`; service startup once; 20/50 single request measured | [Warm reranker](数据重建-P4-Warm-Reranker.md) |
| 2026-11-01 | Warm service `/score` latency | 20 paragraphs ~0.25s; 50 ~0.31s | [Service latency profile](数据重建-P4-Reranker-Service-Profile.md) |
| 2026-11-01 | End-to-end RRF loop profile | sentence FTS 9.24s dominates; total 204.6s / 20 queries | [RRF loop profile](数据重建-P4-RRF-Loop-Profile.md) |
| 2026-11-01 | Sentence FTS latency variants | Direct variants 0.17–0.26s; source-filter fix helped single query | [Sentence FTS latency](数据重建-P4-Sentence-FTS-Latency.md) |
| 2026-11-01 | Two-stage recall + rerank | Unranked recall 0.256s but Recall@10 0.00; 5-term ranked recall 0.85 | [Two-stage recall](数据重建-P4-两阶段召回.md) |
| 2026-11-01 | rank_cd narrow validation | 5 same-paper queries gave false 1.0; spread sample: 1.0000/.8000/.8524 | [rank_cd narrow validation](数据重建-P4-RankCD-小范围.md) |
| 2026-11-01 | Community / literature search solutions | Two-stage retrieval is standard; prefer existing HybridSearch or ParadeDB pg_search; ES/Vespa later | [Search solutions research](检索优化-社区方案调研.md) |

| 2026-11-01 | Existing HybridSearch 20-query baseline | .7000/.6417/.6565; worse than paragraph FTS 1.0000/.8806/.9097; not switched | [HybridSearch baseline](检索评估-HybridSearch-20query.md) |

| 2026-11-01 | HybridSearch recall loss | vector hits had top-level `paper_id=None`; fixed; q009 gold now rank 2; 20-query rerun pending | [HybridSearch paper_id fix](检索-修复HybridSearch丢失paper_id.md) |

| 2026-11-01 | HybridSearch paper_id fix rerun | no-rerank 1.0000/.9250/.9446; None bucket gone; rerank pass pending | [HybridSearch fix](检索-修复HybridSearch丢失paper_id.md) |

| 2026-11-01 | Retrieval document-bias audit | paper recall 1.0000; gold sentence top10 only 9/20; mean max hits/paper 118.4 | [Bias audit](检索-文档级偏置审计.md) |

| 2026-11-01 | HybridSearch document-bias audit | paper recall 0.9000; unique papers@10 4.45; gold sentence 6/20; max hits/paper 5.5 | [HybridSearch bias audit](检索-HybridSearch偏置审计.md) |

| 2026-11-01 | Document-bias / redundancy solutions | per-doc cap, MMR, sentence-level gold; ir_measures/ranx/BEIR | [Bias solutions](检索-文档级偏置方案调研.md) |

| 2026-11-01 | max_per_paper=2 audit | corrected: unique@10 3.85→7.5, gold sentence 9→10; candidate, not shipped | [Bias audit](检索-文档级偏置审计.md) |

| 2026-11-01 | Retrieval SLO / redundancy design | 3s p95 online, 1s light path; no hard cap; MMR + soft caps; gates defined | [SLO design](设计-检索SLO与冗余控制.md) |

| 2026-11-01 | Near-duplicate suppression | opt-in `SCIPAL_NEAR_DUP_THRESHOLD`; audit gold sentence 9→12; 759 tests OK | [Near-duplicate suppression](检索-近重复抑制.md) |

| 2026-11-01 | HybridSearch + near-dup audit | no effect: 0.9000/0.8500/0.8631; unique@10 4.45; gold sentence 6/20 | [HybridSearch near-dup](检索-HybridSearch近重复审计.md) |

| 2026-11-01 | Domain coverage / routing discussion | coverage ceiling vs hubness; domain boost + topic penalty; audit required first | [Domain discussion](讨论-领域覆盖与领域感知路由.md) |

| 2026-11-01 | Domain coverage audit | domain labels missing; journals 940, Gini .588; hub_paper_rate .237; lexical proxy weak | [Domain coverage audit](审计-领域覆盖.md) |

| 2026-11-01 | Open-source domain labels research | OpenAlex Topics first; Europe PMC/PubMed MeSH validate; Crossref fallback; BERTopic exploratory | [Domain labels research](调研-领域标签与覆盖评估.md) |

| 2026-11-01 | OpenAlex DOI coverage probe | 200 random: 199 fetched, 99.5%; 4 domains; 1 missing; labels not yet validated | [OpenAlex coverage](审计-OpenAlex覆盖率.md) |

| 2026-11-01 | Full OpenAlex enrichment | 3,290/3,310 (99.4%); 12 missing; stored paper_domains_openalex; auto L1 labels also found | [Full OpenAlex audit](审计-全量OpenAlex与领域标签.md) |

| 2026-11-01 | OpenAlex 100-paper validation kit | AI prefill 100/100 (72/16/12); human 0/100; OpenAlex+DOI+MeSH evidence | [Human validation kit](审计-OpenAlex-100篇人工校验.md) |

| 2026-11-01 | OpenAlex low-confidence 28 | exported low-confidence review list; human fields blank | [Low-confidence 28](审计-OpenAlex-低置信度28条.md) |

| 2026-11-02 | PG write-path productionization plan | corrected: prod SQLite vs PG diff {}; earlier 7-table gap was dev-vs-prod | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | PG tenancy write path Phase 1 | PG-first user/workspace/member + SQLite mirror; 762 tests; sequence bug fixed | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Tenancy PG canary | create user/workspace/member + list + read-back + cleanup passed in production PG; flag still off | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Tenancy direct-read migration | projects/experiments use tenancy service; PG read canary owner + scrypt pass | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Tenancy write flag production | image tenancy-write healthy; flag=postgres; prod canary pass; rollback tagged | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Production tenancy login verification | login/me/workspaces/members/logout 200; cleanup 401; no public register route | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Tenancy mirror drift check | prod write -> SQLite/PG 3/3, drift false; cleanup 2/2, outbox 0 | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Tenancy drift health task | dual_write_healthcheck adds row-level tenancy drift; compose health-cron every 300s | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Health-cron deployed | 300s drift check running; first run status ok, drift false | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Soft cap / MMR audit | cap2 unique 3.85→7.5 but sentence 12→10; MMR λ=.75 sentence 5; reject | [Soft cap/MMR](检索-SoftCap-MMR审计.md) |

| 2026-11-02 | Work summary / next steps | 766 tests; PG tenancy live; retrieval experiments; backlog prioritized | [Work summary](工作总结-2026-11-02.md) |

| 2026-11-02 | Tenancy outbox removed + alerts | 9 triggers dropped; 0 pending; health webhook/stderr alert; 768 tests | [PG write path](设计-PostgreSQL写路径生产化.md) |

| 2026-11-02 | Tenancy fail-closed on PG outage | PG exited 255; restart policy fixed; fallback removed; 769 tests | [PG write path](设计-PostgreSQL写路径生产化.md) |

## Rules

```text
1. New research or experiment document → add a row here in the same PR.
2. Put the conclusion in the row, not only the title.
3. Keep links relative to docs/.
4. Do not list one-off PR links; link the durable document.
```
