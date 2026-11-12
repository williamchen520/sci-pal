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
- [计划-生信代码RAG](计划-生信代码RAG.md)
- [补充-生信代码RAG-DSH原生检索](补充-生信代码RAG-DSH原生检索.md)
- [实验-PhaseC-SciFact-300](实验-PhaseC-SciFact-300.md)
- [报告-PhaseC-SciFact](报告-PhaseC-SciFact.md)
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
