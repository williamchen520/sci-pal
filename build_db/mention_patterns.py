"""In-text figure/table mention parsing.

Rules:

* ``Fig. 3`` / ``Figure 3`` / ``Figs. 2 and 3`` / ``(Figs. 2, 3)`` / ``Figs. 2-4``
* ``Table 2`` / ``Tables 1 and 2``
* Chinese ``图 2`` / ``表 3``
* mentions preceded by *supplementary / extended data / supporting information*
  are NOT main-figure mentions (they refer to supplementary assets).

The parser returns ``(number, start_offset)`` pairs so callers can tell which
sentence the mention belongs to.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_SUPPLEMENTARY_PREFIX = re.compile(
    r"(supplement|extended\s+data|supporting\s+information|supplementary|appendix)",
    re.IGNORECASE,
)

FIG_GROUP = re.compile(
    r"\b(?:Fig(?:ure)?s?\.?)\s*"
    r"([0-9][0-9A-Za-z]?(?:\s*(?:,|and|&|[-–])\s*[0-9][0-9A-Za-z]?)*)"
)
TABLE_GROUP = re.compile(
    r"\bTables?\s*"
    r"([0-9][0-9A-Za-z]?(?:\s*(?:,|and|&|[-–])\s*[0-9][0-9A-Za-z]?)*)"
)
CN_FIG = re.compile(r"图\s*([0-9]{1,3})")
CN_TABLE = re.compile(r"表\s*([0-9]{1,3})")


def _is_supplementary(text: str, start: int) -> bool:
    window = text[max(0, start - 60):start]
    return bool(_SUPPLEMENTARY_PREFIX.search(window))


def _expand(group: str) -> List[str]:
    numbers: List[str] = []
    for part in re.split(r",|and|&", group):
        part = part.strip()
        if not part:
            continue
        rng = re.fullmatch(r"([0-9]+)\s*[-–]\s*([0-9]+)", part)
        if rng:
            start, end = int(rng.group(1)), int(rng.group(2))
            if 0 < end - start <= 30:
                numbers.extend(str(n) for n in range(start, end + 1))
                continue
        token = re.match(r"([0-9]+[A-Za-z]?)", part)
        if token:
            numbers.append(token.group(1))
    return numbers


def figure_mentions(text: str) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for match in FIG_GROUP.finditer(text):
        if _is_supplementary(text, match.start()):
            continue
        for number in _expand(match.group(1)):
            out.append((number, match.start()))
    for match in CN_FIG.finditer(text):
        out.append((match.group(1), match.start()))
    return out


def table_mentions(text: str) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for match in TABLE_GROUP.finditer(text):
        if _is_supplementary(text, match.start()):
            continue
        for number in _expand(match.group(1)):
            out.append((number, match.start()))
    for match in CN_TABLE.finditer(text):
        out.append((match.group(1), match.start()))
    return out


def caption_number(caption: str) -> str | None:
    """Extract the number the authors put in the caption (``Fig. 2. ...``)."""
    if not caption:
        return None
    match = re.match(r"\s*(?:Fig(?:ure)?\.?|表|图)\s*([0-9]{1,3})", caption, re.IGNORECASE)
    return match.group(1) if match else None
