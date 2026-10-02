"""
Citation Formatter — 基于 CSL 引擎的专业参考文献格式化器（V25.7，完全重构）

**重要决策（2026-09-22 用户确认）**：
不使用手写的格式规则，完全采用专业的 CSL（Citation Style Language）引擎 + 官方 CSL 样式文件来渲染参考文献格式。
- CSL 是学术界的标准，Zotero/Mendeley/Pandoc 都用它
- 样式文件由官方维护，格式细节（斜体/缩写/标点/特殊规则）都经过验证
- 支持几千种期刊格式，只需下载对应的 .csl 文件
- 大模型只负责正文插引用标记，不碰参考文献列表，零幻觉

本模块封装 citeproc-py（纯 Python 的 CSL 1.0.2 处理器），提供：
1. PaperMetadata → CSL JSON 格式转换
2. CSL 样式文件加载和切换
3. 批量参考文献渲染
4. 元数据缺失检测和告警

依赖：
- citeproc-py（pip install citeproc-py）
- CSL 样式文件（放在 csl_styles/ 目录下，从 https://www.zotero.org/styles 下载）

用法：
  from services.review.citation_formatter import format_citation_list, PaperMetadata, metadata_to_csl_json

  metadata_list = [
      PaperMetadata(paper_id="p1", title="...", authors="John Smith; Alice Doe",
                    journal="Nature", year=2023, volume="46", issue="5", pages="1001-1015", doi="10.xxxx"),
  ]

  # APA 格式
  refs = format_citation_list(metadata_list, style="apa")

  # Nature 格式
  refs = format_citation_list(metadata_list, style="nature")

  # Vancouver 格式
  refs = format_citation_list(metadata_list, style="vancouver")
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────

@dataclass
class PaperMetadata:
    """论文元数据（从数据库 papers 表查询）。"""
    paper_id: str
    title: str = ""
    authors: str = ""          # 原始作者字符串，可能是 "张三; 李四; 王五" 或 "Zhang San, Li Si"
    journal: str = ""
    year: Optional[int] = None
    doi: str = ""
    volume: str = ""           # 卷（可能缺失）
    issue: str = ""            # 期（可能缺失）
    pages: str = ""            # 页码，如 "1001-1015"（可能缺失）
    paper_type: str = "J"     # 文献类型标识：J/C/M/D（CSL 中对应 article-journal/paper-conference/book/thesis）

    # 格式化过程中产生的中间字段
    parsed_authors: list[str] = field(default_factory=list)
    is_chinese: bool = False


# ──────────────────────────────────────────────
# 公共工具层（作者解析、元数据检测等，所有格式复用）
# ──────────────────────────────────────────────

def parse_authors(raw_authors: str) -> list[str]:
    """
    解析原始作者字符串为作者列表。

    支持的分隔符：分号、逗号、and、&、中文逗号、顿号
    返回清洗后的作者名列表（去除首尾空格、空字符串）。
    """
    if not raw_authors or not raw_authors.strip():
        return []

    s = raw_authors.strip()
    s = re.sub(r'\s+and\s+', ';', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*&\s*', ';', s)
    s = s.replace(',', ';')
    s = s.replace('，', ';')
    s = s.replace('、', ';')

    authors = [a.strip() for a in s.split(';') if a.strip()]
    return authors


def is_chinese_text(text: str) -> bool:
    """判断文本是否包含中文字符。"""
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def parse_author_to_csl_name(author: str) -> dict:
    """
    把单个作者名字符串转换成 CSL JSON 的 name 对象格式。

    CSL name 对象格式：
    - {"family": "Smith", "given": "John"} （英文，姓+名）
    - {"family": "张三", "given": ""} 或直接 {"literal": "张三"} （中文）

    英文作者的各种输入格式：
    - "John Smith" → {"family": "Smith", "given": "John"}
    - "Smith, John" → {"family": "Smith", "given": "John"}
    - "J. Smith" → {"family": "Smith", "given": "J."}
    - "Smith J" → {"family": "Smith", "given": "J"}
    """
    author = author.strip()
    if not author:
        return {}

    # 中文作者：用 literal 字段，CSL 引擎会原样输出
    if is_chinese_text(author):
        return {"literal": author}

    # 英文作者：尝试解析成 family + given
    # 格式1: "Smith, John" （姓在前，逗号分隔）
    if ',' in author:
        parts = author.split(',', 1)
        family = parts[0].strip()
        given = parts[1].strip() if len(parts) > 1 else ""
        if family:
            return {"family": family, "given": given}

    # 格式2: "John Smith" 或 "J. Smith" （名在前，空格分隔）
    parts = author.split()
    if len(parts) >= 2:
        # 假设最后一个词是姓，前面的都是名
        family = parts[-1]
        given = ' '.join(parts[:-1])
        return {"family": family, "given": given}
    elif len(parts) == 1:
        # 只有一个词，可能是只有姓
        return {"family": parts[0], "given": ""}

    return {"literal": author}


def get_missing_fields_report(metadata: PaperMetadata) -> list[str]:
    """
    检查元数据中缺失的必备字段，返回缺失字段列表（用于告警）。

    必备字段：作者、标题、期刊、年份
    可选字段：卷、期、页码、DOI（缺失只提示，不报错）
    """
    missing = []
    if not metadata.authors:
        missing.append("authors")
    if not metadata.title:
        missing.append("title")
    if not metadata.journal:
        missing.append("journal")
    if not metadata.year:
        missing.append("year")
    return missing


def build_metadata_from_db_row(row: dict) -> PaperMetadata:
    """从数据库查询结果（字典）构建 PaperMetadata 对象。"""
    return PaperMetadata(
        paper_id=row.get('paper_id', ''),
        title=row.get('title', '') or '',
        authors=row.get('authors', '') or '',
        journal=row.get('journal', '') or '',
        year=row.get('year'),
        doi=row.get('doi', '') or '',
        volume=row.get('volume', '') or '',
        issue=row.get('issue', '') or '',
        pages=row.get('pages', '') or '',
        paper_type=row.get('paper_type', 'J') or 'J',
    )


# ──────────────────────────────────────────────
# PaperMetadata → CSL JSON 转换
# ──────────────────────────────────────────────

def metadata_to_csl_json(metadata: PaperMetadata) -> dict:
    """
    把 PaperMetadata 转换成 CSL JSON 格式（citeproc-py 的输入格式）。

    CSL JSON 规范参考：https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html
    """
    # 解析作者
    raw_authors = parse_authors(metadata.authors)
    csl_authors = [parse_author_to_csl_name(a) for a in raw_authors]
    csl_authors = [a for a in csl_authors if a]

    # 文献类型映射
    type_map = {
        "J": "article-journal",
        "C": "paper-conference",
        "M": "book",
        "D": "thesis",
    }
    csl_type = type_map.get(metadata.paper_type, "article-journal")

    # 构建 CSL JSON 对象
    csl_item = {
        "id": metadata.paper_id,
        "type": csl_type,
        "title": metadata.title or metadata.paper_id,
    }

    if csl_authors:
        csl_item["author"] = csl_authors

    if metadata.journal:
        csl_item["container-title"] = metadata.journal

    if metadata.year:
        csl_item["issued"] = {"date-parts": [[metadata.year]]}

    if metadata.volume:
        csl_item["volume"] = str(metadata.volume)

    if metadata.issue:
        csl_item["issue"] = str(metadata.issue)

    if metadata.pages:
        csl_item["page"] = metadata.pages

    if metadata.doi:
        # 清洗 DOI，去除前缀
        doi = metadata.doi.strip()
        doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
        doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE)
        csl_item["DOI"] = doi

    return csl_item


def metadata_list_to_csl_json(metadata_list: list[PaperMetadata]) -> list[dict]:
    """批量把 PaperMetadata 列表转换成 CSL JSON 列表。"""
    return [metadata_to_csl_json(m) for m in metadata_list]


# ──────────────────────────────────────────────
# CSL 引擎封装
# ──────────────────────────────────────────────

# CSL 样式文件目录（相对于项目根目录）
DEFAULT_CSL_STYLES_DIR = "csl_styles"

# 样式名 → 文件名映射
STYLE_FILE_MAP = {
    "apa": "apa.csl",
    "nature": "nature.csl",
    "vancouver": "vancouver.csl",
    "gb-t7714": "gbt7714.csl",
    "gbt7714": "gbt7714.csl",
    "chinese": "gbt7714.csl",
    "国标": "gbt7714.csl",
    "icmje": "vancouver.csl",
    "apa7": "apa.csl",
    "apa-7": "apa.csl",
}


def _get_csl_styles_dir() -> Optional[str]:
    """获取 CSL 样式文件目录。优先在当前项目目录下找 csl_styles/。"""
    # 尝试多个可能的位置
    candidates = [
        os.path.join(os.getcwd(), DEFAULT_CSL_STYLES_DIR),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), DEFAULT_CSL_STYLES_DIR),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def _resolve_style_file(style_name: str) -> Optional[str]:
    """
    解析样式名对应的 CSL 文件路径。

    支持：
    - 样式别名（apa/nature/vancouver 等）
    - 直接的文件名（apa.csl）
    - 直接的文件路径（/path/to/style.csl）
    """
    if not style_name:
        return None

    style_name = style_name.strip()

    # 如果是直接的文件路径，直接返回
    if os.path.isfile(style_name):
        return style_name

    # 查找样式文件目录
    styles_dir = _get_csl_styles_dir()
    if not styles_dir:
        return None

    # 先尝试别名映射
    file_name = STYLE_FILE_MAP.get(style_name.lower())
    if file_name:
        file_path = os.path.join(styles_dir, file_name)
        if os.path.isfile(file_path):
            return file_path

    # 尝试直接加 .csl 后缀
    file_path = os.path.join(styles_dir, f"{style_name}.csl")
    if os.path.isfile(file_path):
        return file_path

    # 尝试直接作为文件名
    file_path = os.path.join(styles_dir, style_name)
    if os.path.isfile(file_path):
        return file_path

    return None


def get_supported_styles() -> list[dict[str, str]]:
    """返回当前可用的样式列表（扫描 csl_styles/ 目录下的 .csl 文件）。"""
    styles_dir = _get_csl_styles_dir()
    if not styles_dir:
        return []

    styles = []
    for file_name in sorted(os.listdir(styles_dir)):
        if file_name.endswith('.csl'):
            style_name = file_name[:-4]  # 去掉 .csl 后缀
            styles.append({
                "name": style_name,
                "file": file_name,
                "path": os.path.join(styles_dir, file_name),
            })
    return styles


def format_citation_list(metadata_list: list[PaperMetadata], style: str = "apa") -> list[str]:
    """
    批量格式化参考文献列表（使用 CSL 引擎渲染）。

    参数：
        metadata_list: 论文元数据列表
        style: 样式名（apa/nature/vancouver 等），默认 apa

    返回：
        格式化后的参考文献字符串列表

    异常：
        ImportError: citeproc-py 未安装
        FileNotFoundError: 样式文件不存在
    """
    # 检查 citeproc-py 是否安装
    try:
        from citeproc import CitationStylesBibliography, CitationStylesStyle, formatter
        from citeproc.source.json import CiteProcJSON
        from citeproc import Citation, CitationItem
    except ImportError:
        raise ImportError(
            "citeproc-py 未安装。请运行: pip install citeproc-py\n"
            "CSL 样式文件请从 https://www.zotero.org/styles 下载，放到 csl_styles/ 目录下。"
        )

    if not metadata_list:
        return []

    # 解析样式文件
    style_file = _resolve_style_file(style)
    if not style_file:
        available = get_supported_styles()
        available_names = [s['name'] for s in available]
        raise FileNotFoundError(
            f"找不到样式文件: '{style}'。\n"
            f"当前可用样式: {available_names}\n"
            f"请从 https://www.zotero.org/styles 下载对应的 .csl 文件，放到 csl_styles/ 目录下。"
        )

    # 转换成 CSL JSON
    csl_json_data = metadata_list_to_csl_json(metadata_list)

    # 加载 CSL 数据源
    bib_source = CiteProcJSON(csl_json_data)

    # 加载 CSL 样式
    csl_style = CitationStylesStyle(style_file, validate=False)

    # 创建参考文献对象
    bibliography = CitationStylesBibliography(csl_style, bib_source, formatter.plain)

    # 注册所有引用（按 paper_id 顺序）
    for metadata in metadata_list:
        bibliography.register(Citation([CitationItem(metadata.paper_id)]))

    # 渲染参考文献列表
    results = []
    for ref in bibliography.bibliography():
        # ref 可能是字符串或带格式的对象，转成字符串
        results.append(str(ref))

    return results


def format_citation(metadata: PaperMetadata, style: str = "apa", index: Optional[int] = None) -> str:
    """
    格式化单条参考文献（便捷函数，内部调用 format_citation_list）。

    参数：
        metadata: 论文元数据
        style: 样式名，默认 apa
        index: 序号（注意：CSL 样式会自己控制是否加序号，这个参数主要用于降级时）

    返回：
        格式化后的参考文献字符串
    """
    results = format_citation_list([metadata], style=style)
    if results:
        return results[0]

    # 降级：如果 CSL 引擎渲染失败，返回最简单的格式
    title = metadata.title or metadata.paper_id
    if index:
        return f"[{index}] {title}"
    return title


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("📝 Citation Formatter Test (V25.7 - CSL 引擎版)")
    print("=" * 60)

    # 测试元数据
    m1 = PaperMetadata(
        paper_id="paper_001",
        title="Deep learning for image recognition",
        authors="John Smith, Alice Doe, Bob Johnson, Charlie Brown",
        journal="Journal of Computer Science",
        year=2023,
        volume="46",
        issue="5",
        pages="1001-1015",
        doi="https://doi.org/10.11897/SP.J.1016.2023.01001",
    )

    m2 = PaperMetadata(
        paper_id="paper_002",
        title="STAT1 and interferon immunity",
        authors="Zhang San, Li Si",
        journal="Nature Immunology",
        year=2021,
    )

    m3 = PaperMetadata(
        paper_id="paper_003",
        title="基于深度学习的图像识别研究",
        authors="张三; 李四; 王五",
        journal="计算机学报",
        year=2023,
        volume="46",
        issue="5",
        pages="1001-1015",
    )

    metadata_list = [m1, m2, m3]

    # 测试 CSL JSON 转换
    print("\n--- CSL JSON 转换测试 ---")
    for m in metadata_list:
        csl = metadata_to_csl_json(m)
        print(f"  {m.paper_id}: type={csl['type']}, authors={len(csl.get('author', []))}人")

    # 测试作者解析
    print("\n--- 作者解析测试 ---")
    test_raw = [
        "张三; 李四; 王五",
        "Zhang San, Li Si, Wang Wu",
        "Zhang San and Li Si",
        "Smith, John",
        "J. Smith",
    ]
    for tr in test_raw:
        csl_name = parse_author_to_csl_name(tr)
        print(f"  {tr:30s} → {csl_name}")

    # 测试各种样式（如果 citeproc-py 和样式文件可用）
    print("\n--- CSL 引擎渲染测试 ---")
    try:
        available = get_supported_styles()
        print(f"  可用样式: {[s['name'] for s in available]}")

        for style_info in available:
            style_name = style_info['name']
            try:
                refs = format_citation_list(metadata_list, style=style_name)
                print(f"\n  === {style_name.upper()} 样式 ===")
                for i, ref in enumerate(refs, 1):
                    print(f"    {ref}")
            except Exception as e:
                print(f"  ⚠️  {style_name} 渲染失败: {e}")

        print("\n✅ CSL 引擎测试完成！")
    except ImportError as e:
        print(f"  ⚠️  citeproc-py 未安装: {e}")
        print("  请运行: pip install citeproc-py")
    except Exception as e:
        print(f"  ⚠️  测试失败: {e}")

    print("\n" + "=" * 60)
