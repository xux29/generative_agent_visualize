"""Load mechanism config for viz (live, baseline, or proposal draft)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from modules.mechanism_config import load_defaults, load_mechanism_config
from modules.mechanism_config.schema import MechanismConfigError, deep_merge, validate_config
from modules.health_mechanisms.model_version import ModelVersionStore


def load_live_config() -> Dict[str, Any]:
    return load_mechanism_config()


def load_baseline_config() -> Dict[str, Any]:
    base = load_defaults()
    return validate_config(deepcopy(base))


def load_proposal_config(proposal_id: str) -> Dict[str, Any]:
    store = ModelVersionStore()
    path = store.proposal_dir(proposal_id) / "config.json"
    if not path.is_file():
        raise MechanismConfigError(f"proposal 不存在或无 config: {proposal_id}")
    with open(path, "r", encoding="utf-8") as f:
        return validate_config(json.load(f))


def resolve_config(proposal_id: Optional[str] = None) -> Dict[str, Any]:
    if proposal_id:
        return load_proposal_config(proposal_id)
    return load_live_config()
