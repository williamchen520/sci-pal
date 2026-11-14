#!/usr/bin/env python3
"""Build docs category indexes without moving files.

Why not git mv: 438 docs, 348 at docs/ root, 43 existing broken links. Moving
all paths would add link breakage and duplicate redirect stubs in the RAG
corpus. The index gives every document a category and a stable link while
keeping the original path intact.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

CATEGORIES = {
    "architecture": "架构规范",
    "plans": "阶段计划",
    "security": "安全复盘",
    "testing": "测试报告",
    "legacy": "废弃历史",
}

PARENT_RULES = {
    "archive": "legacy",
    "archive_legacy": "legacy",
    "publish": "legacy",
    "DSH官方参考": "legacy",
    "data-cards": "testing",
    "工作日志": "plans",
    "adr": "architecture",
    "plans": "plans",
    "en": "architecture",
}

KEYWORDS = [
    ("legacy", ["archive", "archive_legacy", "废弃", "历史", "旧", "legacy", "sqlite", "chroma", "归档", "备忘录", "退役"]),
    ("security", ["安全", "权限", "鉴权", "隔离", "备份", "恢复", "审计", "风险", "break-glass", "密钥", "dsn", "auth", "tenancy", "最小权限"]),
    ("testing", ["测试", "评测", "benchmark", "对账", "验收", "结果", "演练", "烟测", "质量", "回归", "指标", "eval"]),
    ("plans", ["计划", "路线", "phase", "阶段", "迁移", "执行顺序", "工作安排", "路线图", "里程碑", "工单", "next", "todo", "p0", "p1", "p2"]),
    ("architecture", ["架构", "路由", "schema", "数据层", "连接", "契约", "模块", "设计", "接口", "检索", "召回", "向量", "索引", "api"]),
]


def category(path: Path) -> str:
    for parent in path.relative_to(DOCS).parts[:-1]:
        if parent in PARENT_RULES:
            return PARENT_RULES[parent]
    text = str(path).lower()
    for name, words in KEYWORDS:
        if any(word in text for word in words):
            return name
    return "architecture"


def title_and_summary(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = path.stem
    summary = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#") and len(line) > 2:
            if title == path.stem:
                title = line.lstrip("#").strip()
            continue
        if line.startswith(("```", "|", ">", "<!--")):
            continue
        line = re.sub(r"[*_`\[\]]", "", line)
        summary = re.sub(r"\s+", " ", line).strip()
        if summary:
            break
    return title, summary[:140]


def link(from_file: Path, target: Path) -> str:
    return os.path.relpath(target, start=from_file.parent).replace("\\", "/")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    generated = {DOCS / "README.md", DOCS / "_index" / "all.md"}
    generated.update(DOCS / name / "README.md" for name in CATEGORIES)
    files = sorted(
        [path for path in DOCS.rglob("*.md") if path not in generated],
        key=lambda path: path.as_posix(),
    )
    rows = []
    for path in files:
        title, summary = title_and_summary(path)
        rows.append(
            {
                "path": path,
                "title": title,
                "summary": summary,
                "category": category(path),
            }
        )

    counts = Counter(row["category"] for row in rows)
    write(
        DOCS / "README.md",
        f"""# SciPal 文档索引

> 更新：2026-11-12 · 共 {len(rows)} 篇 Markdown  
> 分类是索引视图，不移动原文件；原路径与既有链接保持不变。

## 五大分类

| 分类 | 数量 | 索引 |
|---|---:|---|
| 架构规范 | {counts['architecture']} | [architecture/README.md](architecture/README.md) |
| 阶段计划 | {counts['plans']} | [plans/README.md](plans/README.md) |
| 安全复盘 | {counts['security']} | [security/README.md](security/README.md) |
| 测试报告 | {counts['testing']} | [testing/README.md](testing/README.md) |
| 废弃历史 | {counts['legacy']} | [legacy/README.md](legacy/README.md) |

完整清单：[_index/all.md](_index/all.md)

## 常用入口

- [架构与路由全景图](架构与路由全景图.md)
- [开发-模块手册](开发-模块手册.md)
- [开发流程规范](开发流程规范.md)
- [数据层隔离审计](数据层隔离审计.md)
- [恢复演练-20261112](恢复演练-20261112.md)
- [代码审查-20261112](代码审查-20261112.md)
- [工程治理门禁规范](工程治理门禁规范.md)
- [公共测试集选型](公共测试集选型.md)
- [实验-PhaseC-SciFact-300](实验-PhaseC-SciFact-300.md)
- [报告-PhaseC-SciFact](报告-PhaseC-SciFact.md)
- [实验-PhaseC-收口](实验-PhaseC-收口.md)
- [实验-PhaseC-Manifest](实验-PhaseC-Manifest.md)
- [实验-系统层可行性审计](实验-系统层可行性审计.md)
- [实验-PaperQA2-适配烟测](实验-PaperQA2-适配烟测.md)
- [报告-PaperQA2-适配烟测](报告-PaperQA2-适配烟测.md)
- [实验-BioViz-Recipe-RAG](实验-BioViz-Recipe-RAG.md)
- [实验-代码RAG-P2](实验-代码RAG-P2.md)
- [实验-代码RAG-P2.5](实验-代码RAG-P2.5.md)
- [实验-代码RAG-P3](实验-代码RAG-P3.md)
- [实验-代码RAG-P4](实验-代码RAG-P4.md)
- [实验-代码RAG-P5](实验-代码RAG-P5.md)
- [实验-代码RAG-P6](实验-代码RAG-P6.md)
- [实验-代码RAG-E0](实验-代码RAG-E0.md)
- [实验-代码RAG-E2](实验-代码RAG-E2.md)
- [实验-代码RAG-E3](实验-代码RAG-E3.md)
- [实验-代码RAG-E4](实验-代码RAG-E4.md)
- [实验-代码RAG-E5](实验-代码RAG-E5.md)
- [实验-代码RAG-A-UI](实验-代码RAG-A-UI.md)
- [计划-代码增强RAG-平台模块-v1](计划-代码增强RAG-平台模块-v1.md)
- [计划-代码RAG评测栈-v1](计划-代码RAG评测栈-v1.md)
- [设计-RAG控制面-v1](设计-RAG控制面-v1.md)
- [设计-SciPal-RAG控制面与科研追溯-v1](设计-SciPal-RAG控制面与科研追溯-v1.md)
- [设计-Paper-to-Code与主动科研工作流-v1](设计-Paper-to-Code与主动科研工作流-v1.md)
- [设计-scipal-paper-单篇论文分析插件-v1](设计-scipal-paper-单篇论文分析插件-v1.md)
- [实验-RAG控制面-R0](实验-RAG控制面-R0.md)
- [实验-RAG控制面-R1](实验-RAG控制面-R1.md)
- [实验-RAG控制面-R2](实验-RAG控制面-R2.md)
- [实验-RAG控制面-R3](实验-RAG控制面-R3.md)
- [实验-RAG控制面-R4](实验-RAG控制面-R4.md)
- [实验-RAG控制面-R5](实验-RAG控制面-R5.md)
- [实验-RAG控制面-R6](实验-RAG控制面-R6.md)
- [实验-RAG控制面-R6-live](实验-RAG控制面-R6-live.md)
- [实验-RAG控制面-R6.1](实验-RAG控制面-R6.1.md)
- [实验-RAG控制面-R6.2-UI](实验-RAG控制面-R6.2-UI.md)
- [实验-RAG控制面-R6.3](实验-RAG控制面-R6.3.md)
- [实验-RAG控制面-R6.4-docs](实验-RAG控制面-R6.4-docs.md)
- [实验-RAG控制面-R6.5-fanout](实验-RAG控制面-R6.5-fanout.md)
- [实验-RAG控制面-R7-裁决](实验-RAG控制面-R7-裁决.md)
- [实验-RAG控制面-R8-去重冲突导出](实验-RAG控制面-R8-去重冲突导出.md)
- [实验-RAG控制面-R9-审计与RO-Crate](实验-RAG控制面-R9-审计与RO-Crate.md)
- [实验-RAG控制面-R10-reviewer](实验-RAG控制面-R10-reviewer.md)
- [实验-RAG控制面-R11-双人kappa](实验-RAG控制面-R11-双人kappa.md)
- [实验-RAG控制面-R12-指派](实验-RAG控制面-R12-指派.md)
- [实验-RAG控制面-R13-最终确认](实验-RAG控制面-R13-最终确认.md)
- [实验-RAG控制面-R14-封存签名](实验-RAG控制面-R14-封存签名.md)
- [实验-RAG控制面-R15-签名导出](实验-RAG控制面-R15-签名导出.md)
- [实验-RAG控制面-R16-CSV](实验-RAG控制面-R16-CSV.md)
- [实验-RAG控制面-R17-独立验证](实验-RAG控制面-R17-独立验证.md)
- [实验-RAG控制面-R18-公钥目录](实验-RAG控制面-R18-公钥目录.md)
- [实验-Paper-to-Code-HCC-LAM案例](实验-Paper-to-Code-HCC-LAM案例.md)
- [实验-Paper-to-Code-HCC-基因组案例](实验-Paper-to-Code-HCC-基因组案例.md)
- [实验-HTML解析器](实验-HTML解析器.md)
- [实验-Sentence-Tree](实验-Sentence-Tree.md)
- [实验-Embedding输入审计](实验-Embedding输入审计.md)
- [实验-Paper-Reader-API](实验-Paper-Reader-API.md)
- [实验-Sentence-Evidence](实验-Sentence-Evidence.md)
- [实验-Paper-Analysis](实验-Paper-Analysis.md)
- [实验-Paper-Code-Links](实验-Paper-Code-Links.md)
- [实验-Paper-Code-Bindings](实验-Paper-Code-Bindings.md)
- [实验-R-Parser-v1](实验-R-Parser-v1.md)
- [实验-Paper-Module-Map](实验-Paper-Module-Map.md)
- [实验-第二篇论文-端到端](实验-第二篇论文-端到端.md)
- [实验-Paper-Plugin-Smoke](实验-Paper-Plugin-Smoke.md)
- [实验-Paper-Data-Flow](实验-Paper-Data-Flow.md)
- [实验-Rmd-Mixed](实验-Rmd-Mixed.md)
- [实验-Scipal-Paper-MCP](实验-Scipal-Paper-MCP.md)
- [实验-Replication-Plan](实验-Replication-Plan.md)
- [实验-证据质量修复](实验-证据质量修复.md)
- [实验-全库Caption审计](实验-全库Caption审计.md)
- [实验-Results-Fallback](实验-Results-Fallback.md)
- [实验-Section-Types](实验-Section-Types.md)
- [实验-Section-Type-覆盖](实验-Section-Type-覆盖.md)
- [实验-Paper-Sources](实验-Paper-Sources.md)
- [实验-JATS-Native](实验-JATS-Native.md)
- [实验-HTML-Native](实验-HTML-Native.md)
- [实验-PDF-Native](实验-PDF-Native.md)
- [实验-Federation](实验-Federation.md)
- [讨论-租户独立建库与插件化导入管线](讨论-租户独立建库与插件化导入管线.md)
- [讨论-04-CodeRAG是否按语言建库](讨论-04-CodeRAG是否按语言建库.md)
- [讨论-05-文献监控与自动入库](讨论-05-文献监控与自动入库.md)
- [实验-Paper-Section-API](实验-Paper-Section-API.md)
- [实验-Cross-Language-Edges](实验-Cross-Language-Edges.md)
- [实验-RAG控制面-服务持久化](实验-RAG控制面-服务持久化.md)
- [Changelog](Changelog.md)

## 为什么不立即 git mv

```text
438 篇文档，348 篇在 docs/ 根目录
现有 43 个本地链接已经断开
全量移动会新增断链，并让 RAG 语料出现重复/重定向
```

所以先建立分类索引、时间轴和稳定入口；物理迁移等链接检查器就绪后再做。
""",
    )

    for name, label in CATEGORIES.items():
        selected = [row for row in rows if row["category"] == name]
        lines = [
            f"# {label}",
            "",
            f"> 共 {len(selected)} 篇 · 分类索引，文件原路径不变",
            "",
            "| 标题 | 摘要 | 文档 |",
            "|---|---|---|",
        ]
        for row in selected:
            lines.append(
                f"| {row['title']} | {row['summary']} | [{row['path'].name}]({link(DOCS / name / 'README.md', row['path'])}) |"
            )
        write(DOCS / name / "README.md", "\n".join(lines) + "\n")

    lines = [
        "# 全部文档",
        "",
        f"> 共 {len(rows)} 篇 · 2026-11-12",
        "",
        "| 分类 | 标题 | 摘要 | 文档 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {CATEGORIES[row['category']]} | {row['title']} | {row['summary']} | [{row['path'].name}]({link(DOCS / '_index' / 'all.md', row['path'])}) |"
        )
    write(DOCS / "_index" / "all.md", "\n".join(lines) + "\n")
    print(f"indexed {len(rows)} docs; {dict(counts)}")


if __name__ == "__main__":
    main()
