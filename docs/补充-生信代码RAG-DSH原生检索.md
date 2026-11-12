# 生信代码 RAG 计划：补充建议书

> **已废弃（2026-11-12）**：由 [计划-代码增强RAG-平台模块-v1](计划-代码增强RAG-平台模块-v1.md) 取代；仅保留历史讨论。


> 版本：v1  
> 日期：2026-11-12  
> 关系：对 [计划-生信代码RAG](计划-生信代码RAG.md) 的范围修正  
> 状态：讨论稿，实验 Phase C 之后再实施

---

## 1. 结论

```text
自己的 SciPal 代码库
  -> DSH 原生 grep + read + LSP + 多轮
  -> 不做代码 RAG

外部生信配方 / 包版本 / 方法
  -> 独立 RAG
  -> 才需要 scipal_code

通用代码 RAG
  -> 不做
```

一句话：

```text
代码 RAG 不替代 DSH 的代码搜索
它补的是 DSH 看不到的“外部知识 + 版本历史”
```

---

## 2. 为什么要修正

原计划把“代码 RAG”当成一个整体，容易滑向“全仓索引”。

但自己的仓库有更简单的强基线：

```text
当前工作区是最新事实
grep 能精确找符号/字符串/配置
read 能读指定行
LSP 能确认定义和引用
多轮工具调用能追跨文件链路
```

代码 RAG 在这个场景反而多出：

```text
索引陈旧
分支/未提交修改不一致
chunk 切断调用关系
需要增量索引 worker
可能召回旧 commit
```

对“改代码”尤其危险：

```text
RAG 召回旧写法
DSH read 到新代码
最终可能改错
```

---

## 3. 范围重新划分

| 代码来源 | 默认检索方式 | 是否需要独立 RAG |
|---|---|---|
| 当前 SciPal 仓库 | DSH grep/read/LSP/多轮 | 否 |
| 当前分支未提交代码 | DSH read | 否 |
| 多 repo 外部代码 | checkout + DSH，或外部索引 | 有条件 |
| 生信绘图配方 | BioViz Recipe RAG | 是 |
| 包版本/API/changelog | Version Tracker | 是 |
| 论文方法/仓库 | Method Card + RAG | 是 |
| 自动改用户项目 | 只给 patch proposal | 不自动做 |

---

## 4. DSH 原生检索方案

### 4.1 工具面

```text
repo_map        目录树、入口、测试、配置文件（可选，轻量）
grep            正则；files/content/count 三种输出
glob            按路径找文件
read            指定 offset/limit
lsp_definition  跳定义
lsp_references  找引用
lsp_symbols     文件/工作区符号（可选）
```

当前 DSH 工具面没有原生 LSP；需要额外接语言服务器。

Python 优先：

```text
pyright-langserver
或 jedi / rope 的 definition/references
```

Nextflow/WDL：

```text
没有成熟统一 LSP
只能 grep + parser + 配置键搜索
```

### 4.2 多轮策略

```text
1. repo_map 定位大致模块
2. grep 只取文件路径
3. read 指定行
4. LSP 确认定义/引用
5. 追 import/call/config
6. 读测试
7. 证据足够则停
```

停止条件：

```text
找到定义 + 调用点 + 配置/测试
或连续两轮没有新证据
```

上下文控制：

```text
grep 默认只回路径
content 模式只回匹配行附近
大范围搜索交给子 agent
```

### 4.3 证据纪律

最终回答应带：

```text
文件路径
行号
符号名
当前 branch/commit
```

不把“grep 到相似字符串”当成“确认调用关系”。

---

## 5. 什么时候才需要自己的代码索引

只有 DSH 基线被证明不够时，才考虑轻量补充：

```text
repo 很大，首轮 grep 延迟不可接受
跨大量包/多 repo，路径无法枚举
需要符号级全局索引，而不是文本匹配
```

即使如此，也优先：

```text
repo map
symbol index
LSP workspace symbols
```

而不是直接上向量 RAG。

### 先证伪

20 个自己的代码问题：

```text
PaperStore 在哪定义
trace 为什么曾 500
治理门禁入口在哪
插件迁移脚本在哪
某个配置项被谁读取
某个 workflow 输入从哪来
```

比较：

```text
A. DSH grep/read/多轮
B. A + repo map
C. B + LSP
D. 代码 RAG
```

如果 A/B/C 已够，D 不做。

---

## 6. 独立 RAG 的新边界

`scipal_code` 只放外部知识：

```text
recipes       生信绘图配方、样式、预览、数据契约
packages      包、版本、API、changelog
methods       论文/仓库/commit/license/方法卡
edges         recipe→package, method→repo, symbol→symbol
```

不放：

```text
当前 SciPal 仓库的整仓代码
当前分支未提交文件
docs/ 文档
scipal_rebuild 语料
```

查询时：

```text
当前仓库问题 -> DSH 工具
外部配方问题 -> BioViz RAG
版本兼容问题 -> Version Tracker
文献证据问题 -> 现有文献 RAG
```

---

## 7. 多跳分工

```text
DSH：
  决定是否多跳
  决定往哪跳
  读当前文件验证

RAG：
  提供外部配方
  提供版本/API
  提供方法卡
  提供图邻居（外部代码）
```

不建议：

```text
RAG 内部再跑一个自治 agent
RAG 直接改用户仓库
RAG 用旧 commit 回答当前代码问题
```

---

## 8. 修正后的阶段计划

### Phase 0：DSH 基线评测（2 天）

```text
20 个 SciPal 代码问题
A/B/C 三组
记录文件/符号命中、工具调用、token、延迟
```

### Phase 1：外部配方 RAG（3–5 天）

```text
20 个 Python 生信绘图配方
样式、预览、数据契约、版本约束
不索引自己的仓库
```

### Phase 2：DSH 工具（3–5 天）

```text
bioviz_search
bioviz_render
code_version_check
code_method_trace
```

### Phase 3：版本/方法追踪（后置）

```text
package version snapshot
changelog / API diff
method card
license / provenance
```

### Phase 4：Go / No-Go

```text
自己的代码：DSH 基线不够才加索引
外部配方：RAG 明显优于 DSH 直接搜网页/grep
版本：准确率 >= 90%，stale < 5%
```

---

## 9. 评测标准

### 自己的代码

```text
文件命中
符号命中
调用链正确
答案正确
工具调用次数
token
p95 延迟
```

### 外部配方

```text
代码可运行
图型正确
样式符合目标
人工偏好
版本兼容
```

### 版本

```text
API 是否存在
breaking change
迁移代码可运行
license 允许
```

---

## 10. 风险

| 风险 | 应对 |
|---|---|
| 把 grep 当语义搜索 | 明确问题类型；必要时加 repo map |
| LSP 语言覆盖不足 | Python 优先；其他语言降级 grep |
| 多轮工具循环失控 | 最大轮次 + 证据充分性停止 |
| 旧 commit 污染 | 只用当前 checkout；外部索引标 commit |
| 外部配方 license | 出处 + license + allowlist |
| RAG 自动改代码 | 只给 patch proposal |
| 索引维护成本 | 先不索引自己的仓库 |

---

## 11. 对主计划的修改

原计划中：

```text
scipal_code 索引代码库
```

修正为：

```text
scipal_code 只索引外部配方/版本/方法
自己的代码库交给 DSH 原生检索
```

主计划的其他部分继续有效：

```text
BioViz 优先
版本追踪后置
不做通用代码 RAG
不自动写入
```

---

## 12. 最终建议

```text
先让 DSH 用 grep + read + LSP + 多轮跑自己的仓库
用 20 个问题证明它够不够
够了就不做自己的代码 RAG

独立 RAG 只做：
  外部生信绘图配方
  包版本/API/changelog
  论文方法卡

实验 Phase C 优先
代码 RAG 之后再做 2–3 周 spike
```

---

## 13. 参考

- [Claude Code agentic grep 拆解](https://dbaplus.cn/news-141-7303-1.html)
- [CodeRAG-Bench](https://aclanthology.org/2025.findings-naacl.176/)
- [RepoBench](https://ar5iv.labs.arxiv.org/html/2306.03091)
- [RepoCoder](https://ar5iv.labs.arxiv.org/html/2303.12570)
- [LocAgent](https://aclanthology.org/2025.acl-long.426/)
- [Agentless](https://dl.acm.org/doi/full/10.1145/3715754)
- [BioCoder](http://export.arxiv.org/abs/2308.16458)
