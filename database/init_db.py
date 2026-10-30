"""
Database initialization script for Sci-Pal
Creates all tables in research.db following our 4-domain architecture:
1. Text Domain: papers, paragraphs, chunks
2. Figure Domain: figures
3. Citation Domain: citations
4. User Domain: users, notes, favorites
5. L3 Reserved: entities, experiments, domain_tags, supplementary
"""
import sqlite3
import os
from pathlib import Path
from config.settings import DATABASE_PATH
from services.tenancy.schema import ensure_schema

def init_database():
    """Initialize all database tables"""
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Enable WAL mode for better performance
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    print("=" * 60)
    print("Initializing Sci-Pal Database")
    print("=" * 60)
    
    # ============================================================
    # 1. TEXT DOMAIN
    # ============================================================
    
    # Papers table (metadata)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS papers (
        paper_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        authors TEXT,
        journal TEXT,
        year INTEGER,
        doi TEXT,
        abstract TEXT,
        keywords TEXT,
        file_path TEXT,
        file_hash TEXT,
        page_count INTEGER,
        parser_source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    print("✅ Created table: papers")
    
    # Paragraphs table (paragraph base table - our coordinate system)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS paragraphs (
        para_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        page_number INTEGER,
        section_type TEXT,
        section_name TEXT,
        para_index INTEGER,
        text_content TEXT NOT NULL,
        char_start INTEGER,
        char_end INTEGER,
        parser_source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
    )
    ''')
    print("✅ Created table: paragraphs")
    
    # Chunks table (for vector search)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        para_id TEXT,
        chunk_index INTEGER,
        text_content TEXT NOT NULL,
        embedding BLOB,
        token_count INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id),
        FOREIGN KEY (para_id) REFERENCES paragraphs(para_id)
    )
    ''')
    print("✅ Created table: chunks")
    
    # ============================================================
    # 2. FIGURE DOMAIN
    # ============================================================
    
    # Figures table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS figures (
        figure_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        page_number INTEGER,
        figure_type TEXT,
        caption TEXT,
        image_path TEXT,
        bbox TEXT,
        para_id TEXT,
        parser_source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id),
        FOREIGN KEY (para_id) REFERENCES paragraphs(para_id)
    )
    ''')
    print("✅ Created table: figures")
    
    # ============================================================
    # 3. CITATION DOMAIN
    # ============================================================
    
    # Citations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS citations (
        citation_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        ref_index INTEGER,
        raw_text TEXT,
        author TEXT,
        title TEXT,
        journal TEXT,
        year INTEGER,
        doi TEXT,
        cited_by_count INTEGER DEFAULT 0,
        parser_source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
    )
    ''')
    print("✅ Created table: citations")
    
    # ============================================================
    # 4. USER DOMAIN
    # ============================================================
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    print("✅ Created table: users")
    
    # Notes table (personal notes)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notes (
        note_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        paper_id TEXT,
        para_id TEXT,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id),
        FOREIGN KEY (para_id) REFERENCES paragraphs(para_id)
    )
    ''')
    print("✅ Created table: notes")
    
    # Favorites table (bookmarks)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS favorites (
        favorite_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        paper_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id),
        UNIQUE(user_id, paper_id)
    )
    ''')
    print("✅ Created table: favorites")
    
    # ============================================================
    # 5. L3 RESERVED TABLES
    # ============================================================
    
    # Entities table (for knowledge graph)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS entities (
        entity_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        entity_type TEXT,
        entity_name TEXT NOT NULL,
        normalized_name TEXT,
        para_id TEXT,
        confidence REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id),
        FOREIGN KEY (para_id) REFERENCES paragraphs(para_id)
    )
    ''')
    print("✅ Created table: entities (L3 reserved)")
    
    # Experiments table (for experimental data extraction)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        experiment_type TEXT,
        animal_species TEXT,
        animal_strain TEXT,
        animal_substrain TEXT,
        sample_size INTEGER,
        duration_weeks REAL,
        dose TEXT,
        temperature_c REAL,
        parameters TEXT,
        para_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id),
        FOREIGN KEY (para_id) REFERENCES paragraphs(para_id)
    )
    ''')
    print("✅ Created table: experiments (L3 reserved)")
    
    # Domain tags table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS domain_tags (
        tag_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        tag_name TEXT NOT NULL,
        tag_category TEXT,
        confidence REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
    )
    ''')
    print("✅ Created table: domain_tags (L3 reserved)")
    
    # Supplementary materials table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supplementary (
        supp_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        file_name TEXT,
        file_type TEXT,
        file_path TEXT,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
    )
    ''')
    print("✅ Created table: supplementary")
    
    # ============================================================
    # INDEXES
    # ============================================================
    print("\nCreating indexes...")
    
    # Papers indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);')
    print("  ✅ Papers indexes")
    
    # Paragraphs indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paragraphs_paper_id ON paragraphs(paper_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paragraphs_page ON paragraphs(paper_id, page_number);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_paragraphs_section ON paragraphs(paper_id, section_type);')
    print("  ✅ Paragraphs indexes")
    
    # Chunks indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_paper_id ON chunks(paper_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_para_id ON chunks(para_id);')
    print("  ✅ Chunks indexes")
    
    # Figures indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_figures_paper_id ON figures(paper_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_figures_page ON figures(paper_id, page_number);')
    print("  ✅ Figures indexes")
    
    # Citations indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citations_paper_id ON citations(paper_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citations_doi ON citations(doi);')
    print("  ✅ Citations indexes")
    
    # Entities indexes (L3)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_paper_id ON entities(paper_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(normalized_name);')
    print("  ✅ Entities indexes (L3)")

    # ============================================================
    # Tasks table (V33.12: 统一任务表)
    # ============================================================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        progress_text TEXT DEFAULT '',
        progress_pct REAL DEFAULT 0,
        params TEXT,
        result TEXT,
        error TEXT,
        created_at TEXT,
        started_at TEXT,
        finished_at TEXT
    )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);')
    print("  ✅ Tasks table")

    # Commit and close
    ensure_schema(conn)
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Database initialization complete!")
    print(f"Database path: {DATABASE_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    init_database()
