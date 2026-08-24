"""HTTP routes: visualization pages."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("viz_pages", __name__)


@bp.route("/")
def index():
    return render_template("health_editor.html")


@bp.route("/editor")
def editor_page():
    return render_template("health_editor.html")
