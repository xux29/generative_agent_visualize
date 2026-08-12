"""Sandbox validation / short simulation for model proposals.

Default mode is ``validate`` (config schema + Python AST + scorer smoke).
Optional ``run_sim`` launches a short batch simulation using proposal config
(live code). Use ``materialize`` when code changes must be exercised.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.health_mechanisms.model_version import (
    GA_ROOT,
    ModelVersionStore,
    _read_json,
    _utc_now_iso,
    _write_json,
)
from modules.mechanism_config import (
    reset_mechanism_config,
    set_mechanism_config,
    validate_config,
)
from modules.mechanism_config.schema import MechanismConfigError

SANDBOXES_DIR = GA_ROOT / "data" / "mechanism" / "sandboxes"


def _validate_python_files(files: Dict[str, str]) -> List[str]:
    errors = []
    for rel, content in files.items():
        if not rel.endswith(".py"):
            continue
        try:
            ast.parse(content, filename=rel)
        except SyntaxError as e:
            errors.append(f"{rel}: {e}")
    return errors


def validate_target(
    store: ModelVersionStore,
    target_id: str,
    *,
    is_proposal: bool = True,
) -> Dict[str, Any]:
    """Validate config + code syntax; smoke-test NonlinearHealthScorer with config."""
    root = store.proposal_dir(target_id) if is_proposal else store.model_dir(target_id)
    result: Dict[str, Any] = {
        "mode": "validate",
        "target_id": target_id,
        "started_at": _utc_now_iso(),
        "checks": {},
        "status": "ok",
        "errors": [],
    }
    try:
        raw = _read_json(root / "config.json")
        cfg = validate_config(raw)
        result["checks"]["config"] = "ok"

        files = store._read_code_tree(root / "code")
        py_errors = _validate_python_files(files)
        if py_errors:
            result["checks"]["ast"] = "failed"
            result["errors"].extend(py_errors)
            result["status"] = "failed"
        else:
            result["checks"]["ast"] = "ok"
            result["checks"]["file_count"] = len(files)

        # Scorer smoke with proposal config (does not require proposal code)
        prev = None
        try:
            set_mechanism_config(deepcopy(cfg))
            from modules.health_mechanisms.scoring.nonlinear import NonlinearHealthScorer

            scorer = NonlinearHealthScorer(initial_score=75, discipline_level="medium")
            change, _ = scorer.calculate_daily_change(
                agent_data={},
                had_violation=False,
                intervention_count=0,
                intervention_success=True,
                unblocked_violation_count=0,
            )
            result["checks"]["scorer_smoke"] = {
                "ok": True,
                "change": change,
                "warning_line": scorer.WARNING_LINE,
            }
        except Exception as e:
            result["checks"]["scorer_smoke"] = {"ok": False, "error": str(e)}
            result["errors"].append(f"scorer_smoke: {e}")
            result["status"] = "failed"
        finally:
            reset_mechanism_config()

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        result["traceback"] = traceback.format_exc()

    result["finished_at"] = _utc_now_iso()
    store.update_sandbox_result(target_id, result, is_proposal=is_proposal)
    _write_json(root / "sandbox_last.json", result)
    return result


def materialize_workspace(
    store: ModelVersionStore,
    target_id: str,
    *,
    is_proposal: bool = True,
) -> Path:
    """Build a runnable workspace with proposal code overlay (symlinks + copies)."""
    src = store.proposal_dir(target_id) if is_proposal else store.model_dir(target_id)
    out = SANDBOXES_DIR / target_id / "workspace"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Symlink top-level runtime needs from GA_ROOT
    for name in (
        "start_health_simulation.py",
        "start_health_simulation_visual.py",
        "tools",
        "frontend",
    ):
        src_path = GA_ROOT / name
        if src_path.exists():
            os.symlink(src_path, out / name)

    # modules: symlink each child except health_mechanisms (real copy from proposal)
    modules_out = out / "modules"
    modules_out.mkdir()
    live_modules = GA_ROOT / "modules"
    for child in live_modules.iterdir():
        if child.name == "health_mechanisms":
            continue
        if child.name == "__pycache__":
            continue
        os.symlink(child, modules_out / child.name)

    # Copy proposal health_mechanisms (only the package subtree under code/)
    code_root = src / "code"
    hm_src = code_root / "modules" / "health_mechanisms"
    if not hm_src.is_dir():
        raise MechanismConfigError(
            "proposal/model code 中缺少 modules/health_mechanisms"
        )
    shutil.copytree(hm_src, modules_out / "health_mechanisms")

    # data: symlink most; overlay mechanism active + prompts from proposal
    data_out = out / "data"
    data_out.mkdir()
    live_data = GA_ROOT / "data"
    for child in live_data.iterdir():
        if child.name == "mechanism":
            continue
        os.symlink(child, data_out / child.name)

    mech_out = data_out / "mechanism"
    mech_out.mkdir()
    live_mech = GA_ROOT / "data" / "mechanism"
    for child in live_mech.iterdir():
        if child.name in {"prompts", "active.json"}:
            continue
        # skip heavy runtime dirs we manage
        if child.name in {"sandboxes", "proposals", "models"}:
            continue
        os.symlink(child, mech_out / child.name)

    # active.json from proposal config
    shutil.copy2(src / "config.json", mech_out / "active.json")

    # prompts from proposal code tree
    prompts_src = code_root / "data" / "mechanism" / "prompts"
    if prompts_src.is_dir():
        shutil.copytree(prompts_src, mech_out / "prompts")
    else:
        os.symlink(live_mech / "prompts", mech_out / "prompts")

    return out


def run_sim(
    store: ModelVersionStore,
    target_id: str,
    *,
    is_proposal: bool = True,
    days: int = 1,
    scenario: str = "diabetes",
    with_code: bool = False,
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run a short health simulation in sandbox.

    - with_code=False: use live code + proposal config via --mechanism-config
    - with_code=True: materialize workspace overlay then run inside it
    """
    # Always validate first
    vresult = validate_target(store, target_id, is_proposal=is_proposal)
    if vresult.get("status") != "ok":
        return vresult

    root = store.proposal_dir(target_id) if is_proposal else store.model_dir(target_id)
    config_path = root / "config.json"
    started = _utc_now_iso()
    cmd: List[str]
    cwd: Path

    if with_code:
        workspace = materialize_workspace(store, target_id, is_proposal=is_proposal)
        cwd = workspace
        cmd = [
            sys.executable,
            "start_health_simulation.py",
            "--scenario",
            scenario,
            "--days",
            str(days),
            "--batch",
            "--mechanism-config",
            str(workspace / "data" / "mechanism" / "active.json"),
        ]
    else:
        cwd = GA_ROOT
        cmd = [
            sys.executable,
            str(GA_ROOT / "start_health_simulation.py"),
            "--scenario",
            scenario,
            "--days",
            str(days),
            "--batch",
            "--mechanism-config",
            str(config_path),
        ]

    if extra_args:
        cmd.extend(extra_args)

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(cwd if with_code else GA_ROOT)},
    )
    result = {
        "mode": "run_sim",
        "with_code": with_code,
        "target_id": target_id,
        "started_at": started,
        "finished_at": _utc_now_iso(),
        "command": cmd,
        "returncode": proc.returncode,
        "status": "ok" if proc.returncode == 0 else "failed",
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "validate": vresult,
        "errors": [] if proc.returncode == 0 else [f"exit={proc.returncode}"],
    }
    store.update_sandbox_result(target_id, result, is_proposal=is_proposal)
    _write_json(root / "sandbox_last.json", result)
    return result
