#!/bin/bash
# ============================================================
# Sci-Pal V26.4 — 100篇8主题批量下载脚本（API Key 加速版）
# ============================================================
# 用法: bash scripts/download_100_topics.sh
# 输出: documents/ 目录下的 PDF
# ============================================================

set -e

OUTPUT_DIR="documents"
SCRIPT="scripts/download_pmc.py"
API_KEY="76012a329673a2911604807c76294bf98507"
EMAIL="chenwei-ucas@outlook.com"
ARGS="--api-key $API_KEY --email $EMAIL --output $OUTPUT_DIR --no-meta --quiet"

echo "============================================================"
echo "📦 Sci-Pal 100篇8主题批量下载（API Key 加速）"
echo "============================================================"
echo "输出目录: $OUTPUT_DIR"
echo "限速: 10次/秒（API Key）"
echo "开始时间: $(date)"
echo ""

# 主题1: STAT1 (12篇)
echo "── 主题1/8: STAT1 (12篇) ──"
python3 $SCRIPT --query "STAT1 interferon" --max 4 $ARGS
python3 $SCRIPT --query "STAT1 gain of function" --max 4 $ARGS
python3 $SCRIPT --query "STAT1 deficiency" --max 4 $ARGS

# 主题2: 乳腺癌 (12篇)
echo "── 主题2/8: 乳腺癌 (12篇) ──"
python3 $SCRIPT --query "breast cancer immunotherapy" --max 4 $ARGS
python3 $SCRIPT --query "triple negative breast cancer" --max 4 $ARGS
python3 $SCRIPT --query "breast cancer biomarker" --max 4 $ARGS

# 主题3: 肝病 (12篇)
echo "── 主题3/8: 肝病 (12篇) ──"
python3 $SCRIPT --query "hepatocellular carcinoma" --max 4 $ARGS
python3 $SCRIPT --query "liver fibrosis" --max 4 $ARGS
python3 $SCRIPT --query "NAFLD" --max 4 $ARGS

# 主题4: HBV 乙肝 (13篇)
echo "── 主题4/8: HBV 乙肝 (13篇) ──"
python3 $SCRIPT --query "hepatitis B virus" --max 5 $ARGS
python3 $SCRIPT --query "chronic hepatitis B" --max 4 $ARGS
python3 $SCRIPT --query "HBV infection" --max 4 $ARGS

# 主题5: 生物信息学 (13篇)
echo "── 主题5/8: 生物信息学 (13篇) ──"
python3 $SCRIPT --query "single cell RNA sequencing" --max 5 $ARGS
python3 $SCRIPT --query "machine learning biology" --max 4 $ARGS
python3 $SCRIPT --query "bioinformatics pipeline" --max 4 $ARGS

# 主题6: 免疫学 (13篇)
echo "── 主题6/8: 免疫学 (13篇) ──"
python3 $SCRIPT --query "innate immunity" --max 5 $ARGS
python3 $SCRIPT --query "adaptive immunity" --max 4 $ARGS
python3 $SCRIPT --query "immune checkpoint" --max 4 $ARGS

# 主题7: 儿童免疫 (12篇)
echo "── 主题7/8: 儿童免疫 (12篇) ──"
python3 $SCRIPT --query "pediatric immunodeficiency" --max 4 $ARGS
python3 $SCRIPT --query "children immune response" --max 4 $ARGS
python3 $SCRIPT --query "primary immunodeficiency children" --max 4 $ARGS

# 主题8: 先天免疫缺陷 (13篇)
echo "── 主题8/8: 先天免疫缺陷 (13篇) ──"
python3 $SCRIPT --query "primary immunodeficiency" --max 5 $ARGS
python3 $SCRIPT --query "inborn error of immunity" --max 4 $ARGS
python3 $SCRIPT --query "combined immunodeficiency" --max 4 $ARGS

echo ""
echo "============================================================"
echo "✅ 全部下载完成！"
echo "============================================================"
echo "结束时间: $(date)"
echo ""
echo "下载统计:"
COUNT=$(ls -1 $OUTPUT_DIR/*.pdf 2>/dev/null | wc -l)
echo "  PDF 文件数: $COUNT"
du -sh $OUTPUT_DIR 2>/dev/null | awk '{print "  总大小: " $1}'
echo ""
echo "============================================================"
