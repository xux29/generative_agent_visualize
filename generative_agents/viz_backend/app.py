"""Flask application factory for the visualization backend."""

from __future__ import annotations

from pathlib import Path

from flask import Flask

from viz_backend.extensions import init_app as init_extensions
from viz_backend.routes.editor import bp as editor_bp
from viz_backend.routes.mechanism import bp as mechanism_bp
from viz_backend.routes.pages import bp as pages_bp
from viz_backend.routes.scenarios import bp as scenarios_bp


def create_app(*, include_legacy_editor: bool = True) -> Flask:
    """Build the visualization Flask app (editor + mechanism tabs + scenarios)."""
    ga_root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(ga_root / "frontend" / "templates"),
        static_folder=str(ga_root / "frontend" / "static"),
    )
    init_extensions(app)
    app.register_blueprint(pages_bp)
    app.register_blueprint(scenarios_bp)
    app.register_blueprint(mechanism_bp)
    app.register_blueprint(editor_bp)

    if include_legacy_editor:
        from viz_backend.routes.legacy_editor import register_legacy_editor_routes

        register_legacy_editor_routes(app)

    return app
