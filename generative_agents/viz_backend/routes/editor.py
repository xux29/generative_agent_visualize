"""HTTP routes: AI editor (chat, propose, approve)."""

from __future__ import annotations

import requests
from flask import Blueprint, jsonify, request

from modules.health_mechanisms.ai_edit import AIEditAPI
from modules.mechanism_config import list_ui_param_specs, load_mechanism_config, read_ui_param, write_ui_param
from modules.mechanism_config.schema import MechanismConfigError
from modules.mechanism_config.ui_tunable import UI_PARAM_SPECS
from viz_backend.services.config_loader import load_proposal_config
from viz_backend.services.editor_agent import (
    approve_model,
    chat_turn,
    chat_turn_events,
    config_status,
    list_editor_state,
)
from viz_backend.services.probe_runner import tab_payload
from viz_backend.sse import sse_response

bp = Blueprint("viz_editor", __name__, url_prefix="/api/viz/editor")


def _section_for_ui_key(ui_key: str) -> str:
    return next((s.section for s in UI_PARAM_SPECS if s.key == ui_key), "health")


@bp.route("/status")
def editor_status():
    return jsonify(config_status())


@bp.route("/state")
def editor_state():
    return jsonify(list_editor_state())


@bp.route("/params")
def editor_params():
    proposal_id = request.args.get("proposal_id")
    try:
        cfg = load_mechanism_config()
        if proposal_id:
            cfg = load_proposal_config(proposal_id)
        values = {spec["key"]: read_ui_param(cfg, spec["key"]) for spec in list_ui_param_specs()}
        return jsonify({"params": list_ui_param_specs(), "values": values, "proposal_id": proposal_id})
    except MechanismConfigError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/propose", methods=["POST"])
def editor_propose():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "viz_tune").strip()
    note = (body.get("note") or "可视化调参").strip()
    try:
        pid = AIEditAPI().propose(name=name, note=note, created_by="viz_ui")
        return jsonify({"proposal_id": pid})
    except MechanismConfigError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/tune", methods=["POST"])
def editor_tune():
    body = request.get_json(silent=True) or {}
    ui_key = (body.get("ui_key") or "").strip()
    proposal_id = (body.get("proposal_id") or "").strip()
    if not ui_key or not proposal_id or body.get("value") is None:
        return jsonify({"error": "need proposal_id, ui_key, value"}), 400
    try:
        cfg = load_proposal_config(proposal_id)
        before = read_ui_param(cfg, ui_key)
        updated = write_ui_param(cfg, ui_key, float(body["value"]))
        AIEditAPI().edit_config(proposal_id, config=updated)
        after = read_ui_param(updated, ui_key)
        section = _section_for_ui_key(ui_key)
        return jsonify(
            {
                "ok": True,
                "ui_key": ui_key,
                "before": before,
                "after": after,
                "section": section,
                "tab": tab_payload(section, updated),
            }
        )
    except MechanismConfigError as e:
        return jsonify({"error": str(e)}), 400
    except (StopIteration, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/chat", methods=["POST"])
def editor_chat():
    body = request.get_json(silent=True) or {}
    text = (body.get("message") or "").strip()
    if not text:
        return jsonify({"error": "empty message", "reply": "请输入消息。"}), 400
    try:
        return jsonify(chat_turn(text, session_id=body.get("session_id")))
    except requests.RequestException as e:
        return jsonify(
            {
                "error": True,
                "reply": f"编辑模型请求失败: {e}",
                "traces": [],
            }
        ), 502


@bp.route("/chat/stream", methods=["POST"])
def editor_chat_stream():
    body = request.get_json(silent=True) or {}
    text = (body.get("message") or "").strip()
    if not text:
        return jsonify({"error": "empty message", "reply": "请输入消息。"}), 400
    return sse_response(chat_turn_events(text, session_id=body.get("session_id")))


@bp.route("/approve", methods=["POST"])
def editor_approve():
    body = request.get_json(silent=True) or {}
    model_id = (body.get("model_id") or "").strip()
    if not model_id:
        return jsonify({"error": "missing model_id"}), 400
    try:
        return jsonify(approve_model(model_id, config_only=bool(body.get("config_only"))))
    except MechanismConfigError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/rollback", methods=["POST"])
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
