"""Re-export — Skill loading lives in viz_backend.services.editor_skills."""

from viz_backend.services.editor_skills import (  # noqa: F401
    ROUTER_PREAMBLE,
    SKILL_CODE,
    SKILL_CONFIG,
    build_system_prompt,
    load_skill_text,
)
