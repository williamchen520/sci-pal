[English](CONTRIBUTING.md) | **简体中文**

# 贡献指南（CONTRIBUTING）

> 本文件中的“铁律”优先级高于个人习惯；违反铁律的 PR 不予合并。

## 架构宪法（最高安全红线）

`ARCHITECTURE.json` 是系统宪法，**AI 只读**。

修改路由必须：

1. 在对话框输出拟修改 JSON 代码块和原因；
2. 等待人类回复 **“批准修改”**；
3. 收到批准后才写 `ARCHITECTURE.json`；新节点标 `"status": "planned"`；
4. 运行 `python scripts/validate_arch.py`；
5. 校验通过后才写 Flask 路由/handler。

测试失败若因 Python 与 JSON 契约不一致，必须改 Python 适配 JSON；**绝对禁止反向修改 JSON 参数来跑通测试**。

修改 `ARCHITECTURE.json` 的 commit message 必须含 `[APPROVED_BY_HUMAN]`；由 `pre-commit` + `commit-msg` 钩子拦截。

不在 JSON 中的野路由会被拒绝。详见 [docs/开发流程规范.md](docs/开发流程规范.md)。

## 全自动施工与 PR 审批

默认流程：需要时先提出 JSON 方案 → 实现 → `validate_arch.py` → 全量测试 → 写 Worklog → 建 PR。

- 测试失败自己修、自己重跑，直到全绿。
- 只在循环报错、JSON 未获批准、核心鉴权/tenancy、不可逆数据操作、研究裁决、>300 行重构时停下来问。
- Worklog 写在 `worklogs/YYYY-MM-DD-<topic>.md`，包含模块、业务变化、测试通过率、外部 API/数据风险。
- PR 状态为 `Pending Review`；**只有人类明确回复“批准合并”才能合并。**
- 净变更超过 300 行的 PR 标 `[LARGE]`，必须单独评审。

## 铁律

### 1. PR 必须使用模板
所有 PR 必须包含以下三部分，标题保持原样：

1. `## 1. 背景描述`
2. `## 2. 核心改动`
3. `## 3. 基准测试指标变化`

缺少任意一项，CI 会失败；**没有基准数据的 PR 不合并**。

### 2. 基准测试必须可复现
- 评测语料：本地论文库**全部文章**（当前 **3,297 篇**，不做子集抽样）；
- 评测集：`eval/gold/seed_100.jsonl`（100 题；30 curated + 70 auto）；
- 必须给出：**基线 → 变更后 → 变化**，并注明命令与输出文件；
- 至少包含 `Recall@10`、`MRR`、`nDCG@10`、`refusal_accuracy` 中的相关项；
- 只改文档/CI 的 PR 可写“无指标变化”，但仍需保留该章节。

### 3. 数据表自动生成
`docs/项目里程碑数据表.md` 由脚本生成：

```powershell
python scripts/collect_milestones.py --repo williamchen520/sci-pal
```

**不要手工编辑**该文件；要修正数据，请改 PR 正文后重新生成。

### 4. 测试门槛
- `python -m unittest discover -s tests -p "test_*.py"` 必须全绿；
- 新增行为必须有测试；
- 失败实验可以写进 PR，但不要留在主分支。

### 5. 合并方式
- 只允许 Merge commit，不用 Squash/Rebase；
- 合并后同步 `master` 与 Gitee 镜像。

## PR 模板

见 `.github/pull_request_template.md`。

## 基准数据格式

模板第 3 节必须包含 Markdown 表格：

```markdown
| 指标 | 基线 | 变更后 | 变化 |
|---|---|---|---|
| Recall@10 | 0.5192 | 0.6538 | +25.9% |
| MRR | 0.3331 | 0.3597 | +8.0% |
```

`collect_milestones.py` 会按这个格式抽取。

## 本地检查

```powershell
python -m unittest discover -s tests -p "test_*.py"
python eval/retrieval_eval.py --limit 30
python scripts/collect_milestones.py
python scripts/plot_milestones.py --metric Recall@10 --output docs/milestones_recall.svg
```

---

## 2026-11-12 增补：双库隔离与治理门禁

### 两个数据库

```text
scipal_core      用户 / 鉴权 / 项目 / 实验 / 笔记 / 任务
scipal_rebuild   论文 / 段落 / 句子 / 向量
```

规则：

```text
没有跨库外键
只用逻辑 ID
路由只能走 core_connection() 或 corpus_connection()
业务读不碰 scipal_rebuild
语料读不碰 scipal_core
```

### 最小权限与迁移

```text
core_app       业务/鉴权，无 DDL
corpus_reader  语料只读
corpus_writer  语料写入，无 DDL
app 启动       不得 CREATE/ALTER 表
插件建表       scripts/migrate_ingest_tracking.py（owner 角色）
```

### 生产环境校验

```text
SCIPAL_ENV=production
拒绝 loopback / 错库 DSN
必须有 SCIPAL_CORE_DSN 和 SCIPAL_PG_CORPUS_DSN
```

### 治理门禁

```powershell
python scripts/governance_gate.py --paths <changed> --ops <ops> --plan "..." --risk "..."
```

命中后需要人类回复“批准执行”，并给 PR 加 `governance-approved` 标签。
CI 使用 base 分支的门禁脚本，防止 PR 改门禁绕过门禁。

### 必跑检查

```text
python scripts/validate_arch.py
python scripts/check_data_boundary.py
python -m unittest discover -s tests -p "test_*.py"
python scripts/smoke_http.py          # 27/27
python scripts/smoke_group_b.py       # 13/13
```

### 备份

```text
core 6h / 7d；corpus 7d / 28d
加密；恢复演练包含 GIN + HNSW
```
