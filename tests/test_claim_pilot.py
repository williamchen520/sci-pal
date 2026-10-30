"""Claim pilot service and API tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from build_db.claim_pilot_schema import migrate
from routes.claims import build_claims_blueprint
from services.claims import service


class ClaimPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "claims.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT);
            CREATE TABLE sentences (
                sentence_id TEXT PRIMARY KEY, paper_id TEXT, text TEXT
            );
            CREATE VIRTUAL TABLE sentences_fts USING fts5(text);
            INSERT INTO papers VALUES ('p1', 'HCC immunotherapy trial');
            INSERT INTO sentences VALUES ('s1', 'p1', 'PD-1 blockade improved overall survival in HCC');
            INSERT INTO sentences_fts(rowid, text) VALUES (1, 'PD-1 blockade improved overall survival in HCC');
            """
        )
        conn.commit()
        conn.close()
        migrate(self.db)
        conn = service.connect(self.db)
        self.claim_id = service.create_claim(
            conn,
            {
                "claim_id": "claim_test",
                "title": "PD-1 improves survival",
                "claim_text": "PD-1 blockade improves overall survival in HCC",
                "claim_type": "comparative",
                "qualifiers": {"population": "HCC", "outcome": "OS"},
            },
        )
        conn.close()
        app = Flask(__name__)
        app.register_blueprint(build_claims_blueprint(db_path=self.db))
        self.client = app.test_client()

    def test_add_evidence_and_decision(self) -> None:
        conn = service.connect(self.db)
        result = service.add_evidence(conn, self.claim_id, "s1", "supports", "trial result")
        self.assertEqual(result["quote"], "PD-1 blockade improved overall survival in HCC")
        claim = service.decide(conn, self.claim_id, "accept", "evidence sufficient")
        conn.close()
        self.assertEqual(claim["status"], "accepted")
        self.assertEqual(claim["decision"], "accept")
        self.assertTrue(any(event["action"] == "decision:accept" for event in claim["events"]))

    def test_search_candidates(self) -> None:
        conn = service.connect(self.db)
        candidates = service.search_candidates(conn, self.claim_id, direction="support")
        conn.close()
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["sentence_id"], "s1")

    def test_api_list_detail_and_validation(self) -> None:
        listing = self.client.get("/api/claims").get_json()["claims"]
        self.assertEqual(len(listing), 1)
        detail = self.client.get(f"/api/claims/{self.claim_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["claim_text"], "PD-1 blockade improves overall survival in HCC")
        bad = self.client.post(
            f"/api/claims/{self.claim_id}/evidence",
            json={"sentence_id": "s1", "relation": "wrong"},
        )
        self.assertEqual(bad.status_code, 400)
        added = self.client.post(
            f"/api/claims/{self.claim_id}/evidence",
            json={"sentence_id": "s1", "relation": "supports"},
        )
        self.assertEqual(added.status_code, 201)
        decided = self.client.post(
            f"/api/claims/{self.claim_id}/decision",
            json={"decision": "revise", "note": "needs more evidence"},
        )
        self.assertEqual(decided.status_code, 200)
        self.assertEqual(decided.get_json()["status"], "revised")


if __name__ == "__main__":
    unittest.main()
