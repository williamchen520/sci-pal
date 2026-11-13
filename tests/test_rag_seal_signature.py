"""R14 seal signature tests."""

from __future__ import annotations

import unittest

from services.rag_control.signing import sign, verify


class SealSignatureTests(unittest.TestCase):
    def test_sign_and_verify(self) -> None:
        seal = sign("abc123")
        self.assertEqual(seal["algorithm"], "ed25519")
        self.assertTrue(verify("abc123", seal["signature"], seal["public_key"]))

    def test_tampered_hash_fails(self) -> None:
        seal = sign("abc123")
        self.assertFalse(verify("abc124", seal["signature"], seal["public_key"]))

    def test_key_id_stable_for_same_key(self) -> None:
        first = sign("abc")
        second = sign("def")
        self.assertEqual(first["key_id"], second["key_id"])


if __name__ == "__main__":
    unittest.main()
