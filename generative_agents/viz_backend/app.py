"""Flask application factory for the visualization backend."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from viz_backend.routes.editor import bp as editor_bp
from viz_backend.routes.mechanism import bp as mechanism_bp
from viz_backend.routes.pages import bp as pages_bp


def create_app() -> Flask:
    ga_root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(ga_root / "frontend" / "templates"),
        static_folder=str(ga_root / "frontend" / "static"),
    )
    app.register_blueprint(pages_bp)
    app.register_blueprint(mechanism_bp)
    app.register_blueprint(editor_bp)

    from viz_backend.routes.legacy_editor import register_legacy_editor_routes

    register_legacy_editor_routes(app)

    return app
