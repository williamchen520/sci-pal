# 贡献指南（CONTRIBUTING）

> 本文件中的“铁律”优先级高于个人习惯；违反铁律的 PR 不予合并。

## 铁律

### 1. PR 必须使用模板
所有 PR 必须包含以下三部分，标题保持原样：

1. `## 1. 背景描述`
2. `## 2. 核心改动`
3. `## 3. 基准测试指标变化`

缺少任意一项，CI 会失败；**没有基准数据的 PR 不合并**。

### 2. 基准测试必须可复现
- 评测语料：本地论文库（当前 **3,297 篇**；如使用 **500 篇子集**，必须在 PR 中注明子集与抽样方式）；
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
