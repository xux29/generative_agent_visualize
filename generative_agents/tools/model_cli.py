#!/usr/bin/env python3
"""统一 Model Version CLI：propose / edit / validate / promote / approve / rollback。

工作目录: generative_agents/

典型 AI 流程::

    python tools/model_cli.py propose --name ai_relapse --note "降低复发基线"
    python tools/model_cli.py edit-config --proposal P --path simulation.relapse.base_prob --value 0.10
    python tools/model_cli.py edit-code --proposal P --file modules/health_mechanisms/scoring/nonlinear.py --from-file /tmp/x.py
    python tools/model_cli.py validate --proposal P
    python tools/model_cli.py promote --proposal P
    python tools/model_cli.py approve --model M          # 专家批准，写入 live
    python tools/model_cli.py rollback --model M_prev

说明：
  - propose/edit 默认不改 active.json / 线上代码
  - approve/activate 才会落地，并默认先 autosave 当前 live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.health_mechanisms.ai_edit import AIEditAPI  # noqa: E402
from modules.health_mechanisms.model_version import ModelVersionStore  # noqa: E402
from modules.health_mechanisms.sandbox import run_sim, validate_target  # noqa: E402
from modules.mechanism_config.schema import MechanismConfigError  # noqa: E402
from modules.mechanism_config.ui_tunable import assert_ui_tunable_json_path  # noqa: E402


def _api() -> AIEditAPI:
    return AIEditAPI()


def _store() -> ModelVersionStore:
    return ModelVersionStore()


def cmd_roots(_: argparse.Namespace) -> int:
    roots = _api().editable_roots()
    print("editable roots (relative to generative_agents/):")
    for r in roots:
        print(f"  - {r}")
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    pid = _api().propose(
        name=args.name,
        note=args.note or "",
        created_by=args.by,
        base_model_id=args.base_model,
    )
    print(f"proposal: {pid}")
    print("(draft — live tree unchanged)")
    return 0


def cmd_list_proposals(_: argparse.Namespace) -> int:
    rows = _store().list_proposals()
    if not rows:
        print("(no proposals)")
        return 0
    print(f"{'ID':<42} {'STATUS':<14} {'BY':<8} NAME")
    print("-" * 90)
    for r in rows:
        print(
            f"{str(r.get('id', '')):<42} {str(r.get('status', '')):<14} "
            f"{str(r.get('created_by', '')):<8} {r.get('name', '')}"
        )
    return 0


def cmd_list_models(_: argparse.Namespace) -> int:
    rows = _store().list_models()
    if not rows:
        print("(no models)")
        return 0
    print(f"{'ACTIVE':<8} {'ID':<42} {'STATUS':<12} {'BY':<8} NAME")
    print("-" * 100)
    for r in rows:
        mark = "*" if r.get("active") else ""
        print(
            f"{mark:<8} {str(r.get('id', '')):<42} {str(r.get('status', '')):<12} "
            f"{str(r.get('created_by', '')):<8} {r.get('name', '')}"
        )
    print(f"\nactive_model_id: {_store().get_active_model_id()}")
    return 0


def cmd_edit_config(args: argparse.Namespace) -> int:
    assert_ui_tunable_json_path(args.path)
    _api().edit_config(
        args.proposal,
        dotted_path=args.path,
        value=args.value,
    )
    print(f"updated proposal config: {args.proposal}")
    print(f"  {args.path} = {args.value}")
    return 0


def cmd_edit_code(args: argparse.Namespace) -> int:
    if args.from_file:
        content = Path(args.from_file).read_text(encoding="utf-8")
    elif args.content is not None:
        content = args.content
    else:
        raise MechanismConfigError("需要 --from-file 或 --content")
    _api().edit_code(args.proposal, args.file, content)
    print(f"updated proposal code: {args.proposal}")
    print(f"  file: {args.file}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    store = _store()
    if args.proposal:
        result = validate_target(store, args.proposal, is_proposal=True)
        label = f"proposal {args.proposal}"
    else:
        result = validate_target(store, args.model, is_proposal=False)
        label = f"model {args.model}"
    print(f"validate {label}: {result.get('status')}")
    print(json.dumps(result.get("checks", {}), ensure_ascii=False, indent=2))
    if result.get("errors"):
        print("errors:")
        for e in result["errors"]:
            print(f"  - {e}")
        return 1
    return 0


def cmd_sandbox(args: argparse.Namespace) -> int:
    store = _store()
    is_prop = bool(args.proposal)
    tid = args.proposal or args.model
    if args.run_sim:
        result = run_sim(
            store,
            tid,
            is_proposal=is_prop,
            days=args.days,
            scenario=args.scenario,
            with_code=args.with_code,
        )
    else:
        result = validate_target(store, tid, is_proposal=is_prop)
    print(json.dumps({k: result[k] for k in result if k not in {"stdout_tail", "stderr_tail", "traceback", "validate"}}, ensure_ascii=False, indent=2))
    if result.get("stdout_tail"):
        print("\n--- stdout (tail) ---")
        print(result["stdout_tail"])
    if result.get("stderr_tail"):
        print("\n--- stderr (tail) ---")
        print(result["stderr_tail"])
    return 0 if result.get("status") == "ok" else 1


def cmd_promote(args: argparse.Namespace) -> int:
    mid = _api().promote(args.proposal, name=args.name)
    print(f"model: {mid}")
    print("(proposed — not live until approve)")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    autosaved = _api().approve(
        args.model,
        apply_code=not args.config_only,
        autosave=not args.no_autosave,
    )
    print(f"activated model: {args.model}")
    print(f"autosaved: {autosaved}")
    print(f"active_model_id: {_store().get_active_model_id()}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    autosaved = _api().rollback(args.model, apply_code=not args.config_only)
    print(f"rolled back to: {args.model}")
    print(f"autosaved: {autosaved}")
    print(f"active_model_id: {_store().get_active_model_id()}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    mid = _store().save_live_as_model(
        name=args.name,
        note=args.note or "",
        created_by=args.by,
        set_active=args.set_active,
    )
    print(f"snapshot model: {mid}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Model Version / AI edit CLI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("roots", help="显示 AI 可编辑目录白名单")
    s.set_defaults(func=cmd_roots)

    s = sub.add_parser("propose", help="创建 draft proposal（不改 live）")
    s.add_argument("--name", required=True)
    s.add_argument("--note", default="")
    s.add_argument("--by", default="ai", help="created_by: ai|expert|system")
    s.add_argument("--base-model", default=None, help="基于已有 model 创建")
    s.set_defaults(func=cmd_propose)

    s = sub.add_parser("list-proposals", help="列出 proposals")
    s.set_defaults(func=cmd_list_proposals)

    s = sub.add_parser("list-models", help="列出 model versions")
    s.set_defaults(func=cmd_list_models)

    s = sub.add_parser("edit-config", help="在 proposal 内改参数")
    s.add_argument("--proposal", required=True)
    s.add_argument("--path", required=True, help="点分路径，如 simulation.relapse.base_prob")
    s.add_argument("--value", required=True, help="JSON 或字符串值")
    s.set_defaults(func=cmd_edit_config)

    s = sub.add_parser("edit-code", help="在 proposal 内改机制代码/prompt")
    s.add_argument("--proposal", required=True)
    s.add_argument("--file", required=True, help="相对 generative_agents/ 的路径")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-file", help="从本地文件读取新内容")
    g.add_argument("--content", help="直接传入文件内容")
    s.set_defaults(func=cmd_edit_code)

    s = sub.add_parser("validate", help="校验 proposal/model（AST+config+scorer）")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--proposal")
    g.add_argument("--model")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("sandbox", help="沙箱：默认 validate；可 --run-sim")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--proposal")
    g.add_argument("--model")
    s.add_argument("--run-sim", action="store_true", help="真正跑短仿真")
    s.add_argument("--with-code", action="store_true", help="用 proposal 代码 overlay 跑")
    s.add_argument("--days", type=int, default=1)
    s.add_argument("--scenario", default="diabetes")
    s.set_defaults(func=cmd_sandbox)

    s = sub.add_parser("promote", help="proposal → 不可变 model（仍不进 live）")
    s.add_argument("--proposal", required=True)
    s.add_argument("--name", default=None)
    s.set_defaults(func=cmd_promote)

    s = sub.add_parser("approve", help="专家批准：写入 live config/code")
    s.add_argument("--model", required=True)
    s.add_argument("--config-only", action="store_true", help="只激活 JSON，不写代码")
    s.add_argument("--no-autosave", action="store_true")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("rollback", help="回滚到指定 model")
    s.add_argument("--model", required=True)
    s.add_argument("--config-only", action="store_true")
    s.set_defaults(func=cmd_rollback)

    s = sub.add_parser("snapshot", help="把当前 live 存成 model 快照")
    s.add_argument("--name", required=True)
    s.add_argument("--note", default="")
    s.add_argument("--by", default="expert")
    s.add_argument("--set-active", action="store_true")
    s.set_defaults(func=cmd_snapshot)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except MechanismConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
