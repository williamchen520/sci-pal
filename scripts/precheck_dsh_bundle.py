#!/usr/bin/env python
"""DSH bundle 安装前体检（只读诊断 + 仓库内备份）。

定位
    人工装 bundle 前跑一次，回答两个问题：
      1. profile 里有没有和 bundle 重名的 serverName？（有 → 先清场，否则加载报错）
      2. bundle 自身是否合法？（不合法 → 别装）

    本脚本**只读** ~/.dsh 下的文件，唯一的写入是把它备份到仓库内的
    tests/backups/（因为该文件在 git 之外，删坏了 git 救不回来）。

退出码
    0 = 无冲突、bundle 合法 → 可安装
    1 = 存在 serverName 冲突 → 需先按输出的行区间清理
    2 = bundle 自身不合法（或无法完成校验）→ 不许装

用法
    venv_sciPal_py312\\Scripts\\python.exe scripts\\precheck_dsh_bundle.py

硬约束
    · 绝不写 ~/.dsh/** 任何文件
    · YAML 依赖缺失时报 FAIL，不静默跳过
    · 不用 try/except: pass 吞异常（本项目已因吞异常栽过：run_db_migrations）
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DIR = PROJECT_ROOT / "packages" / "dsh-scipal"
PATCH_FILE = BUNDLE_DIR / "cordis.patch.yml"
PACKAGE_FILE = BUNDLE_DIR / "package.json"
ICON_FILE = BUNDLE_DIR / "icon.svg"
LOCALE_DIR = BUNDLE_DIR / "locale"

PROFILE_PATCH = Path.home() / ".dsh" / "profiles" / "desktop" / "cordis.patch.yml"
BACKUP_DIR = PROJECT_ROOT / "tests" / "backups"

DSH_PROCESS_KEYWORD = "deepseek harness"
ALLOWED_PACKAGES = {"@deepseek-ai/dsh-mcp-client"}
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ICON_MAX_BYTES = 256 * 1024


class Checks:
    """PASS/FAIL 收集器：每条检查都必须有结论，不允许静默跳过。"""

    def __init__(self) -> None:
        self.results: list[tuple[bool, str, str]] = []

    def add(self, passed: bool, name: str, detail: str = "") -> None:
        self.results.append((passed, name, detail))
        tag = "PASS" if passed else "FAIL"
        print(f"[{tag}] {name}" + (f" —— {detail}" if detail else ""))

    @property
    def ok(self) -> bool:
        return all(passed for passed, _, _ in self.results)


# ---------------------------------------------------------------------------
# 1. DSH 运行状态
# ---------------------------------------------------------------------------


def detect_dsh_process() -> tuple[bool, str]:
    """用 tasklist 查 Electron 主进程名 'DeepSeek Harness'。"""
    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=20,
        )
    except Exception as exc:  # 不吞异常：返回可见的失败信息
        return False, f"无法执行 tasklist：{exc}"

    for line in (completed.stdout or "").splitlines():
        if DSH_PROCESS_KEYWORD in line.lower():
            name = line.split(",")[0].strip('"')
            return True, name
    return False, ""


# ---------------------------------------------------------------------------
# 2. 备份（唯一允许的写入，且只写仓库内）
# ---------------------------------------------------------------------------


def backup_profile() -> Path | None:
    if not PROFILE_PATCH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    target = BACKUP_DIR / f"cordis.patch.yml.{stamp}.bak"
    shutil.copy2(PROFILE_PATCH, target)
    return target


# ---------------------------------------------------------------------------
# 3. YAML 解析（带真实行号）
# ---------------------------------------------------------------------------


def iter_insert_entries(root_node, lines: list[str]) -> list[dict]:
    """从顶层 sequence 里抽出所有 insert 条目（含 1-based 行区间）。

    顶层写成 `- id: xxx`（没有 insert）不会被这里识别 —— 这正是要暴露的坑，
    由 check_patch_yaml() 单独判定。
    """
    entries: list[dict] = []
    if root_node is None or not hasattr(root_node, "value"):
        return entries

    for top in root_node.value:
        if not hasattr(top, "value"):
            continue
        # PyYAML 的 MappingNode.value 是 [(key_node, value_node), ...]
        for key_node, value_node in top.value:
            if getattr(key_node, "value", None) != "insert" or not hasattr(value_node, "value"):
                continue
            for item in value_node.value:
                entry = _parse_entry(item, lines)
                if entry:
                    entries.append(entry)
    return entries


def _parse_entry(item, lines: list[str]) -> dict | None:
    if not hasattr(item, "value"):
        return None
    data: dict = {}
    for key_node, value_node in item.value:
        key = getattr(key_node, "value", None)
        if key == "id":
            data["id"] = value_node.value
        elif key == "name":
            data["name"] = value_node.value
        elif key == "config" and hasattr(value_node, "value"):
            for ck, cv in value_node.value:
                if getattr(ck, "value", None) == "serverName":
                    data["serverName"] = cv.value

    start_idx = item.start_mark.line          # 0-based
    indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    end_idx = _find_block_end(lines, start_idx, indent)
    data["start_line"] = start_idx + 1
    data["end_line"] = end_idx + 1
    return data


def _find_block_end(lines: list[str], start_idx: int, indent: int) -> int:
    """向下找到同级缩进的行（或文件末尾），返回块的最后一行（0-based）。"""
    last = start_idx
    for idx in range(start_idx + 1, len(lines)):
        raw = lines[idx]
        if not raw.strip():
            continue
        cur_indent = len(raw) - len(raw.lstrip())
        if cur_indent <= indent:
            break
        last = idx
    return last


# ---------------------------------------------------------------------------
# 4. bundle 静态校验
# ---------------------------------------------------------------------------


def check_package_json(checks: Checks) -> dict | None:
    if not PACKAGE_FILE.exists():
        checks.add(False, "package.json 存在", str(PACKAGE_FILE))
        return None

    try:
        pkg = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        checks.add(False, "package.json 可解析", str(exc))
        return None
    checks.add(True, "package.json 可解析")

    checks.add(bool(pkg.get("name")), "package.json name 非空", str(pkg.get("name")))
    checks.add(bool(pkg.get("version")), "package.json version 非空", str(pkg.get("version")))
    checks.add(pkg.get("private") is True, "package.json private: true")
    checks.add(pkg.get("type") == "module", "package.json type: module")

    exports = pkg.get("exports") or {}
    checks.add(
        "./locale/*.json" in exports and exports.get("./icon") == "./icon.svg",
        "package.json exports 含 ./locale/*.json 与 ./icon",
        json.dumps(exports, ensure_ascii=False),
    )

    files = pkg.get("files") or []
    required_files = {"cordis.patch.yml", "locale/*.json", "icon.svg"}
    checks.add(
        required_files.issubset(set(files)),
        "package.json files 含 patch / locale / icon",
        json.dumps(files, ensure_ascii=False),
    )

    patch_path = (pkg.get("dsh") or {}).get("bundle", {}).get("patch")
    if not patch_path:
        checks.add(False, "package.json 含 dsh.bundle.patch（bundle 层，不是 profile 层）")
    else:
        resolved = (BUNDLE_DIR / patch_path).resolve()
        checks.add(
            resolved.is_file(),
            "dsh.bundle.patch 指向存在的文件",
            f"{patch_path} -> {resolved}",
        )
    checks.add("profile" not in (pkg.get("dsh") or {}), "未误用 dsh.profile.bundles 字段")
    return pkg


def check_patch_yaml(checks: Checks) -> list[dict]:
    try:
        import yaml
    except ImportError:
        checks.add(
            False,
            "PyYAML 可用",
            "未安装 PyYAML —— 请用 venv_sciPal_py312\\Scripts\\python.exe 运行本脚本",
        )
        return []

    checks.add(True, "PyYAML 可用")

    if not PATCH_FILE.exists():
        checks.add(False, "cordis.patch.yml 存在", str(PATCH_FILE))
        return []

    text = PATCH_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        checks.add(False, "cordis.patch.yml 可解析", str(exc))
        return []
    checks.add(True, "cordis.patch.yml 可解析")

    checks.add(
        isinstance(root, yaml.SequenceNode),
        "顶层是数组",
        type(root).__name__ if root is not None else "None",
    )

    # 顶层 `- id:` 没有 insert = 静默跳过（踩过的坑）
    top_level_ids = []
    if isinstance(root, yaml.SequenceNode):
        for top in root.value:
            if not hasattr(top, "value"):
                continue
            keys = [getattr(k, "value", None) for k, _ in top.value]
            if "id" in keys and "insert" not in keys:
                top_level_ids.append(str(top.value[1].value))
    checks.add(
        not top_level_ids,
        "无顶层 - id: 条目（必须包在 insert: 内）",
        f"违规：{top_level_ids}" if top_level_ids else "",
    )

    entries = iter_insert_entries(root, lines)
    checks.add(bool(entries), "insert 块内至少有 1 个条目", f"共 {len(entries)} 条")

    for entry in entries:
        label = entry.get("id", "<no-id>")
        name = entry.get("name")
        server_name = entry.get("serverName")
        checks.add(
            name in ALLOWED_PACKAGES,
            f"[{label}] name 在官方可安装清单内",
            str(name),
        )
        checks.add(
            bool(server_name) and bool(SERVER_NAME_RE.match(str(server_name))),
            f"[{label}] serverName 合法（^[A-Za-z0-9_-]{{1,32}}$）",
            str(server_name),
        )
    return entries


def check_icon(checks: Checks) -> None:
    if not ICON_FILE.exists():
        checks.add(False, "icon.svg 存在", str(ICON_FILE))
        return
    size = ICON_FILE.stat().st_size
    checks.add(size <= ICON_MAX_BYTES, "icon.svg ≤ 256KiB", f"{size} B")
    head = ICON_FILE.read_text(encoding="utf-8", errors="replace")[:64].lstrip()
    checks.add(head.startswith("<svg"), "icon.svg 以 <svg 开头", head[:24])


def check_locale(checks: Checks) -> None:
    for lang in ("en", "zh"):
        path = LOCALE_DIR / f"{lang}.json"
        if not path.exists():
            checks.add(False, f"locale/{lang}.json 存在")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            checks.add(False, f"locale/{lang}.json 可解析", str(exc))
            continue
        meta = data.get("meta") or {}
        checks.add(
            bool(meta.get("title")) and bool(meta.get("description")),
            f"locale/{lang}.json 含 meta.title / meta.description",
            str(meta.get("title")),
        )


# ---------------------------------------------------------------------------
# 5. 冲突扫描
# ---------------------------------------------------------------------------


def scan_conflicts(checks: Checks, bundle_entries: list[dict]) -> list[dict]:
    """扫描 profile 与 bundle 的 serverName 交集。

    注意：冲突**不作为** bundle 合法性判定的一部分 —— 冲突时退出码应为 1（需清场），
    而不是 2（bundle 自身不合法）。因此这里只把「无法扫描」记入 checks。
    """
    if not PROFILE_PATCH.exists():
        print("[PASS] profile patch 不存在 —— 无需冲突扫描")
        return []

    try:
        import yaml
    except ImportError:
        checks.add(False, "profile 冲突扫描", "PyYAML 不可用，无法扫描")
        return []

    text = PROFILE_PATCH.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    try:
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        checks.add(False, "profile patch 可解析", str(exc))
        return []

    profile_entries = iter_insert_entries(root, lines)
    bundle_by_name = {
        str(e.get("serverName")): e for e in bundle_entries if e.get("serverName")
    }

    conflicts: list[dict] = []
    for entry in profile_entries:
        server_name = str(entry.get("serverName") or "")
        if server_name in bundle_by_name:
            conflicts.append(
                {
                    "serverName": server_name,
                    "profile": entry,
                    "bundle": bundle_by_name[server_name],
                }
            )

    if conflicts:
        print(f"[WARN] 发现 {len(conflicts)} 个 serverName 冲突（需先清理 profile）")
    else:
        print("[PASS] 无 serverName 冲突")
    return conflicts


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    print("=== SciPal DSH bundle 安装前体检 ===")
    print(f"仓库     : {PROJECT_ROOT}")
    print(f"bundle   : {BUNDLE_DIR}")
    print(f"profile  : {PROFILE_PATCH}")
    print()

    running, proc_name = detect_dsh_process()
    if running:
        print(f"[WARN] DSH 正在运行（进程：{proc_name}）")
        print("       DSH 正在运行 —— 安装请在 DSH 会话内进行（见 packages/dsh-scipal/INSTALL.md）；")
        print("       本脚本不做任何写入 ~/.dsh 的操作。改 profile 需先完全退出 DSH。")
    else:
        print("[INFO] DSH 未运行 —— 可以安全备份/清理 profile。")
    print()

    backup = backup_profile()
    if backup:
        size = backup.stat().st_size
        print(f"[OK] 已备份 profile -> {backup.relative_to(PROJECT_ROOT)}（{size} B）")
    else:
        print("[INFO] profile 文件不存在，无需备份。")
    print()

    checks = Checks()
    print("--- bundle 静态校验 ---")
    check_package_json(checks)
    entries = check_patch_yaml(checks)
    check_icon(checks)
    check_locale(checks)
    print()

    print("--- serverName 冲突扫描 ---")
    conflicts = scan_conflicts(checks, entries)
    print()

    if conflicts:
        print("--- 冲突清单（需从 profile 中删除）---")
        for idx, conflict in enumerate(conflicts, start=1):
            p = conflict["profile"]
            b = conflict["bundle"]
            print(f"  冲突 {idx}: serverName = {conflict['serverName']}")
            print(
                f"    profile : 第 {p['start_line']}-{p['end_line']} 行"
                f"（id={p.get('id')}）  ← 需删除"
            )
            print(
                f"    bundle  : 第 {b['start_line']}-{b['end_line']} 行"
                f"（id={b.get('id')}）  ← 保留"
            )
        block = _insert_block_range(PROFILE_PATCH)
        if block:
            print()
            print(f"  建议：整块删除 profile 第 {block[0]}-{block[1]} 行的 `- insert:` 块")
            print("        （删前确认该块内只有上述条目；删后重跑本脚本应退出码 0）")
        print()

    print("--- 结论 ---")
    if not checks.ok:
        print("❌ bundle 自身不合法或无法完成校验，禁止安装。")
        print("退出码: 2")
        return 2
    if conflicts:
        print(f"⚠️  存在 {len(conflicts)} 个 serverName 冲突，需先按上面的行区间清理 profile。")
        print("退出码: 1")
        return 1
    print("✅ 无冲突且 bundle 合法，可以安装（安装须在 DSH 会话内进行）。")
    print("退出码: 0")
    return 0


def _insert_block_range(path: Path) -> tuple[int, int] | None:
    """定位 profile 顶层 `- insert:` 块的行区间（1-based），用于给出删除范围。"""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return None
    for idx, raw in enumerate(lines):
        if raw.lstrip().startswith("- insert:"):
            indent = len(raw) - len(raw.lstrip())
            end = _find_block_end(lines, idx, indent)
            return idx + 1, end + 1
    return None


if __name__ == "__main__":
    raise SystemExit(main())
