#!/usr/bin/env python3
"""
Seed Test Data
Populates the database with sample papers so you can test the system
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.init_db import init_database
from build_db.db_writer import DatabaseWriter

def seed_test_data():
    """Populate database with sample research papers"""
    
    print("🌱 Seeding test data...")
    print("=" * 60)
    
    # Initialize database first
    init_database()
    
    db_writer = DatabaseWriter()
    
    # ============================================================
    # Paper 1: Biology sample
    # ============================================================
    paper1 = {
        "paper_id": "paper_biology_2024",
        "metadata": {
            "title": "Recent Advances in Molecular Biology",
            "authors": "Smith, J., Johnson, A., Williams, K.",
            "journal": "Journal of Molecular Biology",
            "year": 2024,
            "doi": "10.1016/j.jmb.2024.01.001",
            "abstract": "This review discusses recent advances in molecular biology techniques, including CRISPR gene editing and single-cell sequencing. We examine the impact of these technologies on our understanding of cellular processes and discuss future directions.",
            "page_count": 15,
            "parser_source": "seed"
        },
        "paragraphs": [
            {
                "para_id": "paper_biology_2024_p001",
                "paper_id": "paper_biology_2024",
                "page_number": 1,
                "section_type": "abstract",
                "section_name": "Abstract",
                "para_index": 0,
                "text_content": "This review discusses recent advances in molecular biology techniques, including CRISPR gene editing and single-cell sequencing. We examine the impact of these technologies on our understanding of cellular processes and discuss future directions.",
                "parser_source": "seed"
            },
            {
                "para_id": "paper_biology_2024_p002",
                "paper_id": "paper_biology_2024",
                "page_number": 2,
                "section_type": "introduction",
                "section_name": "Introduction",
                "para_index": 0,
                "text_content": "Molecular biology has undergone a revolution in the past decade. CRISPR-Cas9 gene editing has transformed our ability to modify genomes, while single-cell RNA sequencing has revealed previously hidden cellular heterogeneity.",
                "parser_source": "seed"
            },
            {
                "para_id": "paper_biology_2024_p003",
                "paper_id": "paper_biology_2024",
                "page_number": 3,
                "section_type": "methodology",
                "section_name": "CRISPR Methods",
                "para_index": 0,
                "text_content": "The CRISPR-Cas9 system uses guide RNA to direct the Cas9 nuclease to specific genomic locations. We optimized the protocol for mammalian cell culture, achieving 85% editing efficiency with our optimized sgRNA design.",
                "parser_source": "seed"
            },
            {
                "para_id": "paper_biology_2024_p004",
                "paper_id": "paper_biology_2024",
                "page_number": 5,
                "section_type": "results",
                "section_name": "Single-cell Results",
                "para_index": 0,
                "text_content": "Single-cell sequencing of 10,000 cells from mouse brain tissue revealed 12 distinct cell clusters, including several previously unknown subtypes. This demonstrates the power of single-cell approaches for discovering new cell types.",
                "parser_source": "seed"
            }
        ],
        "figures": [
            {
                "figure_id": "paper_biology_2024_fig001",
                "paper_id": "paper_biology_2024",
                "page_number": 4,
                "figure_type": "figure",
                "caption": "Figure 1: CRISPR-Cas9 gene editing mechanism. The guide RNA directs Cas9 to the target DNA sequence.",
                "para_id": "paper_biology_2024_p003",
                "parser_source": "seed"
            }
        ],
        "citations": [
            {
                "citation_id": "paper_biology_2024_cit001",
                "paper_id": "paper_biology_2024",
                "ref_index": 1,
                "raw_text": "Doudna, J.A. & Charpentier, E. (2014). The new frontier of genome engineering with CRISPR-Cas9. Science, 346(6213).",
                "author": "Doudna, J.A.",
                "title": "The new frontier of genome engineering with CRISPR-Cas9",
                "journal": "Science",
                "year": 2014,
                "cited_by_count": 5000,
                "parser_source": "seed"
            },
            {
                "citation_id": "paper_biology_2024_cit002",
                "paper_id": "paper_biology_2024",
                "ref_index": 2,
                "raw_text": "Macosko, E.Z. et al. (2015). Highly parallel genome-wide expression profiling of individual cells using nanoliter droplets. Cell, 161(5).",
                "author": "Macosko, E.Z.",
                "title": "Highly parallel genome-wide expression profiling of individual cells",
                "journal": "Cell",
                "year": 2015,
                "cited_by_count": 3000,
                "parser_source": "seed"
            }
        ],
        "tables": []
    }
    
    db_writer.insert_paper(paper1)
    print()
    
    # ============================================================
    # Paper 2: AI / ML sample
    # ============================================================
    paper2 = {
        "paper_id": "paper_ai_2024",
        "metadata": {
            "title": "Deep Learning Applications in Medical Imaging",
            "authors": "Lee, S., Patel, R., Chen, M.",
            "journal": "Nature Medicine",
            "year": 2024,
            "doi": "10.1038/s41591-024-00002-x",
            "abstract": "Deep learning has shown remarkable performance in medical image analysis tasks, from cancer detection to radiographic interpretation. This paper reviews current state-of-the-art models and discusses clinical translation challenges.",
            "page_count": 20,
            "parser_source": "seed"
        },
        "paragraphs": [
            {
                "para_id": "paper_ai_2024_p001",
                "paper_id": "paper_ai_2024",
                "page_number": 1,
                "section_type": "abstract",
                "section_name": "Abstract",
                "para_index": 0,
                "text_content": "Deep learning has shown remarkable performance in medical image analysis tasks, from cancer detection to radiographic interpretation. This paper reviews current state-of-the-art models and discusses clinical translation challenges.",
                "parser_source": "seed"
            },
            {
                "para_id": "paper_ai_2024_p002",
                "paper_id": "paper_ai_2024",
                "page_number": 3,
                "section_type": "methodology",
                "section_name": "Model Architecture",
                "para_index": 0,
                "text_content": "We used a vision transformer (ViT) architecture pretrained on ImageNet and fine-tuned on our medical imaging dataset. The model achieved 96% accuracy on lung cancer detection, outperforming radiologists on the benchmark dataset.",
                "parser_source": "seed"
            },
            {
                "para_id": "paper_ai_2024_p003",
                "paper_id": "paper_ai_2024",
                "page_number": 7,
                "section_type": "results",
                "section_name": "Clinical Validation",
                "para_index": 0,
                "text_content": "In a prospective clinical trial of 500 patients, the AI-assisted system reduced false positive rates by 30% while maintaining sensitivity. Radiologists using the system were 15% faster in their diagnoses.",
                "parser_source": "seed"
            }
        ],
        "figures": [
            {
                "figure_id": "paper_ai_2024_fig001",
                "paper_id": "paper_ai_2024",
                "page_number": 5,
                "figure_type": "figure",
                "caption": "Figure 2: ROC curve showing model performance on lung cancer detection. AUC = 0.96.",
                "para_id": "paper_ai_2024_p002",
                "parser_source": "seed"
            }
        ],
        "citations": [
            {
                "citation_id": "paper_ai_2024_cit001",
                "paper_id": "paper_ai_2024",
                "ref_index": 1,
                "raw_text": "Esteva, A. et al. (2017). Dermatologist-level classification of skin cancer with deep neural networks. Nature, 542(7639).",
                "author": "Esteva, A.",
                "title": "Dermatologist-level classification of skin cancer with deep neural networks",
                "journal": "Nature",
                "year": 2017,
                "cited_by_count": 4000,
                "parser_source": "seed"
            }
        ],
        "tables": []
    }
    
    db_writer.insert_paper(paper2)
    print()
    
    print("=" * 60)
    print("✅ Test data seeding complete!")
    print(f"  - 2 sample papers added")
    print(f"  - 7 paragraphs total")
    print(f"  - 2 figures total")
    print(f"  - 3 citations total")
    print("=" * 60)
    print()
    print("You can now:")
    print("  1. Start the server: python app.py")
    print("  2. Open http://localhost:5000 in your browser")
    print("  3. Search for 'CRISPR' or 'deep learning'")
    print("  4. Ask the AI: 'What is CRISPR?' or 'How accurate is the medical imaging model?'")

if __name__ == "__main__":
    seed_test_data()
