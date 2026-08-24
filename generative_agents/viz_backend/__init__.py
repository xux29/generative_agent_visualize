"""Visualization page backend — APIs for mechanism tabs, probes, scenarios, and AI editor.

Separate from the LLM simulator (`start_health_simulation*.py`).

Entry points:
  python viz_server.py
  python visualize_health.py   # same app factory, default port 5002
"""

from viz_backend.app import create_app

__all__ = ["create_app"]
