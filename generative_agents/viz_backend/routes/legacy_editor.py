"""Backward-compatible /api/editor/* routes for older frontends."""

from __future__ import annotations

from flask import jsonify, render_template, request

from modules.health_mechanisms.ai_edit import AIEditAPI
from modules.mechanism_config import list_ui_param_specs, load_mechanism_config, read_ui_param, write_ui_param
from modules.mechanism_config.schema import MechanismConfigError
from viz_backend.services.config_loader import load_proposal_config
from viz_backend.services.editor_agent import (
    approve_model,
    chat_turn,
    config_status,
    list_editor_state,
)


def register_legacy_editor_routes(app) -> None:
    @app.route("/editor")
    def editor_page():
        return render_template("health_editor.html")

    @app.route("/api/editor/status")
    def editor_status():
        return jsonify(config_status())

    @app.route("/api/editor/state")
    def editor_state():
        return jsonify(list_editor_state())

    @app.route("/api/editor/tunable-params")
    def editor_tunable_params():
        proposal_id = request.args.get("proposal_id")
        cfg = load_mechanism_config()
        if proposal_id:
            try:
                cfg = load_proposal_config(proposal_id)
            except MechanismConfigError:
                pass
        values = {spec["key"]: read_ui_param(cfg, spec["key"]) for spec in list_ui_param_specs()}
        return jsonify({"params": list_ui_param_specs(), "values": values})

    @app.route("/api/editor/tune", methods=["POST"])
    def editor_tune():
        body = request.get_json(silent=True) or {}
        ui_key = (body.get("ui_key") or "").strip()
        proposal_id = (body.get("proposal_id") or "").strip()
        if not ui_key or not proposal_id or body.get("value") is None:
            return jsonify({"error": "need ui_key, proposal_id, value"}), 400
        try:
            cfg = load_proposal_config(proposal_id)
            before = read_ui_param(cfg, ui_key)
            updated = write_ui_param(cfg, ui_key, float(body["value"]))
            AIEditAPI().edit_config(proposal_id, config=updated)
            after = read_ui_param(updated, ui_key)
            return jsonify({"ok": True, "ui_key": ui_key, "before": before, "after": after})
        except MechanismConfigError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/editor/propose", methods=["POST"])
    def editor_propose():
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "ui_tune").strip()
        note = (body.get("note") or "界面滑杆调参").strip()
        pid = AIEditAPI().propose(name=name, note=note, created_by="viz_ui")
        return jsonify({"proposal_id": pid})

    @app.route("/api/editor/chat", methods=["POST"])
    def editor_chat():
        body = request.get_json(silent=True) or {}
        text = (body.get("message") or "").strip()
        if not text:
            return jsonify({"error": "empty message", "reply": "请输入要改的机制或参数。"}), 400
        return jsonify(chat_turn(text, session_id=body.get("session_id")))

    @app.route("/api/editor/approve", methods=["POST"])
    def editor_approve():
        body = request.get_json(silent=True) or {}
        model_id = (body.get("model_id") or "").strip()
        if not model_id:
            return jsonify({"error": "missing model_id"}), 400
        try:
            return jsonify(approve_model(model_id, config_only=bool(body.get("config_only"))))
        except MechanismConfigError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/editor/rollback", methods=["POST"])
    def editor_rollback():
        body = request.get_json(silent=True) or {}
        model_id = (body.get("model_id") or "").strip()
        if not model_id:
            return jsonify({"error": "missing model_id"}), 400
        try:
            applied = AIEditAPI().rollback(model_id, apply_code=not bool(body.get("config_only")))
            return jsonify({"ok": True, "applied": applied, "model_id": model_id})
        except MechanismConfigError as e:
            return jsonify({"error": str(e)}), 400
