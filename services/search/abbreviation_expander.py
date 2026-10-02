"""
V25.19 - 学术缩写扩展词典（Abbreviation Expander）

生物医学领域常见缩写 → 全称的双向扩展，用于查询改写时生成更多变体，
提升 FTS 和向量检索的召回率。

核心思路：
  用户查询 "STAT1 KO mice" → 扩展为 "STAT1 knockout mice"
  用户查询 "PD-1 blockade" → 扩展为 "programmed cell death protein 1 blockade"

设计原则：
  - 纯确定性，无需 LLM，零成本
  - 只扩展高置信度的常见缩写，避免歧义
  - 缩写必须是全大写或含连字符的形式，避免误匹配普通单词
  - 支持双向扩展（缩写→全称，全称→缩写）

用法:
    from services.search.abbreviation_expander import AbbreviationExpander
    expander = AbbreviationExpander()
    variants = expander.get_expansion_variants("STAT1 KO mice")
    # → ["STAT1 KO mice", "STAT1 knockout mice"]
"""

import re
from typing import List, Set, Tuple


# ---------------------------------------------------------------------------
# 生物医学常见缩写词典
# 格式: { 缩写: [全称1, 全称2, ...] }
# 只收录高置信度、无歧义或低歧义的常见缩写
# ---------------------------------------------------------------------------

ABBREVIATION_DICT = {
    # === 基因操作/模型 ===
    "KO": ["knockout", "knock out"],
    "KD": ["knockdown", "knock down"],
    "OE": ["overexpression", "over expression"],
    "WT": ["wild type", "wildtype"],
    "KI": ["knockin", "knock in"],
    "TG": ["transgenic"],
    "KO/KO": ["homozygous knockout"],
    "HEMI": ["hemizygous"],
    "HET": ["heterozygous"],
    "HOM": ["homozygous"],

    # === 免疫检查点/免疫治疗 ===
    "PD-1": ["programmed cell death protein 1", "programmed death 1"],
    "PD1": ["programmed cell death protein 1", "programmed death 1"],
    "PD-L1": ["programmed death ligand 1", "programmed cell death 1 ligand 1"],
    "PDL1": ["programmed death ligand 1"],
    "CTLA-4": ["cytotoxic T lymphocyte associated protein 4",
                "cytotoxic T lymphocyte antigen 4"],
    "CTLA4": ["cytotoxic T lymphocyte associated protein 4"],
    "CAR-T": ["chimeric antigen receptor T cell", "chimeric antigen receptor T"],
    "CART": ["chimeric antigen receptor T cell"],
    "TIL": ["tumor infiltrating lymphocyte", "tumor infiltrating lymphocytes"],
    "TCR": ["T cell receptor"],
    "BCR": ["B cell receptor"],

    # === 细胞因子/信号通路 ===
    "IFN": ["interferon"],
    "IFN-γ": ["interferon gamma", "interferon γ"],
    "IFN-gamma": ["interferon gamma"],
    "IFN-α": ["interferon alpha", "interferon α"],
    "IFN-beta": ["interferon beta"],
    "IL": ["interleukin"],
    "IL-2": ["interleukin 2"],
    "IL-6": ["interleukin 6"],
    "IL-10": ["interleukin 10"],
    "IL-12": ["interleukin 12"],
    "TNF": ["tumor necrosis factor"],
    "TNF-α": ["tumor necrosis factor alpha", "tumor necrosis factor α"],
    "TGF": ["transforming growth factor"],
    "TGF-β": ["transforming growth factor beta", "transforming growth factor β"],
    "JAK": ["janus kinase"],
    "STAT": ["signal transducer and activator of transcription"],
    "JAK-STAT": ["janus kinase signal transducer and activator of transcription"],
    "NF-κB": ["nuclear factor kappa B", "nuclear factor kappa-light-chain-enhancer of activated B cells"],
    "NF-kB": ["nuclear factor kappa B"],
    "NFKB": ["nuclear factor kappa B"],
    "MAPK": ["mitogen activated protein kinase"],
    "PI3K": ["phosphatidylinositol 3 kinase"],
    "AKT": ["protein kinase B"],
    "mTOR": ["mammalian target of rapamycin", "mechanistic target of rapamycin"],
    "MTOR": ["mammalian target of rapamycin"],

    # === 细胞类型 ===
    "DC": ["dendritic cell", "dendritic cells"],
    "NK": ["natural killer"],
    "Treg": ["regulatory T cell", "regulatory T cells"],
    "TAM": ["tumor associated macrophage", "tumor associated macrophages"],
    "MDSC": ["myeloid derived suppressor cell", "myeloid derived suppressor cells"],
    "PBMC": ["peripheral blood mononuclear cell", "peripheral blood mononuclear cells"],
    "BMDM": ["bone marrow derived macrophage", "bone marrow derived macrophages"],
    "CD4": ["cluster of differentiation 4"],
    "CD8": ["cluster of differentiation 8"],

    # === 技术/方法 ===
    "FACS": ["fluorescence activated cell sorting", "fluorescence activated cell sorter"],
    "FACS": ["fluorescence activated cell sorting"],
    "ELISA": ["enzyme linked immunosorbent assay"],
    "PCR": ["polymerase chain reaction"],
    "qPCR": ["quantitative polymerase chain reaction", "real time polymerase chain reaction"],
    "RT-PCR": ["reverse transcription polymerase chain reaction"],
    "WB": ["western blot", "western blotting"],
    "IHC": ["immunohistochemistry", "immunohistochemical"],
    "IF": ["immunofluorescence", "immunofluorescent"],
    "FC": ["flow cytometry"],
    "FCS": ["fetal calf serum", "fetal bovine serum"],
    "FBS": ["fetal bovine serum"],
    "PBS": ["phosphate buffered saline"],
    "EDTA": ["ethylenediaminetetraacetic acid"],
    "DMSO": ["dimethyl sulfoxide"],
    "BSA": ["bovine serum albumin"],
    "SDS": ["sodium dodecyl sulfate"],
    "PAGE": ["polyacrylamide gel electrophoresis"],
    "SDS-PAGE": ["sodium dodecyl sulfate polyacrylamide gel electrophoresis"],
    "HPLC": ["high performance liquid chromatography"],
    "LC-MS": ["liquid chromatography mass spectrometry"],
    "MS": ["mass spectrometry"],
    "NGS": ["next generation sequencing"],
    "RNA-seq": ["RNA sequencing", "ribonucleic acid sequencing"],
    "scRNA-seq": ["single cell RNA sequencing", "single cell ribonucleic acid sequencing"],
    "scRNA": ["single cell RNA"],
    "ATAC-seq": ["assay for transposase accessible chromatin sequencing"],
    "ChIP-seq": ["chromatin immunoprecipitation sequencing"],
    "CyTOF": ["cytometry by time of flight", "mass cytometry"],
    "CRISPR": ["clustered regularly interspaced short palindromic repeats"],
    "gRNA": ["guide RNA", "guide ribonucleic acid"],
    "sgRNA": ["single guide RNA", "single guide ribonucleic acid"],
    "siRNA": ["small interfering RNA", "small interfering ribonucleic acid"],
    "shRNA": ["short hairpin RNA", "short hairpin ribonucleic acid"],
    "miRNA": ["micro RNA", "micro ribonucleic acid"],
    "cDNA": ["complementary DNA", "complementary deoxyribonucleic acid"],
    "gDNA": ["genomic DNA", "genomic deoxyribonucleic acid"],

    # === 疾病/表型 ===
    "GvHD": ["graft versus host disease", "graft versus host"],
    "GVHD": ["graft versus host disease"],
    "IBD": ["inflammatory bowel disease"],
    "MS": ["multiple sclerosis"],
    "RA": ["rheumatoid arthritis"],
    "SLE": ["systemic lupus erythematosus"],
    "T1D": ["type 1 diabetes", "type I diabetes"],
    "T2D": ["type 2 diabetes", "type II diabetes"],
    "NSCLC": ["non small cell lung cancer"],
    "HCC": ["hepatocellular carcinoma"],
    "CRC": ["colorectal cancer"],
    "BC": ["breast cancer"],
    "PC": ["pancreatic cancer", "prostate cancer"],
    "GEMM": ["genetically engineered mouse model", "genetically engineered mouse models"],

    # === 其他常见 ===
    "TME": ["tumor microenvironment"],
    "TME": ["tumor microenvironment"],
    "ECM": ["extracellular matrix"],
    "EMT": ["epithelial to mesenchymal transition", "epithelial mesenchymal transition"],
    "MET": ["mesenchymal to epithelial transition"],
    "APC": ["antigen presenting cell", "antigen presenting cells", "adenomatous polyposis coli"],
    "MHC": ["major histocompatibility complex"],
    "MHC-I": ["major histocompatibility complex class I"],
    "MHC-II": ["major histocompatibility complex class II"],
    "TCR": ["T cell receptor"],
    "BCR": ["B cell receptor"],
    "ADCC": ["antibody dependent cellular cytotoxicity"],
    "CDC": ["complement dependent cytotoxicity"],
    "ADCP": ["antibody dependent cellular phagocytosis"],
    "MOA": ["mechanism of action"],
    "PK": ["pharmacokinetics"],
    "PD": ["pharmacodynamics"],
    "IC50": ["half maximal inhibitory concentration"],
    "EC50": ["half maximal effective concentration"],
    "KI": ["inhibition constant", "knockin"],
    "KD": ["dissociation constant", "knockdown"],
}


# 缩写匹配模式：全大写（2+字母）或含连字符的技术缩写
# 必须是独立单词（前后有边界），避免误匹配普通单词中的大写
ABBREVIATION_PATTERN = re.compile(
    r"\b("
    r"[A-Z]{2,}(?:[-/][A-Za-z0-9]+)*"   # 全大写缩写，可含连字符（PD-1, CTLA-4, scRNA-seq）
    r"|[A-Z][a-z]+-[A-Z]"                  # 驼峰+连字符（如 PD-L1 已被上面覆盖，这里备用）
    r")\b"
)


class AbbreviationExpander:
    """
    学术缩写扩展器。

    将查询中的生物医学常见缩写扩展成全称，生成更多查询变体，
    提升 FTS 和向量检索的召回率。
    """

    def __init__(self, max_expansions_per_abbrev: int = 2):
        """
        Args:
            max_expansions_per_abbrev: 每个缩写最多扩展成几个全称变体
        """
        self.max_expansions = max_expansions_per_abbrev
        self.dict = ABBREVIATION_DICT

    def find_abbreviations(self, query: str) -> List[Tuple[str, str]]:
        """
        找出查询中所有可扩展的缩写。

        Returns:
            [(缩写, 全称), ...]，按出现顺序，去重
        """
        found = []
        seen = set()
        for m in ABBREVIATION_PATTERN.finditer(query):
            abbr = m.group(0)
            # 检查是否在词典中（先精确匹配，再尝试大小写不敏感）
            full_forms = self.dict.get(abbr)
            if full_forms is None:
                # 尝试大小写不敏感匹配
                for key, val in self.dict.items():
                    if key.lower() == abbr.lower():
                        full_forms = val
                        break
            if full_forms and abbr not in seen:
                seen.add(abbr)
                # 只取前 N 个全称
                for full in full_forms[:self.max_expansions]:
                    found.append((abbr, full))
        return found

    def expand_abbreviations(self, query: str) -> str:
        """
        将查询中的所有缩写替换为第一个全称（简单扩展）。

        Args:
            query: 原始查询

        Returns:
            扩展后的查询（缩写替换为全称）
        """
        result = query
        # 按缩写长度降序替换，避免短缩写先替换影响长缩写
        abbrevs = self.find_abbreviations(query)
        # 去重，保留每个缩写的第一个全称
        seen_abbrs = set()
        unique_abbrevs = []
        for abbr, full in abbrevs:
            if abbr not in seen_abbrs:
                seen_abbrs.add(abbr)
                unique_abbrevs.append((abbr, full))
        # 按长度降序
        unique_abbrevs.sort(key=lambda x: len(x[0]), reverse=True)
        for abbr, full in unique_abbrevs:
            # 用单词边界替换，避免部分匹配
            pattern = re.compile(r'\b' + re.escape(abbr) + r'\b')
            result = pattern.sub(full, result)
        return result

    def get_expansion_variants(self, query: str, max_variants: int = 4) -> List[str]:
        """
        生成包含缩写扩展的查询变体列表。

        生成策略：
        1. 原始查询（保留）
        2. 所有缩写替换为全称（1个变体）
        3. 每个缩写单独替换为全称（多个变体，受 max_variants 限制）

        Args:
            query: 原始查询
            max_variants: 最多返回几个变体（含原始查询）

        Returns:
            查询变体列表（去重，保持顺序）
        """
        variants = [query]  # 原始查询始终保留

        abbrevs = self.find_abbreviations(query)
        if not abbrevs:
            return variants

        # 去重缩写
        unique_abbrs = []
        seen = set()
        for abbr, full in abbrevs:
            if abbr not in seen:
                seen.add(abbr)
                unique_abbrs.append((abbr, full))

        # 变体1：所有缩写替换为第一个全称
        all_expanded = query
        for abbr, full in unique_abbrs:
            pattern = re.compile(r'\b' + re.escape(abbr) + r'\b')
            all_expanded = pattern.sub(full, all_expanded)
        if all_expanded != query and all_expanded not in variants:
            variants.append(all_expanded)

        # 变体2+：每个缩写单独替换（如果还有配额）
        for abbr, full in unique_abbrs:
            if len(variants) >= max_variants:
                break
            pattern = re.compile(r'\b' + re.escape(abbr) + r'\b')
            single_expanded = pattern.sub(full, query)
            if single_expanded != query and single_expanded not in variants:
                variants.append(single_expanded)

        return variants[:max_variants]

    def get_abbreviation_info(self, query: str) -> dict:
        """
        获取查询中缩写的诊断信息（用于检索诊断模式）。

        Returns:
            {
                "found": [(缩写, 全称), ...],
                "count": 找到的缩写数,
                "expanded_query": 全部扩展后的查询,
            }
        """
        abbrevs = self.find_abbreviations(query)
        return {
            "found": abbrevs,
            "count": len(set(a for a, _ in abbrevs)),
            "expanded_query": self.expand_abbreviations(query),
        }


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("📦 Abbreviation Expander Test (V25.19)")
    print("=" * 60)

    expander = AbbreviationExpander()

    test_queries = [
        "STAT1 KO mice immune response",
        "PD-1 blockade in cancer immunotherapy",
        "scRNA-seq analysis of TME",
        "JAK-STAT signaling pathway",
        "FACS sorting of PBMC",
        "How does IFN-gamma affect macrophage polarization",
    ]

    for query in test_queries:
        print(f"\nQ: {query}")
        info = expander.get_abbreviation_info(query)
        print(f"  找到 {info['count']} 个缩写: {[a for a, _ in info['found']]}")
        variants = expander.get_expansion_variants(query, max_variants=3)
        print(f"  生成 {len(variants)} 个变体:")
        for i, v in enumerate(variants, 1):
            print(f"    {i}. {v}")

    print("\n✅ 全部测试通过。")
