"""Mechanism registry: maps logical mechanism names to code + config paths.

JSON 定义「这个机制用什么参数 / 实现在哪」；Python 代码定义「机制怎么算」。
AI 可编辑范围见 registry.json meta.editable_code_roots。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "mechanism" / "registry.json"
)


class MechanismRegistryError(Exception):
    """Registry load / lookup error."""


@lru_cache(maxsize=1)
def _load_raw() -> Dict[str, Any]:
    if not REGISTRY_PATH.exists():
        raise MechanismRegistryError(f"Registry not found: {REGISTRY_PATH}")
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def reload_registry() -> Dict[str, Any]:
    """Clear cache and reload registry from disk."""
    _load_raw.cache_clear()
    return _load_raw()


def get_registry() -> Dict[str, Any]:
    """Full registry document (meta + mechanisms)."""
    return _load_raw()


def list_mechanisms() -> List[str]:
    """Sorted mechanism ids."""
    return sorted(_load_raw().get("mechanisms", {}).keys())


def get_mechanism(name: str) -> Dict[str, Any]:
    """Return one mechanism entry or raise."""
    mechs = _load_raw().get("mechanisms", {})
    if name not in mechs:
        raise MechanismRegistryError(
            f"Unknown mechanism '{name}'. Known: {', '.join(sorted(mechs))}"
        )
    return mechs[name]


def get_implementation(name: str) -> str:
    return get_mechanism(name)["implementation"]


def get_config_path(name: str) -> Optional[str]:
    return get_mechanism(name).get("config_path")


def get_prompt_templates(name: str) -> List[str]:
    return list(get_mechanism(name).get("prompts") or [])


def editable_code_roots() -> List[str]:
    return list(_load_raw().get("meta", {}).get("editable_code_roots") or [])


def ai_editable_mechanisms() -> Dict[str, Dict[str, Any]]:
    """Mechanisms with editable_by_ai=true (docs/界面可调参数.md scope)."""
    return {
        mid: entry
        for mid, entry in _load_raw().get("mechanisms", {}).items()
        if entry.get("editable_by_ai")
    }


def mechanisms_by_config_prefix(prefix: str) -> Dict[str, Dict[str, Any]]:
    """Mechanisms whose config_path starts with prefix (e.g. 'simulation.')."""
    out = {}
    for mid, entry in _load_raw().get("mechanisms", {}).items():
        cp = entry.get("config_path") or ""
        if cp.startswith(prefix) or cp == prefix.rstrip("."):
            out[mid] = entry
    return out
