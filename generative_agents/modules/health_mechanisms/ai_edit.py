"""AI dual-edit API: parameter JSON + mechanism code (whitelisted).

Does NOT modify live ``active.json`` or live code unless ``approve``/``activate``
is explicitly called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from modules.health_mechanisms.model_version import (
    ModelVersionStore,
    assert_editable_relpath,
    resolve_editable_roots,
)
from modules.mechanism_config.schema import MechanismConfigError


class AIEditAPI:
    """High-level AI editing surface."""

    def __init__(self, store: Optional[ModelVersionStore] = None):
        self.store = store or ModelVersionStore()

    def editable_roots(self):
        return resolve_editable_roots()

    def propose(
        self,
        name: str,
        note: str = "",
        created_by: str = "ai",
        base_model_id: Optional[str] = None,
    ) -> str:
        """Start a draft proposal from live (or base model)."""
        return self.store.create_proposal(
            name=name,
            note=note,
            created_by=created_by,
            base_model_id=base_model_id,
        )

    def edit_config(
        self,
        proposal_id: str,
        *,
        dotted_path: Optional[str] = None,
        value: Any = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Parameter edit — only inside the proposal."""
        self.store.edit_proposal_config(
            proposal_id,
            config=config,
            dotted_path=dotted_path,
            value=value,
        )

    def edit_code(
        self,
        proposal_id: str,
        rel_path: str,
        content: str,
    ) -> None:
        """Mechanism code edit — whitelisted paths only, proposal only."""
        assert_editable_relpath(rel_path)
        self.store.edit_proposal_code(proposal_id, rel_path, content)

    def edit_code_from_file(
        self,
        proposal_id: str,
        rel_path: str,
        source_file: str,
    ) -> None:
        src = Path(source_file)
        if not src.is_file():
            raise MechanismConfigError(f"源文件不存在: {source_file}")
        self.edit_code(proposal_id, rel_path, src.read_text(encoding="utf-8"))

    def promote(self, proposal_id: str, name: Optional[str] = None) -> str:
        """Freeze proposal → immutable model version (still not live)."""
        return self.store.promote_proposal(proposal_id, name=name)

    def approve(
        self,
        model_id: str,
        *,
        apply_code: bool = True,
        autosave: bool = True,
    ) -> str:
        """Expert approval: apply model to live tree."""
        return self.store.activate(
            model_id, apply_code=apply_code, autosave=autosave
        )

    def rollback(self, model_id: str, *, apply_code: bool = True) -> str:
        return self.store.rollback(model_id, apply_code=apply_code)
