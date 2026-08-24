#!/usr/bin/env python3
"""Start the visualization backend (mechanism tabs + AI editor + scenarios).

Usage:
    python viz_server.py
    VIZ_PORT=5002 VIZ_DEBUG=1 python viz_server.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viz_backend.app import create_app
from viz_backend.config import DEFAULT_HOST, DEFAULT_PORT

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("VIZ_HOST", DEFAULT_HOST)
    port = int(os.environ.get("VIZ_PORT", str(DEFAULT_PORT)))
    debug = os.environ.get("VIZ_DEBUG") == "1"
    print(f"viz_backend at http://{host}:{port}  (/health  /editor  /api/viz/*)")
    app.run(host=host, port=port, debug=debug)
