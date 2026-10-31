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
                sentence_id TEXT PRIMARY KEY, paper_id TEXT, text TEXT, para_id TEXT
            );
            CREATE VIRTUAL TABLE sentences_fts USING fts5(text);
            INSERT INTO papers VALUES ('p1', 'HCC immunotherapy trial');
            INSERT INTO sentences VALUES ('s1', 'p1', 'PD-1 blockade improved overall survival in HCC', 'pa1');
            INSERT INTO sentences VALUES ('s2', 'p1', 'PD-1 blockade did not improve overall survival in HCC', 'pa1');
            INSERT INTO sentences VALUES ('s3', 'p1', 'PD-1 blockade showed no benefit in a resistant subgroup', 'pa2');
            INSERT INTO sentences_fts(rowid, text) VALUES (1, 'PD-1 blockade improved overall survival in HCC');
            INSERT INTO sentences_fts(rowid, text) VALUES (2, 'PD-1 blockade did not improve overall survival in HCC');
            INSERT INTO sentences_fts(rowid, text) VALUES (3, 'PD-1 blockade showed no benefit in a resistant subgroup');
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

    def test_contest_decision(self) -> None:
        conn = service.connect(self.db)
        claim = service.decide(conn, self.claim_id, "contest", "conflicting evidence")
        conn.close()
        self.assertEqual(claim["status"], "contested")
        self.assertEqual(claim["decision"], "contest")

    def test_writing_brief(self) -> None:
        conn = service.connect(self.db)
        claim = service.set_writing_brief(
            conn, self.claim_id, {"safe_claim": "bounded statement"}
        )
        conn.close()
        self.assertEqual(claim["writing_brief"]["safe_claim"], "bounded statement")

    def test_search_candidates(self) -> None:
        conn = service.connect(self.db)
        candidates = service.search_candidates(conn, self.claim_id, direction="support")
        conn.close()
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["sentence_id"], "s1")

    def test_opposition_retrieval_prefers_contrary_sentence(self) -> None:
        conn = service.connect(self.db)
        candidates = service.search_candidates(conn, self.claim_id, direction="oppose")
        conn.close()
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["sentence_id"], "s2")
        self.assertGreater(candidates[0]["direction_cues"], 0)
        self.assertIn("query", candidates[0])

    def test_interrogate_with_fake_llm(self) -> None:
        class FakeLLM:
            def is_available(self):
                return True

            def chat_json(self, system_prompt, user_prompt, temperature=None):
                return {
                    "relation": "supports",
                    "confidence": 0.8,
                    "reason": "direct survival result",
                }

        conn = service.connect(self.db)
        candidates = service.interrogate(
            conn, self.claim_id, direction="support", use_llm=True, llm_client=FakeLLM()
        )
        conn.close()
        self.assertEqual(candidates[0]["suggested_relation"], "supports")
        self.assertEqual(candidates[0]["confidence"], 0.8)

    def test_semantic_retrieval_expands_paragraph_to_sentence(self) -> None:
        class FakeRetriever:
            def retrieve(self, query, **kwargs):
                return {"paragraphs": [{"para_id": "pa2", "text": "resistant subgroup"}]}

        conn = service.connect(self.db)
        candidates = service.search_candidates(
            conn,
            self.claim_id,
            direction="oppose",
            retriever=FakeRetriever(),
        )
        conn.close()
        self.assertTrue(any(item["sentence_id"] == "s3" for item in candidates))

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
        noted = self.client.post(
            f"/api/claims/{self.claim_id}/note",
            json={"note": "keep contested"},
        )
        self.assertEqual(noted.status_code, 200)
        self.assertTrue(any(event["action"] == "review_note" for event in noted.get_json()["events"]))


if __name__ == "__main__":
    unittest.main()
