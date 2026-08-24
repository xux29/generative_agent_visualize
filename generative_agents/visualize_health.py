"""Health Simulation Visualization — unified entry via viz_backend."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viz_backend.app import create_app
from viz_backend.config import DEFAULT_HOST, DEFAULT_PORT

app = create_app()


def create_templates() -> None:
    """Legacy bootstrap: only used if template files are missing."""
    template_dir = Path("frontend/templates")
    if (template_dir / "health_index.html").is_file():
        return
    # Templates ship in repo; no-op when present.
    template_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Health Simulation Visualization")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Server host")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    args = parser.parse_args()
    create_templates()
    print(f"Starting health visualization server at http://{args.host}:{args.port}")
    print("  /          场景列表")
    print("  /editor    机制编辑（AI + 滑杆 + 探针）")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
