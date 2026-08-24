"""Health simulation result loading for scenario pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from viz_backend.config import RESULTS_HEALTH


def load_simulation_data(
    scenario_name: str,
    result_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    scenario_path = (result_path or RESULTS_HEALTH) / scenario_name
    if not scenario_path.exists():
        return None

    data: Dict[str, Any] = {
        "scenario": scenario_name,
        "daily_logs": [],
        "report": None,
    }

    for log_file in sorted(scenario_path.glob("day_*.json")):
        with open(log_file, "r", encoding="utf-8") as f:
            data["daily_logs"].append(json.load(f))

    report_file = scenario_path / "final_report.json"
    if report_file.is_file():
        with open(report_file, "r", encoding="utf-8") as f:
            data["report"] = json.load(f)

    return data


def list_scenario_summaries(result_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = result_path or RESULTS_HEALTH
    scenarios: List[Dict[str, Any]] = []
    if not root.exists():
        return scenarios

    for scenario_dir in sorted(root.iterdir()):
        if not scenario_dir.is_dir():
            continue
        report_file = scenario_dir / "final_report.json"
        if not report_file.is_file():
            continue
        with open(report_file, "r", encoding="utf-8") as f:
            report = json.load(f)
        scenarios.append(
            {
                "name": scenario_dir.name,
                "days": report.get("total_days", 0),
                "avg_score": report.get("average_health_score", 0),
            }
        )
    return scenarios


def list_scenario_names(result_path: Optional[Path] = None) -> List[str]:
    root = result_path or RESULTS_HEALTH
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())
