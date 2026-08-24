"""HTTP routes: visualization pages."""

from __future__ import annotations

from flask import Blueprint, render_template

from viz_backend.services.scenarios import list_scenario_summaries

bp = Blueprint("viz_pages", __name__)


@bp.route("/")
def index():
    return render_template("health_index.html", scenarios=list_scenario_summaries())


@bp.route("/editor")
def editor_page():
    return render_template("health_editor.html")
