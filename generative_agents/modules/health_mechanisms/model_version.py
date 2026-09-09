"""Unified Model Version: mechanism config + editable code snapshot.

A Model Version binds:
  - config.json     (mechanism parameters)
  - code/           (files under AI-editable roots)
  - meta.json       (status, parent, note, sandbox results)

Lifecycle::

    propose (draft) → edit config/code → validate/sandbox → approve/activate
                                                         → reject / rollback
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.mechanism_config.loader import (
    DEFAULT_ACTIVE_PATH,
    MECHANISM_DATA_DIR,
    load_mechanism_config,
    reset_mechanism_config,
)
from modules.mechanism_config.schema import MechanismConfigError, validate_config
from modules.health_mechanisms.registry import editable_code_roots

GA_ROOT = Path(__file__).resolve().parents[2]  # generative_agents/
MODELS_DIR = MECHANISM_DATA_DIR / "models"
PROPOSALS_DIR = MECHANISM_DATA_DIR / "proposals"
MANIFEST_PATH = MODELS_DIR / "manifest.json"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_\-]+")

# Fallback AI-editable paths (posix, relative to GA_ROOT). Prefer registry.json
# meta.editable_code_roots. Scope = docs/界面可调参数.md mechanisms only;
# file-level paths — no whole-package edits, no add/delete of mechanisms.
DEFAULT_EDITABLE_ROOTS = [
    "modules/health_mechanisms/scoring/nonlinear.py",
    "modules/health_mechanisms/management/strategy.py",
    "modules/health_mechanisms/agent_mixin.py",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("_", name.strip()).strip("_").lower()
    return slug[:48] or "unnamed"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise MechanismConfigError(f"期望 JSON 对象: {path}")
    return data


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_editable_roots() -> List[str]:
    """Return editable roots relative to generative_agents/."""
    try:
        roots = editable_code_roots()
    except Exception:
        roots = []
    if not roots:
        roots = list(DEFAULT_EDITABLE_ROOTS)
    # normalize: strip trailing slashes
    return [r.rstrip("/").replace("\\", "/") for r in roots]


def assert_editable_relpath(rel_path: str) -> Path:
    """Validate rel_path is inside editable roots; return absolute path under GA_ROOT.

    Roots may be directories or exact files (docs/界面可调参数.md mechanism scope).
    New mechanism files cannot be introduced: path must already exist on disk.
    """
    rel = rel_path.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise MechanismConfigError(f"禁止路径穿越: {rel_path}")
    roots = resolve_editable_roots()
    ok = any(rel == root or rel.startswith(root + "/") for root in roots)
    if not ok:
        raise MechanismConfigError(
            f"路径不在 AI 可编辑范围: {rel_path}；允许: {roots}"
        )
    abs_path = (GA_ROOT / rel).resolve()
    if not str(abs_path).startswith(str(GA_ROOT.resolve())):
        raise MechanismConfigError(f"路径越界: {rel_path}")
    # Disallow inventing new files (add mechanism); only modify existing ones.
    if not abs_path.is_file():
        raise MechanismConfigError(
            f"禁止新增机制文件（只允许修改已有文件）: {rel_path}"
        )
    return abs_path


def snapshot_editable_code(ga_root: Optional[Path] = None) -> Dict[str, str]:
    """Collect editable files → {relative_posix_path: content}."""
    root = Path(ga_root) if ga_root else GA_ROOT
    files: Dict[str, str] = {}
    for rel_root in resolve_editable_roots():
        base = root / rel_root
        if not base.exists():
            continue
        if base.is_file():
            files[rel_root.replace("\\", "/")] = base.read_text(encoding="utf-8")
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".txt", ".md", ".json"}:
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            rel = path.relative_to(root).as_posix()
            files[rel] = path.read_text(encoding="utf-8")
    return files


def code_manifest(files: Dict[str, str]) -> Dict[str, str]:
    return {k: _sha256_text(v) for k, v in sorted(files.items())}


class ModelVersionStore:
    """Unified model versions (config + code) and mutable proposals."""

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        proposals_dir: Optional[Path] = None,
        active_config_path: Optional[Path] = None,
        ga_root: Optional[Path] = None,
    ):
        self.ga_root = Path(ga_root) if ga_root else GA_ROOT
        self.models_dir = Path(models_dir) if models_dir else MODELS_DIR
        self.proposals_dir = Path(proposals_dir) if proposals_dir else PROPOSALS_DIR
        self.active_config_path = (
            Path(active_config_path) if active_config_path else DEFAULT_ACTIVE_PATH
        )
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.models_dir / "manifest.json"

    # ------------------------------------------------------------------
    # manifest
    # ------------------------------------------------------------------

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"active_model_id": None, "models": []}
        data = _read_json(self.manifest_path)
        data.setdefault("active_model_id", None)
        data.setdefault("models", [])
        return data

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        _write_json(self.manifest_path, manifest)

    def _generate_id(self, prefix: str, name: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = f"{prefix}_{stamp}_{_slugify(name)}"
        candidate = base
        n = 1
        while (self.models_dir / candidate).exists() or (
            self.proposals_dir / candidate
        ).exists():
            n += 1
            candidate = f"{base}_{n}"
        return candidate

    # ------------------------------------------------------------------
    # proposal (mutable workspace for AI edits)
    # ------------------------------------------------------------------

    def create_proposal(
        self,
        name: str,
        note: str = "",
        created_by: str = "ai",
        base_model_id: Optional[str] = None,
    ) -> str:
        """Create a draft proposal from live tree (or a model snapshot)."""
        if not name or not str(name).strip():
            raise MechanismConfigError("create_proposal 需要非空 name")

        proposal_id = self._generate_id("p", name)
        dest = self.proposals_dir / proposal_id
        dest.mkdir(parents=True, exist_ok=False)

        if base_model_id:
            model_dir = self.models_dir / base_model_id
            if not model_dir.is_dir():
                raise MechanismConfigError(f"base model 不存在: {base_model_id}")
            config = validate_config(_read_json(model_dir / "config.json"))
            files = {}
            code_dir = model_dir / "code"
            for path in code_dir.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(code_dir).as_posix()
                    # code/ stores files with full rel paths flattened?
                    files[rel] = path.read_text(encoding="utf-8")
            # Our store writes code with full ga-relative paths mirrored
            parent = base_model_id
        else:
            config = load_mechanism_config(str(self.active_config_path))
            files = snapshot_editable_code(self.ga_root)
            parent = self.get_active_model_id()

        _write_json(dest / "config.json", config)
        self._write_code_tree(dest / "code", files)
        _write_json(dest / "code_manifest.json", code_manifest(files))
        meta = {
            "id": proposal_id,
            "name": name,
            "note": note or "",
            "status": "draft",
            "created_by": created_by,
            "created_at": _utc_now_iso(),
            "parent_model_id": parent,
            "sandbox": None,
        }
        _write_json(dest / "meta.json", meta)
        return proposal_id

    def _write_code_tree(self, code_root: Path, files: Dict[str, str]) -> None:
        if code_root.exists():
            shutil.rmtree(code_root)
        code_root.mkdir(parents=True)
        for rel, content in files.items():
            # store under code/ using the same relative path as GA_ROOT
            path = code_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _read_code_tree(self, code_root: Path) -> Dict[str, str]:
        files: Dict[str, str] = {}
        if not code_root.is_dir():
            return files
        for path in code_root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(code_root).as_posix()
                files[rel] = path.read_text(encoding="utf-8")
        return files

    def proposal_dir(self, proposal_id: str) -> Path:
        path = self.proposals_dir / proposal_id
        if not path.is_dir():
            raise MechanismConfigError(f"proposal 不存在: {proposal_id}")
        return path

    def get_proposal_meta(self, proposal_id: str) -> Dict[str, Any]:
        return _read_json(self.proposal_dir(proposal_id) / "meta.json")

    def list_proposals(self) -> List[Dict[str, Any]]:
        out = []
        if not self.proposals_dir.is_dir():
            return out
        for path in sorted(self.proposals_dir.iterdir()):
            meta_path = path / "meta.json"
            if meta_path.is_file():
                out.append(_read_json(meta_path))
        return out

    def edit_proposal_config(
        self,
        proposal_id: str,
        config: Optional[Dict[str, Any]] = None,
        dotted_path: Optional[str] = None,
        value: Any = None,
    ) -> None:
        """Replace full config or set one dotted path. Does NOT touch active.json."""
        dest = self.proposal_dir(proposal_id)
        meta = _read_json(dest / "meta.json")
        if meta.get("status") not in {"draft", "validated", "sandbox_failed"}:
            raise MechanismConfigError(
                f"proposal 状态为 {meta.get('status')}，不可再编辑"
            )

        if config is not None:
            validated = validate_config(config)
        else:
            if not dotted_path:
                raise MechanismConfigError("需要 config 或 dotted_path")
            current = _read_json(dest / "config.json")
            self._set_dotted(current, dotted_path, value)
            validated = validate_config(current)

        _write_json(dest / "config.json", validated)
        meta["updated_at"] = _utc_now_iso()
        meta["status"] = "draft"
        _write_json(dest / "meta.json", meta)

    @staticmethod
    def _set_dotted(obj: Dict[str, Any], dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        cur: Any = obj
        for p in parts[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
        # coerce simple JSON scalars from strings
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        cur[parts[-1]] = value

    def edit_proposal_code(
        self,
        proposal_id: str,
        rel_path: str,
        content: str,
    ) -> None:
        """Write one editable file inside the proposal. Does NOT touch live code."""
        # Validate against whitelist using the relative path as it will appear in GA
        assert_editable_relpath(rel_path)
        dest = self.proposal_dir(proposal_id)
        meta = _read_json(dest / "meta.json")
        if meta.get("status") not in {"draft", "validated", "sandbox_failed"}:
            raise MechanismConfigError(
                f"proposal 状态为 {meta.get('status')}，不可再编辑"
            )

        rel = rel_path.replace("\\", "/").lstrip("/")
        path = dest / "code" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        files = self._read_code_tree(dest / "code")
        _write_json(dest / "code_manifest.json", code_manifest(files))
        meta["updated_at"] = _utc_now_iso()
        meta["status"] = "draft"
        _write_json(dest / "meta.json", meta)

    def promote_proposal(self, proposal_id: str, name: Optional[str] = None) -> str:
        """Freeze proposal into an immutable model version (status=proposed)."""
        src = self.proposal_dir(proposal_id)
        meta = _read_json(src / "meta.json")
        model_name = name or meta.get("name") or proposal_id
        model_id = self._generate_id("m", model_name)
        dest = self.models_dir / model_id
        dest.mkdir(parents=True, exist_ok=False)

        shutil.copy2(src / "config.json", dest / "config.json")
        if (src / "code").exists():
            shutil.copytree(src / "code", dest / "code")
        shutil.copy2(src / "code_manifest.json", dest / "code_manifest.json")

        model_meta = {
            "id": model_id,
            "name": model_name,
            "note": meta.get("note", ""),
            "status": "proposed",
            "created_by": meta.get("created_by", "ai"),
            "created_at": _utc_now_iso(),
            "parent_model_id": meta.get("parent_model_id"),
            "source_proposal_id": proposal_id,
            "sandbox": meta.get("sandbox"),
        }
        _write_json(dest / "meta.json", model_meta)

        manifest = self._load_manifest()
        manifest["models"].append(
            {
                "id": model_id,
                "name": model_name,
                "created_at": model_meta["created_at"],
                "note": model_meta.get("note", ""),
                "status": "proposed",
                "created_by": model_meta.get("created_by"),
            }
        )
        self._save_manifest(manifest)

        meta["status"] = "promoted"
        meta["model_id"] = model_id
        _write_json(src / "meta.json", meta)
        return model_id

    # ------------------------------------------------------------------
    # model versions
    # ------------------------------------------------------------------

    def model_dir(self, model_id: str) -> Path:
        path = self.models_dir / model_id
        if not path.is_dir():
            raise MechanismConfigError(f"model 不存在: {model_id}")
        return path

    def get_active_model_id(self) -> Optional[str]:
        return self._load_manifest().get("active_model_id")

    def list_models(self) -> List[Dict[str, Any]]:
        manifest = self._load_manifest()
        active = manifest.get("active_model_id")
        out = []
        for entry in manifest.get("models", []):
            item = dict(entry)
            item["active"] = entry.get("id") == active
            # refresh status from meta if present
            meta_path = self.models_dir / entry["id"] / "meta.json"
            if meta_path.is_file():
                item["status"] = _read_json(meta_path).get("status", item.get("status"))
            out.append(item)
        return out

    def get_model_meta(self, model_id: str) -> Dict[str, Any]:
        return _read_json(self.model_dir(model_id) / "meta.json")

    def save_live_as_model(
        self,
        name: str,
        note: str = "",
        created_by: str = "expert",
        set_active: bool = False,
    ) -> str:
        """Snapshot current live config+code as a model version."""
        model_id = self._generate_id("m", name)
        dest = self.models_dir / model_id
        dest.mkdir(parents=True, exist_ok=False)

        config = load_mechanism_config(str(self.active_config_path))
        files = snapshot_editable_code(self.ga_root)
        _write_json(dest / "config.json", config)
        self._write_code_tree(dest / "code", files)
        _write_json(dest / "code_manifest.json", code_manifest(files))
        meta = {
            "id": model_id,
            "name": name,
            "note": note or "",
            "status": "approved" if set_active else "snapshot",
            "created_by": created_by,
            "created_at": _utc_now_iso(),
            "parent_model_id": self.get_active_model_id(),
            "sandbox": None,
        }
        _write_json(dest / "meta.json", meta)

        manifest = self._load_manifest()
        manifest["models"].append(
            {
                "id": model_id,
                "name": name,
                "created_at": meta["created_at"],
                "note": note or "",
                "status": meta["status"],
                "created_by": created_by,
            }
        )
        if set_active:
            manifest["active_model_id"] = model_id
        self._save_manifest(manifest)
        return model_id

    def activate(
        self,
        model_id: str,
        apply_code: bool = True,
        autosave: bool = True,
    ) -> str:
        """Apply model config (and optionally code) to the live tree.

        Returns:
            autosaved model id (if any) or model_id
        """
        src = self.model_dir(model_id)
        autosaved = ""
        if autosave:
            autosaved = self.save_live_as_model(
                name=f"auto_before_activate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                note=f"activate 前自动快照（目标: {model_id}）",
                created_by="system",
                set_active=False,
            )

        # config → active.json
        config = validate_config(_read_json(src / "config.json"))
        _write_json(self.active_config_path, config)
        reset_mechanism_config()

        if apply_code:
            files = self._read_code_tree(src / "code")
            for rel, content in files.items():
                assert_editable_relpath(rel)
                path = self.ga_root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

        meta = _read_json(src / "meta.json")
        meta["status"] = "active"
        meta["activated_at"] = _utc_now_iso()
        _write_json(src / "meta.json", meta)

        manifest = self._load_manifest()
        # demote previous active status in meta files
        prev = manifest.get("active_model_id")
        if prev and prev != model_id:
            prev_meta_path = self.models_dir / prev / "meta.json"
            if prev_meta_path.is_file():
                prev_meta = _read_json(prev_meta_path)
                if prev_meta.get("status") == "active":
                    prev_meta["status"] = "approved"
                    _write_json(prev_meta_path, prev_meta)
        manifest["active_model_id"] = model_id
        for entry in manifest.get("models", []):
            if entry.get("id") == model_id:
                entry["status"] = "active"
        self._save_manifest(manifest)
        return autosaved or model_id

    def rollback(self, model_id: str, apply_code: bool = True) -> str:
        """Rollback live tree to a previous model (autosave current first)."""
        return self.activate(model_id, apply_code=apply_code, autosave=True)

    def update_sandbox_result(
        self,
        target_id: str,
        result: Dict[str, Any],
        *,
        is_proposal: bool = True,
    ) -> None:
        """Attach sandbox result to proposal or model meta."""
        if is_proposal:
            dest = self.proposal_dir(target_id)
        else:
            dest = self.model_dir(target_id)
        meta = _read_json(dest / "meta.json")
        meta["sandbox"] = result
        status = result.get("status")
        if status == "ok":
            meta["status"] = "validated"
        elif status == "failed":
            meta["status"] = "sandbox_failed"
        meta["updated_at"] = _utc_now_iso()
        _write_json(dest / "meta.json", meta)

    def diff_code(
        self,
        a_id: str,
        b_id: str,
        *,
        a_is_proposal: bool = False,
        b_is_proposal: bool = False,
    ) -> Dict[str, Any]:
        """Diff code manifests between two proposals/models."""
        def _files(oid: str, is_prop: bool) -> Dict[str, str]:
            root = self.proposal_dir(oid) if is_prop else self.model_dir(oid)
            return self._read_code_tree(root / "code")

        fa, fb = _files(a_id, a_is_proposal), _files(b_id, b_is_proposal)
        keys = sorted(set(fa) | set(fb))
        changes = {}
        for k in keys:
            ha = _sha256_text(fa[k]) if k in fa else None
            hb = _sha256_text(fb[k]) if k in fb else None
            if ha != hb:
                changes[k] = {
                    "a_sha": ha,
                    "b_sha": hb,
                    "a_missing": k not in fa,
                    "b_missing": k not in fb,
                }
        return {"a": a_id, "b": b_id, "changes": changes}
