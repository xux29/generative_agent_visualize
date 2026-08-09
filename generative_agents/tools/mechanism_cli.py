#!/usr/bin/env python3
"""机制参数版本 CLI：list / show / save / activate / rollback / diff。

工作目录约定为 generative_agents/::

    python tools/mechanism_cli.py list
    python tools/mechanism_cli.py show
    python tools/mechanism_cli.py show --version v0_baseline
    python tools/mechanism_cli.py save --name 实验A --note "提高复发基线"
    python tools/mechanism_cli.py activate <version_id>
    python tools/mechanism_cli.py rollback <version_id>
    python tools/mechanism_cli.py diff <id_a> <id_b>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.mechanism_config import (  # noqa: E402
    DEFAULT_ACTIVE_PATH,
    MECHANISM_DATA_DIR,
    MechanismConfigError,
    VersionStore,
    load_mechanism_config,
    validate_config,
)
from modules.mechanism_config.schema import get_by_dotted  # noqa: E402

# show 摘要关注的关键路径
_KEY_PATHS = [
    "simulation.subject.self_discipline",
    "simulation.subject.addiction_level",
    "simulation.subject.initial_health",
    "simulation.health.warning_line",
    "simulation.relapse.base_prob",
    "simulation.satisfaction.base_score",
    "management.tidal.scenarios",
]


def _store() -> VersionStore:
    return VersionStore()


def _read_version_or_active(version_id: Optional[str]) -> Dict[str, Any]:
    if version_id:
        path = MECHANISM_DATA_DIR / "versions" / f"{version_id}.json"
        if not path.is_file():
            raise MechanismConfigError(f"版本不存在: {version_id} ({path})")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return validate_config(raw)
    # active：经 loader（与 defaults 合并）
    return load_mechanism_config(str(DEFAULT_ACTIVE_PATH))


def cmd_list(_: argparse.Namespace) -> int:
    versions = _store().list_versions()
    if not versions:
        print("(无版本)")
        return 0
    print(f"{'ACTIVE':<8} {'ID':<40} {'NAME':<20} {'CREATED_AT':<22} NOTE")
    print("-" * 110)
    for v in versions:
        mark = "*" if v.get("active") else ""
        print(
            f"{mark:<8} {str(v.get('id', '')):<40} {str(v.get('name', '')):<20} "
            f"{str(v.get('created_at', '')):<22} {v.get('note', '')}"
        )
    print(f"\nactive_id: {_store().get_active_id()}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cfg = _read_version_or_active(args.version)
    meta = cfg.get("meta", {})
    label = args.version or f"active ({DEFAULT_ACTIVE_PATH})"
    print(f"=== mechanism config: {label} ===\n")
    print("[meta]")
    for k in ("version_id", "name", "created_at", "note"):
        print(f"  {k}: {meta.get(k, '')}")
    print("\n[key paths]")
    for path in _KEY_PATHS:
        val = get_by_dotted(cfg, path, default="<missing>")
        if path.endswith(".scenarios") and isinstance(val, dict):
            val = sorted(val.keys())
        print(f"  {path}: {val}")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    vid = _store().save(name=args.name, note=args.note or "")
    print(f"saved: {vid}")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    _store().activate(args.version_id)
    print(f"activated: {args.version_id}")
    print(f"active_id: {_store().get_active_id()}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    autosave = not args.no_autosave
    result = _store().rollback(args.version_id, autosave=autosave)
    if autosave:
        print(f"autosaved before rollback: {result}")
    print(f"rolled back to: {args.version_id}")
    print(f"active_id: {_store().get_active_id()}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    result = _store().diff(args.id_a, args.id_b)
    changes: Dict[str, Any] = result.get("changes", {})
    print(f"diff {result['a']} → {result['b']}")
    print(f"changes: {len(changes)}")
    if not changes:
        print("(identical)")
        return 0
    # 限制输出量，避免刷屏
    items: List[tuple] = sorted(changes.items())
    limit = args.limit if args.limit and args.limit > 0 else len(items)
    for path, pair in items[:limit]:
        print(f"  {path}:")
        print(f"    a: {pair.get('a')}")
        print(f"    b: {pair.get('b')}")
    if len(items) > limit:
        print(f"  ... ({len(items) - limit} more)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="机制参数版本管理 CLI（工作目录: generative_agents/）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出版本")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="显示 active 或指定版本摘要")
    p_show.add_argument("--version", type=str, default=None, help="版本 id（默认 active）")
    p_show.set_defaults(func=cmd_show)

    p_save = sub.add_parser("save", help="把当前 active 存为新版本")
    p_save.add_argument("--name", required=True, help="版本名称")
    p_save.add_argument("--note", default="", help="备注")
    p_save.set_defaults(func=cmd_save)

    p_act = sub.add_parser("activate", help="激活指定版本为 active.json")
    p_act.add_argument("version_id", help="版本 id")
    p_act.set_defaults(func=cmd_activate)

    p_rb = sub.add_parser("rollback", help="回退到指定版本（默认先 autosave 当前）")
    p_rb.add_argument("version_id", help="目标版本 id")
    p_rb.add_argument(
        "--no-autosave",
        action="store_true",
        help="回退前不自动保存当前 active",
    )
    p_rb.set_defaults(func=cmd_rollback)

    p_diff = sub.add_parser("diff", help="比较两个版本差异")
    p_diff.add_argument("id_a", help="版本 A")
    p_diff.add_argument("id_b", help="版本 B")
    p_diff.add_argument("--limit", type=int, default=50, help="最多打印条数（默认 50）")
    p_diff.set_defaults(func=cmd_diff)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except MechanismConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
