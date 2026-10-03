#!/usr/bin/env python3
"""
PMC 全文 XML 解析脚本 V1.0

按照 PMC 全文 XML 的结构提取信息：
  - 标题
  - 摘要
  - 正文（按章节、段落）
  - 参考文献
  - 图表

并且！保留：
  - 段落之间的关系（哪个段落属于哪个章节）
  - 句子之间的关系（哪个句子属于哪个段落）

使用方法：
  python scripts/parse_pmc_xml.py <xml文件>
  python scripts/parse_pmc_xml.py documents_xml/PMC12956738.xml
"""

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def split_sentences(text: str) -> list[str]:
    """
    按句号切分句子

    Args:
        text: 文本

    Returns:
        句子列表
    """
    # 简单的句子切分：按句号、问号、感叹号切分
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # 过滤空句子
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def parse_pmc_xml(xml_path: str) -> dict:
    """
    解析 PMC 全文 XML

    Args:
        xml_path: XML 文件路径

    Returns:
        解析结果字典
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # 找到 <article> 标签
    article = root.find(".//article")
    if article is None:
        raise ValueError("找不到 <article> 标签")

    result = {
        "pmcid": None,
        "pmid": None,
        "doi": None,
        "title": None,
        "authors": [],  # 作者列表
        "journal": None,  # 期刊名
        "publish_date": None,  # 发表日期
        "keywords": [],  # 关键词列表
        "abstract": [],  # 摘要段落列表
        "body": [],  # 正文章节列表
        "figures": [],  # 图表列表
        "tables": [],  # 表格列表
        "references": [],  # 参考文献列表
    }

    # ============================================================
    # 提取文章元数据
    # ============================================================
    article_meta = article.find(".//article-meta")
    if article_meta is not None:
        # PMCID
        pmcid_elem = article_meta.find(".//article-id[@pub-id-type='pmcid']")
        if pmcid_elem is not None:
            result["pmcid"] = pmcid_elem.text

        # PMID
        pmid_elem = article_meta.find(".//article-id[@pub-id-type='pmid']")
        if pmid_elem is not None:
            result["pmid"] = pmid_elem.text

        # DOI
        doi_elem = article_meta.find(".//article-id[@pub-id-type='doi']")
        if doi_elem is not None:
            result["doi"] = doi_elem.text

        # 标题
        title_elem = article_meta.find(".//article-title")
        if title_elem is not None:
            result["title"] = "".join(title_elem.itertext()).strip()

        # 作者
        contrib_group_elem = article_meta.find(".//contrib-group")
        if contrib_group_elem is not None:
            for contrib_elem in contrib_group_elem.findall("./contrib[@contrib-type='author']"):
                name_elem = contrib_elem.find(".//name")
                if name_elem is not None:
                    given_names = name_elem.find(".//given-names")
                    surname = name_elem.find(".//surname")
                    if given_names is not None and surname is not None:
                        author_name = f"{given_names.text} {surname.text}"
                        result["authors"].append(author_name)

        # 期刊
        journal_meta_elem = article.find(".//journal-meta")
        if journal_meta_elem is not None:
            journal_title_elem = journal_meta_elem.find(".//journal-title")
            if journal_title_elem is not None:
                result["journal"] = journal_title_elem.text

        # 发表日期
        pub_date_elem = article_meta.find(".//pub-date")
        if pub_date_elem is not None:
            year_elem = pub_date_elem.find(".//year")
            month_elem = pub_date_elem.find(".//month")
            day_elem = pub_date_elem.find(".//day")
            year = year_elem.text if year_elem is not None else None
            month = month_elem.text if month_elem is not None else None
            day = day_elem.text if day_elem is not None else None
            if year and month and day:
                result["publish_date"] = f"{year}-{month}-{day}"
            elif year:
                result["publish_date"] = year

        # 关键词
        kw_group_elem = article_meta.find(".//kwd-group")
        if kw_group_elem is not None:
            for kw_elem in kw_group_elem.findall("./kwd"):
                kw_text = "".join(kw_elem.itertext()).strip()
                if kw_text:
                    result["keywords"].append(kw_text)

    # ============================================================
    # 提取摘要
    # ============================================================
    abstract_elem = article.find(".//abstract")
    if abstract_elem is not None:
        for p_elem in abstract_elem.findall(".//p"):
            text = "".join(p_elem.itertext()).strip()
            if text:
                sentences = split_sentences(text)
                result["abstract"].append({
                    "text": text,
                    "sentences": sentences,
                })

    # ============================================================
    # 提取正文
    # ============================================================
    body_elem = article.find(".//body")
    if body_elem is not None:
        def parse_sec(sec_elem, level=1):
            """递归解析章节"""
            sec = {
                "level": level,
                "title": None,
                "paragraphs": [],  # 段落列表
                "subsections": [],  # 子章节列表
            }

            # 章节标题
            title_elem = sec_elem.find("./title")
            if title_elem is not None:
                sec["title"] = "".join(title_elem.itertext()).strip()

            # 段落
            for p_elem in sec_elem.findall("./p"):
                text = "".join(p_elem.itertext()).strip()
                if text:
                    sentences = split_sentences(text)
                    sec["paragraphs"].append({
                        "text": text,
                        "sentences": sentences,
                    })

            # 子章节
            for subsec_elem in sec_elem.findall("./sec"):
                subsec = parse_sec(subsec_elem, level + 1)
                sec["subsections"].append(subsec)

            return sec

        # 解析顶级章节
        for sec_elem in body_elem.findall("./sec"):
            sec = parse_sec(sec_elem, level=1)
            result["body"].append(sec)

    # ============================================================
    # 提取图表
    # ============================================================
    for fig_elem in article.findall(".//fig"):
        fig_id = fig_elem.get("id")
        # 提取图表标题
        fig_caption_elem = fig_elem.find(".//caption")
        fig_caption = None
        if fig_caption_elem is not None:
            fig_caption = "".join(fig_caption_elem.itertext()).strip()
        result["figures"].append({
            "id": fig_id,
            "caption": fig_caption,
        })

    # ============================================================
    # 提取表格
    # ============================================================
    for table_elem in article.findall(".//table-wrap"):
        table_id = table_elem.get("id")
        # 提取表格标题
        table_caption_elem = table_elem.find(".//caption")
        table_caption = None
        if table_caption_elem is not None:
            table_caption = "".join(table_caption_elem.itertext()).strip()
        result["tables"].append({
            "id": table_id,
            "caption": table_caption,
        })

    # ============================================================
    # 提取参考文献
    # ============================================================
    ref_list_elem = article.find(".//ref-list")
    if ref_list_elem is not None:
        for ref_elem in ref_list_elem.findall("./ref"):
            ref_id = ref_elem.get("id")
            # 提取参考文献文本
            mixed_citation_elem = ref_elem.find(".//mixed-citation")
            if mixed_citation_elem is not None:
                text = "".join(mixed_citation_elem.itertext()).strip()
                result["references"].append({
                    "id": ref_id,
                    "text": text,
                })

    return result


def main():
    parser = argparse.ArgumentParser(description="PMC 全文 XML 解析脚本")
    parser.add_argument("xml_path", type=str, help="XML 文件路径")
    parser.add_argument("--output", type=str, help="输出 JSON 文件路径（可选）")

    args = parser.parse_args()

    print(f"📄 解析: {args.xml_path}")

    result = parse_pmc_xml(args.xml_path)

    # 打印结果
    print(f"\n{'='*60}")
    print(f"✅ 解析完成！")
    print(f"{'='*60}")
    print(f"  PMCID: {result['pmcid']}")
    print(f"  PMID: {result['pmid']}")
    print(f"  DOI: {result['doi']}")
    print(f"  标题: {result['title']}")
    print(f"  作者: {', '.join(result['authors'][:5])}{'...' if len(result['authors']) > 5 else ''}")
    print(f"  期刊: {result['journal']}")
    print(f"  发表日期: {result['publish_date']}")
    print(f"  关键词: {', '.join(result['keywords'][:5])}{'...' if len(result['keywords']) > 5 else ''}")
    print(f"  摘要段落数: {len(result['abstract'])}")
    print(f"  顶级章节数: {len(result['body'])}")
    print(f"  图表数: {len(result['figures'])}")
    print(f"  表格数: {len(result['tables'])}")
    print(f"  参考文献数: {len(result['references'])}")

    # 打印摘要内容
    if result['abstract']:
        print(f"\n{'='*60}")
        print(f"📝 摘要内容：")
        print(f"{'='*60}")
        for i, p in enumerate(result['abstract']):
            print(f"\n段落 {i+1}:")
            print(f"  {p['text'][:200]}...")  # 只打印前 200 个字符
            print(f"  句子数: {len(p['sentences'])}")

    # 打印正文内容
    if result['body']:
        print(f"\n{'='*60}")
        print(f"📖 正文内容：")
        print(f"{'='*60}")
        for i, sec in enumerate(result['body']):
            print(f"\n章节 {i+1}: {sec['title']}")
            print(f"  段落数: {len(sec['paragraphs'])}")
            if sec['paragraphs']:
                first_para = sec['paragraphs'][0]
                print(f"  第一段: {first_para['text'][:200]}...")  # 只打印前 200 个字符
                print(f"  句子数: {len(first_para['sentences'])}")

    # 保存到 JSON
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存到: {args.output}")


if __name__ == "__main__":
    main()
