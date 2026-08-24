"""Flask extensions: logging, error handlers, health check."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import jsonify

from modules.mechanism_config.schema import MechanismConfigError

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger("viz_backend")


def init_app(app: "Flask") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    @app.errorhandler(MechanismConfigError)
    def handle_mechanism_error(exc: MechanismConfigError):
        logger.warning("MechanismConfigError: %s", exc)
        return jsonify({"error": str(exc)}), 400

    @app.errorhandler(404)
    def handle_not_found(_exc):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(500)
    def handle_server_error(exc):
        logger.exception("Unhandled error: %s", exc)
        return jsonify({"error": "internal server error"}), 500

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "viz_backend"})
