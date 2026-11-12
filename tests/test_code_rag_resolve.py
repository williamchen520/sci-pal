"""Symbol binding tests for the Python resolver."""

from __future__ import annotations

import unittest

from code_rag.resolve import FileInfo, build_imports, module_of, resolve_target


class ResolverTests(unittest.TestCase):
    def test_module_names_strip_src(self) -> None:
        self.assertEqual(module_of("src/pkg/sub/a.py"), "pkg.sub.a")
        self.assertEqual(module_of("pkg/__init__.py"), "pkg")

    def test_relative_import_resolves_to_other_file(self) -> None:
        files = {
            "src/pkg/a.py": FileInfo("src/pkg/a.py", "from .b import helper\n\ndef local():\n    helper()\n"),
            "src/pkg/b.py": FileInfo("src/pkg/b.py", "def helper():\n    pass\n"),
            "src/pkg/c.py": FileInfo("src/pkg/c.py", "def local():\n    pass\n"),
        }
        imports = build_imports(files)
        hit = resolve_target(
            source_path="src/pkg/a.py",
            target="unresolved:helper",
            imports=imports,
            file_by_module={"pkg.a": "src/pkg/a.py", "pkg.b": "src/pkg/b.py"},
            symbols_by_path={
                "src/pkg/a.py": {"local": "unit_a"},
                "src/pkg/b.py": {"helper": "unit_b"},
                "src/pkg/c.py": {"local": "unit_c"},
            },
        )
        self.assertEqual(hit, ("unit_b", "high"))

    def test_self_method_uses_enclosing_class(self) -> None:
        hit = resolve_target(
            source_path="src/pkg/a.py",
            target="unresolved:self.helper",
            imports={},
            file_by_module={},
            symbols_by_path={},
            source_unit_id="unit_run",
            parent_by_unit={"unit_run": "unit_class"},
            class_methods={"unit_class": {"helper": "unit_helper"}},
        )
        self.assertEqual(hit, ("unit_helper", "high"))

    def test_unresolved_external_is_left_alone(self) -> None:
        hit = resolve_target(
            source_path="src/pkg/a.py",
            target="unresolved:numpy.array",
            imports={},
            file_by_module={},
            symbols_by_path={},
        )
        self.assertIsNone(hit)


if __name__ == "__main__":
    unittest.main()
