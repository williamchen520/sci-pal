"""Minimal echo adapter used to validate the plugin contract."""

from __future__ import annotations

from typing import Any, Dict


class EchoPlugin:
    name = "echo"
    version = "0.1.0"

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = str(payload.get("text") or "")
        return {"echo": text, "length": len(text)}
