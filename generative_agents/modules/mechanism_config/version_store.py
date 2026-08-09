"""机制参数版本库：快照存档 / 激活 / 回退 / diff。

版本文件一经写入不可变；activate 将快照复制为 active.json。
"""

from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import (
    DEFAULT_ACTIVE_PATH,
    MECHANISM_DATA_DIR,
    load_mechanism_config,
    reset_mechanism_config,
)
from .schema import MechanismConfigError, flatten_diff, validate_config

VERSIONS_DIR = MECHANISM_DATA_DIR / "versions"
MANIFEST_PATH = VERSIONS_DIR / "manifest.json"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_\-]+")


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


class VersionStore:
    """机制配置版本存储。"""

    def __init__(
        self,
        versions_dir: Optional[Path] = None,
        active_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
    ):
        self.versions_dir = Path(versions_dir) if versions_dir else VERSIONS_DIR
        self.active_path = Path(active_path) if active_path else DEFAULT_ACTIVE_PATH
        self.manifest_path = Path(manifest_path) if manifest_path else (
            self.versions_dir / "manifest.json"
        )
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.active_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # manifest helpers
    # ------------------------------------------------------------------

    def _default_manifest(self) -> Dict[str, Any]:
        return {"active_id": None, "versions": []}

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.is_file():
            return self._default_manifest()
        data = _read_json(self.manifest_path)
        data.setdefault("active_id", None)
        data.setdefault("versions", [])
        return data

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        _write_json(self.manifest_path, manifest)

    def _version_path(self, version_id: str) -> Path:
        return self.versions_dir / f"{version_id}.json"

    def _generate_version_id(self, name: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = f"v_{stamp}_{_slugify(name)}"
        candidate = base
        n = 1
        while self._version_path(candidate).exists():
            n += 1
            candidate = f"{base}_{n}"
        return candidate

    def _find_entry(self, manifest: Dict[str, Any], version_id: str) -> Optional[Dict[str, Any]]:
        for entry in manifest.get("versions", []):
            if entry.get("id") == version_id:
                return entry
        return None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def get_active_id(self) -> Optional[str]:
        return self._load_manifest().get("active_id")

    def list_versions(self) -> List[Dict[str, Any]]:
        """列出版本；每项含 id/name/created_at/note/active。"""
        manifest = self._load_manifest()
        active_id = manifest.get("active_id")
        out: List[Dict[str, Any]] = []
        for entry in manifest.get("versions", []):
            item = {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "created_at": entry.get("created_at"),
                "note": entry.get("note", ""),
                "active": entry.get("id") == active_id,
            }
            out.append(item)
        return out

    def save(
        self,
        name: str,
        note: str = "",
        source_path: Optional[str] = None,
    ) -> str:
        """将当前 active（或指定文件）存为不可变版本快照。

        Returns:
            新版本 id
        """
        if not name or not str(name).strip():
            raise MechanismConfigError("save 需要非空 name")

        src = Path(source_path) if source_path else self.active_path
        if not src.is_file():
            raise MechanismConfigError(f"无法存档：源文件不存在 {src}")

        raw = _read_json(src)
        validated = validate_config(raw)

        version_id = self._generate_version_id(name)
        created_at = _utc_now_iso()

        snapshot = deepcopy(validated)
        meta = snapshot.setdefault("meta", {})
        meta["version_id"] = version_id
        meta["name"] = name
        meta["created_at"] = created_at
        meta["note"] = note or meta.get("note", "")

        dest = self._version_path(version_id)
        if dest.exists():
            raise MechanismConfigError(f"版本文件已存在（不可变，禁止覆盖）: {dest}")
        _write_json(dest, snapshot)

        manifest = self._load_manifest()
        manifest["versions"].append(
            {
                "id": version_id,
                "name": name,
                "created_at": created_at,
                "note": note or "",
                "file": dest.name,
            }
        )
        self._save_manifest(manifest)
        return version_id

    def activate(self, version_id: str) -> None:
        """将指定版本复制为 active.json，并更新 manifest.active_id。"""
        if not version_id:
            raise MechanismConfigError("activate 需要 version_id")

        src = self._version_path(version_id)
        if not src.is_file():
            raise MechanismConfigError(f"版本不存在: {version_id} ({src})")

        manifest = self._load_manifest()
        if self._find_entry(manifest, version_id) is None:
            # 允许磁盘上有文件但 manifest 未登记时补登记
            snapshot_meta = _read_json(src).get("meta", {})
            manifest["versions"].append(
                {
                    "id": version_id,
                    "name": snapshot_meta.get("name", version_id),
                    "created_at": snapshot_meta.get("created_at", _utc_now_iso()),
                    "note": snapshot_meta.get("note", ""),
                    "file": src.name,
                }
            )

        # 复制为 active（不修改版本源文件）
        shutil.copy2(src, self.active_path)
        manifest["active_id"] = version_id
        self._save_manifest(manifest)

        # 使进程内单例失效，下次 get 时重新加载
        reset_mechanism_config()

    def rollback(self, version_id: str, autosave: bool = True) -> str:
        """回退到指定版本（语义等同 activate）。

        Args:
            version_id: 目标版本
            autosave: 若为 True，先将当前 active 存为 auto_before_rollback_* 版本

        Returns:
            若 autosave 则返回自动存档的 version_id，否则返回目标 version_id
        """
        autosaved_id = ""
        if autosave and self.active_path.is_file():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            autosaved_id = self.save(
                name=f"auto_before_rollback_{stamp}",
                note=f"rollback 前自动保存（目标: {version_id}）",
            )
        self.activate(version_id)
        return autosaved_id or version_id

    def diff(self, a: str, b: str) -> Dict[str, Any]:
        """比较两个版本快照的点分路径差异。

        Returns:
            {
              "a": version_id,
              "b": version_id,
              "changes": { "path": {"a": val, "b": val}, ... }
            }
        """
        path_a = self._version_path(a)
        path_b = self._version_path(b)
        if not path_a.is_file():
            raise MechanismConfigError(f"版本不存在: {a}")
        if not path_b.is_file():
            raise MechanismConfigError(f"版本不存在: {b}")

        cfg_a = validate_config(_read_json(path_a))
        cfg_b = validate_config(_read_json(path_b))
        changes = flatten_diff(cfg_a, cfg_b)
        return {"a": a, "b": b, "changes": changes}

    def reload_active(self) -> Dict[str, Any]:
        """重新加载当前 active.json 到进程单例。"""
        return load_mechanism_config(str(self.active_path))
