"""HTTP routes: mechanism tabs & probes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from modules.health_mechanisms.ai_edit import AIEditAPI
from modules.mechanism_config import list_ui_param_specs, read_ui_param, write_ui_param
from modules.mechanism_config.schema import MechanismConfigError
from modules.mechanism_config.ui_tunable import UI_PARAM_SPECS

from viz_backend.config import TAB_SECTIONS
from viz_backend.services.config_loader import resolve_config
from viz_backend.services.probe_runner import probe_ui_param_delta, tab_payload

bp = Blueprint("viz_mechanism", __name__, url_prefix="/api/viz/mechanism")


@bp.route("/tabs")
def list_tabs():
    return jsonify({"tabs": TAB_SECTIONS})


@bp.route("/params")
def list_params():
    proposal_id = request.args.get("proposal_id")
    cfg = resolve_config(proposal_id or None)
    values = {spec["key"]: read_ui_param(cfg, spec["key"]) for spec in list_ui_param_specs()}
    return jsonify({"params": list_ui_param_specs(), "values": values, "proposal_id": proposal_id})


@bp.route("/tab/<section>")
def get_tab(section: str):
    proposal_id = request.args.get("proposal_id")
    try:
        cfg = resolve_config(proposal_id or None)
        return jsonify(tab_payload(section, cfg))
    except (MechanismConfigError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/probe", methods=["POST"])
def probe_param():
    body = request.get_json(silent=True) or {}
    ui_key = (body.get("ui_key") or "").strip()
    proposal_id = (body.get("proposal_id") or "").strip()
    if not ui_key or body.get("value") is None:
        return jsonify({"error": "need ui_key and value"}), 400
    try:
        cfg = resolve_config(proposal_id or None)
        return jsonify(probe_ui_param_delta(cfg, ui_key, float(body["value"])))
    except MechanismConfigError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/tune", methods=["POST"])
def tune_param():
    body = request.get_json(silent=True) or {}
    ui_key = (body.get("ui_key") or "").strip()
    proposal_id = (body.get("proposal_id") or "").strip()
    if not ui_key or not proposal_id or body.get("value") is None:
        return jsonify({"error": "need proposal_id, ui_key, value"}), 400
    try:
        cfg = resolve_config(proposal_id)
        before = read_ui_param(cfg, ui_key)
        updated = write_ui_param(cfg, ui_key, float(body["value"]))
        AIEditAPI().edit_config(proposal_id, config=updated)
        after = read_ui_param(updated, ui_key)
        section = next((s.section for s in UI_PARAM_SPECS if s.key == ui_key), "health")
        tab = tab_payload(section, updated)
        return jsonify(
            {
                "ok": True,
                "ui_key": ui_key,
                "before": before,
                "after": after,
                "tab": tab,
            }
        )
    except MechanismConfigError as e:
        return jsonify({"error": str(e)}), 400

