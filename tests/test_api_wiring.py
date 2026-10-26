"""Seam test: the contract pilot routes keep the agreed response shape.

This does not import ``api_server`` (it needs models and a database); it parses
the source so a refactor that drops the envelope breaks the test instead of
silently reverting the pilot.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "api_server.py"
ROUTES_DIR = Path(__file__).resolve().parents[1] / "routes"

PILOT_ROUTES = {"review_llm_status"}


def _tree() -> ast.Module:
    return ast.parse(API.read_text(encoding="utf-8"))


def _all_trees() -> list[ast.Module]:
    trees = [_tree()]
    for path in sorted(ROUTES_DIR.glob("*.py")):
        trees.append(ast.parse(path.read_text(encoding="utf-8")))
    return trees


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    functions: dict[str, ast.FunctionDef] = {}
    for source in _all_trees():
        for node in ast.walk(source):
            if isinstance(node, ast.FunctionDef):
                functions.setdefault(node.name, node)
    return functions


def _called_names(node: ast.AST) -> set[str]:
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            names.add(child.func.id)
    return names


class ContractPilotTests(unittest.TestCase):
    def test_contracts_are_imported(self) -> None:
        source = API.read_text(encoding="utf-8")
        self.assertIn("from contracts import", source)

    def test_pilot_routes_exist(self) -> None:
        functions = _functions(_tree())
        for name in PILOT_ROUTES:
            self.assertIn(name, functions, f"route {name} disappeared")

    def test_pilot_routes_return_envelopes(self) -> None:
        functions = _functions(_tree())
        for name in PILOT_ROUTES:
            calls = _called_names(functions[name])
            self.assertIn("ok", calls, f"{name} no longer returns ok(...)")
            self.assertIn("fail", calls, f"{name} no longer returns fail(...)")

    def test_pilot_routes_do_not_leak_exception_text(self) -> None:
        functions = _functions(_tree())
        for name in PILOT_ROUTES:
            node = functions[name]
            calls = _called_names(node)
            self.assertNotIn("str", calls, f"{name} interpolates the raw exception")

    def test_handlers_not_registered_globally_yet(self) -> None:
        # The pilot keeps the blast radius to two routes; global error handlers
        # come in a later batch together with the router split.
        source = API.read_text(encoding="utf-8")
        self.assertNotIn("register_error_handlers", source)

    def test_system_blueprint_is_registered(self) -> None:
        source = API.read_text(encoding="utf-8")
        self.assertIn("from routes.system import build_system_blueprint", source)
        self.assertIn("register_blueprint(", source)
        self.assertNotIn("def graph_stats", source)
        self.assertNotIn("def list_communities", source)

    def test_papers_blueprint_is_registered(self) -> None:
        source = API.read_text(encoding="utf-8")
        self.assertIn("from routes.papers import build_papers_blueprint", source)
        self.assertNotIn("def list_papers", source)
        self.assertNotIn("def paper_detail", source)
        self.assertNotIn("def paper_graph", source)

    def test_search_blueprint_is_registered(self) -> None:
        source = API.read_text(encoding="utf-8")
        self.assertIn("from routes.search import build_search_blueprint", source)
        self.assertNotIn("def download_status", source)
        self.assertNotIn("def download_history", source)
        self.assertNotIn("def download_queue_status", source)


if __name__ == "__main__":
    unittest.main()
