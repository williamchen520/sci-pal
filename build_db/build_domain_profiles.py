"""Build domain_profiles / paper_domains from title, abstract and keywords."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from services.search.domain_taxonomy import DOMAINS, classify_text

DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def main() -> None:
    conn = sqlite3.connect(str(DB))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS domain_profiles (
            domain_id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            keywords TEXT,
            refusal_threshold REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS paper_domains (
            paper_id TEXT,
            domain_id TEXT,
            confidence REAL,
            source TEXT,
            PRIMARY KEY (paper_id, domain_id)
        );
        CREATE INDEX IF NOT EXISTS idx_paper_domains_domain ON paper_domains(domain_id);
        """
    )
    for domain_id, config in DOMAINS.items():
        conn.execute(
            "INSERT OR REPLACE INTO domain_profiles "
            "(domain_id, name, keywords, refusal_threshold, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                domain_id,
                config["name"],
                ",".join(config["keywords"]),
                0.35,
                "auto-generated from title/abstract keywords",
            ),
        )
    conn.execute(
        "INSERT OR REPLACE INTO domain_profiles "
        "(domain_id, name, keywords, refusal_threshold, description) "
        "VALUES ('general', 'General biomedical', '', 0.35, 'fallback domain')"
    )
    rows = conn.execute(
        "SELECT paper_id, title, abstract, keywords FROM papers"
    ).fetchall()
    counts = {}
    for paper_id, title, abstract, keywords in rows:
        domain_id, confidence, distribution = classify_text(title, abstract, keywords)
        conn.execute(
            "INSERT OR REPLACE INTO paper_domains (paper_id, domain_id, confidence, source) "
            "VALUES (?, ?, ?, 'auto')",
            (paper_id, domain_id, confidence),
        )
        counts[domain_id] = counts.get(domain_id, 0) + 1
    conn.commit()
    conn.close()
    print({"papers": len(rows), "domains": counts})


if __name__ == "__main__":
    main()
