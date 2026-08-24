"""Backward-compatible Flask route registration — delegates to viz_backend."""

from __future__ import annotations


def register_editor_routes(app) -> None:
    from viz_backend.routes.legacy_editor import register_legacy_editor_routes

    register_legacy_editor_routes(app)
