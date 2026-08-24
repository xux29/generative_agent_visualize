"""Visualization page backend — APIs for mechanism tabs, probes, and AI editor.

Separate from the LLM simulator (`start_health_simulation*.py`).
Entry: ``viz_backend.app.create_app()`` or ``python viz_server.py``.
"""

from viz_backend.app import create_app

__all__ = ["create_app"]
