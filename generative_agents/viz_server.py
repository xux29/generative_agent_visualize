#!/usr/bin/env python3
"""Start the visualization backend (mechanism tabs + AI editor).

Usage:
    python viz_server.py
    VIZ_PORT=5002 python viz_server.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viz_backend.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("VIZ_PORT", "5002"))
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("VIZ_DEBUG") == "1")
