"""HTTP routes: health simulation scenario list and charts."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from viz_backend.services.scenarios import (
    list_scenario_names,
    list_scenario_summaries,
    load_simulation_data,
)

bp = Blueprint("viz_scenarios", __name__)


@bp.route("/api/scenarios")
def api_scenarios():
    return jsonify({"scenarios": list_scenario_names()})


@bp.route("/api/scenario/<scenario_name>")
def api_scenario(scenario_name: str):
    data = load_simulation_data(scenario_name)
    if data:
        return jsonify(data)
    return jsonify({"error": "Scenario not found"}), 404


@bp.route("/api/scenario/<scenario_name>/day/<int:day>")
def api_day(scenario_name: str, day: int):
    data = load_simulation_data(scenario_name)
    if not data:
        return jsonify({"error": "Scenario not found"}), 404
    for log in data["daily_logs"]:
        if log.get("day") == day:
            return jsonify(log)
    return jsonify({"error": f"Day {day} not found"}), 404


@bp.route("/api/scenario/<scenario_name>/chart/health")
def api_health_chart(scenario_name: str):
    data = load_simulation_data(scenario_name)
    if not data or not data.get("report"):
        return jsonify({"error": "Data not available"}), 404
    report = data["report"]
    return jsonify(
        {
            "labels": list(range(1, len(report["daily_health_scores"]) + 1)),
            "datasets": [
                {
                    "label": "健康分",
                    "data": report["daily_health_scores"],
                    "borderColor": "rgb(75, 192, 192)",
                    "tension": 0.1,
                }
            ],
        }
    )


@bp.route("/api/scenario/<scenario_name>/chart/interventions")
def api_interventions_chart(scenario_name: str):
    data = load_simulation_data(scenario_name)
    if not data or not data.get("report"):
        return jsonify({"error": "Data not available"}), 404
    summary = data["report"]["intervention_summary"]
    return jsonify(
        {
            "labels": ["观察 (L0)", "劝说 (L1)", "移除 (L2)", "锁定 (L3)"],
            "datasets": [
                {
                    "label": "干预次数",
                    "data": [
                        summary["level_0"],
                        summary["level_1"],
                        summary["level_2"],
                        summary["level_3"],
                    ],
                    "backgroundColor": [
                        "rgba(75, 192, 192, 0.5)",
                        "rgba(255, 206, 86, 0.5)",
                        "rgba(255, 159, 64, 0.5)",
                        "rgba(255, 99, 132, 0.5)",
                    ],
                }
            ],
        }
    )


@bp.route("/scenario/<scenario_name>")
def scenario_detail(scenario_name: str):
    data = load_simulation_data(scenario_name)
    if not data:
        return "Scenario not found", 404
    return render_template("health_scenario.html", data=data)


@bp.route("/scenario/<scenario_name>/timeline")
def scenario_timeline(scenario_name: str):
    data = load_simulation_data(scenario_name)
    if not data:
        return "Scenario not found", 404
    return render_template("health_timeline.html", data=data)
