"""Code parsers for P2 ingestion.

Python uses tree-sitter; Nextflow uses a conservative block scanner until a
Nextflow grammar is added. Parser output is deliberately lossless spans: every
unit can be read back from the repository.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from tree_sitter import Language, Parser
import tree_sitter_python as tsp

PY_LANGUAGE = Language(tsp.language())
PY_PARSER = Parser(PY_LANGUAGE)

NEXTFLOW_BLOCK = re.compile(r"\b(process|workflow)(?:\s+([A-Za-z_][A-Za-z0-9_]*))?\s*\{")
NEXTFLOW_INCLUDE = re.compile(r"\binclude\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")


@dataclass
class ParsedUnit:
    unit_id: str
    file_path: str
    symbol_name: str
    unit_type: str
    text: str
    start_line: int
    end_line: int
    parent_unit_id: str | None = None


@dataclass
class ParsedEdge:
    src_unit_id: str
    dst_unit_id: str
    relation: str
    source: str = "parser"
    confidence: str = "medium"


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return prefix + "_" + hashlib.sha1(raw).hexdigest()[:16]


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _python_docstring(source: bytes, node) -> str:
    body = node.child_by_field_name("body")
    if body is None or not body.children:
        return ""
    first = body.children[0]
    if first.type == "expression_statement" and first.children:
        string = first.children[0]
        if string.type in {"string", "concatenated_string"}:
            return _node_text(source, string).strip("'\" \n")[:500]
    return ""


def parse_python(text: str, path: str) -> tuple[list[ParsedUnit], list[ParsedEdge]]:
    source = text.encode("utf-8")
    tree = PY_PARSER.parse(source)
    file_id = _stable_id("unit", path, "file")
    units: list[ParsedUnit] = [
        ParsedUnit(
            unit_id=file_id,
            file_path=path,
            symbol_name=path,
            unit_type="file",
            text=text,
            start_line=1,
            end_line=text.count("\n") + 1,
        )
    ]
    edges: list[ParsedEdge] = []

    def visit(node, parent_id: str | None) -> None:
        if node.type == "call" and parent_id:
            fn = node.child_by_field_name("function")
            if fn:
                target = _node_text(source, fn)
                edges.append(
                    ParsedEdge(parent_id, f"unresolved:{target}", "calls", "ast", "medium")
                )
        if node.type in {"function_definition", "class_definition"}:
            name_node = node.child_by_field_name("name")
            name = _node_text(source, name_node) if name_node else node.type
            unit_type = "function" if node.type == "function_definition" else "class"
            uid = _stable_id("unit", path, unit_type, name, str(node.start_byte), str(node.end_byte))
            body = _node_text(source, node)
            units.append(
                ParsedUnit(
                    unit_id=uid,
                    file_path=path,
                    symbol_name=name,
                    unit_type=unit_type,
                    text=body,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    parent_unit_id=parent_id or file_id,
                )
            )
            for child in node.children:
                visit(child, uid)
            return
        if node.type in {"import_statement", "import_from_statement"}:
            target = _node_text(source, node).strip()
            edges.append(
                ParsedEdge(file_id, f"unresolved:{target}", "imports", "ast", "high")
            )
        for child in node.children:
            visit(child, parent_id)

    visit(tree.root_node, file_id)
    return units, edges


def _match_brace(text: str, start: int) -> int:
    depth = 0
    quote: str | None = None
    triple = False
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if triple and text.startswith(quote * 3, i):
                i += 3
                quote = None
                triple = False
                continue
            if not triple and ch == "\\":
                i += 2
                continue
            if not triple and ch == quote:
                quote = None
            i += 1
            continue
        if text.startswith("//", i):
            i = text.find("\n", i)
            if i == -1:
                return -1
            continue
        if text.startswith("/*", i):
            i = text.find("*/", i + 2)
            if i == -1:
                return -1
            i += 2
            continue
        if ch in {"'", '"'}:
            quote = ch
            triple = text.startswith(ch * 3, i)
            i += 3 if triple else 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_nextflow(text: str, path: str) -> tuple[list[ParsedUnit], list[ParsedEdge]]:
    file_id = _stable_id("unit", path, "file")
    units = [
        ParsedUnit(
            unit_id=file_id,
            file_path=path,
            symbol_name=path,
            unit_type="file",
            text=text,
            start_line=1,
            end_line=text.count("\n") + 1,
        )
    ]
    edges: list[ParsedEdge] = []
    for match in NEXTFLOW_BLOCK.finditer(text):
        kind, name = match.group(1), match.group(2)
        if not name:
            name = f"{kind}_anonymous"
        open_at = match.end() - 1
        close_at = _match_brace(text, open_at)
        if close_at == -1:
            continue
        uid = _stable_id("unit", path, kind, name, str(match.start()), str(close_at))
        units.append(
            ParsedUnit(
                unit_id=uid,
                file_path=path,
                symbol_name=name,
                unit_type=kind,
                text=text[match.start() : close_at + 1],
                start_line=text[: match.start()].count("\n") + 1,
                end_line=text[: close_at + 1].count("\n") + 1,
                parent_unit_id=file_id,
            )
        )
    for match in NEXTFLOW_INCLUDE.finditer(text):
        names, target = match.group(1), match.group(2)
        edges.append(
            ParsedEdge(file_id, f"include:{target}", "imports", "nextflow", "high")
        )
    return units, edges


R_FUNCTION = re.compile(
    r"(?m)^\s*([A-Za-z_.][A-Za-z0-9_.]*)\s*(?:<-|=)\s*function\s*\("
)
R_R6 = re.compile(
    r"(?m)^\s*([A-Za-z_.][A-Za-z0-9_.]*)\s*(?:<-|=)\s*R6Class\s*\(\s*['\"]([^'\"]+)"
)
R_S4 = re.compile(r"\b(setClass|setGeneric|setMethod)\s*\(\s*['\"]([^'\"]+)")
R_LIBRARY = re.compile(r"\b(?:library|require)\s*\(\s*['\"]?([A-Za-z0-9_.]+)")
R_SOURCE = re.compile(r"\bsource\s*\(\s*['\"]([^'\"]+)['\"]")


def _match_r_brace(text: str, start: int) -> int:
    """Match an R brace block while skipping strings and # comments."""
    depth = 0
    quote: str | None = None
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "#":
            newline = text.find("\n", i)
            if newline == -1:
                return -1
            i = newline
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_r(text: str, path: str) -> tuple[list[ParsedUnit], list[ParsedEdge]]:
    file_id = _stable_id("unit", path, "file")
    units = [
        ParsedUnit(
            unit_id=file_id,
            file_path=path,
            symbol_name=path,
            unit_type="file",
            text=text,
            start_line=1,
            end_line=text.count("\n") + 1,
        )
    ]
    edges: list[ParsedEdge] = []
    seen: set[tuple[str, str]] = set()

    for match in R_FUNCTION.finditer(text):
        name = match.group(1)
        open_at = text.find("{", match.end())
        if open_at == -1:
            continue
        close_at = _match_r_brace(text, open_at)
        if close_at == -1:
            continue
        key = (name, str(match.start()))
        if key in seen:
            continue
        seen.add(key)
        uid = _stable_id("unit", path, "function", name, str(match.start()), str(close_at))
        units.append(
            ParsedUnit(
                unit_id=uid,
                file_path=path,
                symbol_name=name,
                unit_type="function",
                text=text[match.start() : close_at + 1],
                start_line=text[: match.start()].count("\n") + 1,
                end_line=text[: close_at + 1].count("\n") + 1,
                parent_unit_id=file_id,
            )
        )

    for match in R_R6.finditer(text):
        name, class_name = match.group(1), match.group(2)
        uid = _stable_id("unit", path, "class", class_name, str(match.start()))
        units.append(
            ParsedUnit(
                unit_id=uid,
                file_path=path,
                symbol_name=class_name,
                unit_type="class",
                text=text[match.start() :],
                start_line=text[: match.start()].count("\n") + 1,
                end_line=text.count("\n") + 1,
                parent_unit_id=file_id,
            )
        )

    for match in R_S4.finditer(text):
        kind, name = match.group(1), match.group(2)
        uid = _stable_id("unit", path, kind, name, str(match.start()))
        units.append(
            ParsedUnit(
                unit_id=uid,
                file_path=path,
                symbol_name=name,
                unit_type=kind,
                text=text[match.start() :],
                start_line=text[: match.start()].count("\n") + 1,
                end_line=text.count("\n") + 1,
                parent_unit_id=file_id,
            )
        )

    for match in R_LIBRARY.finditer(text):
        package = match.group(1)
        edges.append(
            ParsedEdge(file_id, f"unresolved:library:{package}", "imports", "r", "high")
        )
    for match in R_SOURCE.finditer(text):
        target = match.group(1)
        edges.append(
            ParsedEdge(file_id, f"source:{target}", "imports", "r", "high")
        )
    return units, edges


RMD_FENCE = re.compile(r"(?m)^[ \t]*```+[ \t]*\{([A-Za-z0-9_+-]+)([^}]*)\}[ \t]*$")
RMD_CLOSE = re.compile(r"(?m)^[ \t]*```+[ \t]*$")
RMD_LABEL = re.compile(r"(?:label\s*=\s*|#\s*)([A-Za-z0-9_.-]+)")


def parse_rmd(text: str, path: str) -> tuple[list[ParsedUnit], list[ParsedEdge]]:
    """Parse R Markdown / Quarto fenced chunks as units."""
    file_id = _stable_id("unit", path, "file")
    units = [
        ParsedUnit(
            unit_id=file_id,
            file_path=path,
            symbol_name=path,
            unit_type="file",
            text=text,
            start_line=1,
            end_line=text.count("\n") + 1,
        )
    ]
    edges: list[ParsedEdge] = []
    for index, match in enumerate(RMD_FENCE.finditer(text), 1):
        language = match.group(1).lower()
        info = match.group(2) or ""
        label_match = RMD_LABEL.search(info)
        if label_match:
            label = label_match.group(1)
        else:
            first = info.strip().split(",", 1)[0].strip()
            label = first if re.fullmatch(r"[A-Za-z0-9_.-]+", first) else f"{language}_chunk_{index}"
        body_start = text.find("\n", match.end())
        if body_start == -1:
            continue
        body_start += 1
        close = RMD_CLOSE.search(text, body_start)
        body_end = close.start() if close else len(text)
        body = text[body_start:body_end]
        uid = _stable_id("unit", path, "chunk", label, str(match.start()))
        chunk_start = text[:match.start()].count("\n") + 1
        units.append(
            ParsedUnit(
                unit_id=uid,
                file_path=path,
                symbol_name=label,
                unit_type="chunk",
                text=body,
                start_line=chunk_start,
                end_line=text[:body_end].count("\n") + 1,
                parent_unit_id=file_id,
            )
        )
        inner_units = []
        if language == "r":
            inner_units, _ = parse_r(body, f"{path}#{label}")
        elif language == "python":
            inner_units, _ = parse_python(body, f"{path}#{label}")
        for inner in inner_units:
            if inner.unit_type == "file":
                continue
            inner_id = _stable_id(
                "unit", path, "chunk", label, "inner", inner.unit_type,
                inner.symbol_name, str(inner.start_line), str(inner.end_line),
            )
            units.append(
                ParsedUnit(
                    unit_id=inner_id,
                    file_path=path,
                    symbol_name=inner.symbol_name,
                    unit_type=inner.unit_type,
                    text=inner.text,
                    start_line=chunk_start + inner.start_line - 1,
                    end_line=chunk_start + inner.end_line - 1,
                    parent_unit_id=uid,
                )
            )
    return units, edges
