#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 day_*.json 文件重建 complete_results.json 和 CSV
解决并行模式下 simulation_state.json 状态保存不完整的问题
"""

import json
import sys
from pathlib import Path
from datetime import datetime

def rebuild_results(run_dir: Path):
    """从 day_*.json 文件重建结果"""
    day_files = sorted(run_dir.glob("day_*.json"), key=lambda x: int(x.stem.split("_")[1]))
    if not day_files:
        print(f"No day files found in {run_dir}")
        return

    print(f"Found {len(day_files)} day files")
    daily_logs = []
    for day_file in day_files:
        try:
            with open(day_file, 'r', encoding='utf-8') as f:
                daily_logs.append(json.load(f))
        except Exception as e:
            print(f"Error reading {day_file}: {e}")

    print(f"Loaded {len(daily_logs)} daily logs")

    existing_results_file = run_dir / "complete_results.json"
    if existing_results_file.exists():
        try:
            with open(existing_results_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                metadata = existing.get("metadata", {})
                profile_config = existing.get("profile_config", {})
        except:
            metadata, profile_config = {}, {}
    else:
        metadata, profile_config = {}, {}

    complete_results = {
        "metadata": {
            "scenario_name": metadata.get("scenario_name", "diabetes"),
            "scenario_display_name": metadata.get("scenario_display_name", "糖尿病场景（老人与护工）"),
            "target_agent": metadata.get("target_agent", "克劳斯"),
            "manager_agent": metadata.get("manager_agent", "玛丽亚"),
            "total_days": len(daily_logs),
            "map_folder": metadata.get("map_folder", "village"),
            "export_time": datetime.now().isoformat(),
            "scoring_mode": metadata.get("scoring_mode", "nonlinear"),
        },
        "profile_config": profile_config,
        "daily_data": [],
        "summary": {
            "total_days_completed": len(daily_logs),
            "average_health_score": 0, "average_emotion_score": 0, "average_satisfaction_score": 0,
            "min_health_score": 100, "max_health_score": 0,
            "min_emotion_score": 10, "max_emotion_score": 0,
            "min_satisfaction_score": 10, "max_satisfaction_score": 0,
            "total_interventions": 0,
            "intervention_by_level": {"0": 0, "1": 0, "2": 0, "3": 0},
            "compliance_rate": 0, "violation_count": 0,
        },
        "phase_analysis": {
            "honeymoon": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "蜜月期"},
            "adjustment": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "调整期"},
            "fatigue": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "倦怠期"},
            "stable": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "稳定期"},
            "relapse": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "复发期"},
        },
        "trend_data": {"days": [], "health_scores": [], "emotion_scores": [], "satisfaction_scores": [], "intervention_levels": []},
    }

    total_score, total_emotion_score, total_interventions, violations = 0, 0, 0, 0

    for i, day_log in enumerate(daily_logs):
        day_num = day_log.get("day", i + 1)
        date = day_log.get("date", "")
        health_score = day_log.get("health_score", day_log.get("new_score", 75))
        # 新字段优先，回退旧字段
        emotion_score = day_log.get(
            "satisfaction_score",
            day_log.get("emotion_score", 5.0),
        )
        day_interventions = day_log.get("interventions", [])
        intervention_count = len(day_interventions)
        max_level = max([iv.get("level", 0) for iv in day_interventions], default=0)
        day_violations = day_log.get("violations", [])
        violation_count = len(day_violations) if isinstance(day_violations, list) else (1 if day_violations else 0)
        dynamic_phase = day_log.get("dynamic_phase", "adjustment")

        # 提取违规相关字段
        events = day_log.get("events", [])
        turnarounds = [e for e in events if e.get("type") == "turnaround"]
        turnaround_count = len(turnarounds)
        had_violation = day_log.get("had_violation", False)
        unblocked_violation_count = day_log.get("unblocked_violation_count", 0)

        # 提取agents数据
        agents_data = day_log.get("agents", {})
        target_agent_data = {}
        if isinstance(agents_data, dict) and agents_data:
            for k, v in agents_data.items():
                if k != 'manager' and isinstance(v, dict):
                    target_agent_data = v
                    break

        complete_results["daily_data"].append({
            "day": day_num, "date": date, "health_score": health_score,
            "emotion_score": emotion_score, "satisfaction_score": emotion_score,
            "interventions": day_interventions,  # 完整列表
            "max_intervention_level": max_level, "violations": violation_count,
            "dynamic_phase": dynamic_phase, "summary": day_log.get("summary", ""),
            # 新增违规相关字段
            "had_violation": had_violation,
            "unblocked_violation_count": unblocked_violation_count,
            "turnaround_count": turnaround_count,
            "events": events,
            "agents": agents_data,
        })

        total_score += health_score
        total_emotion_score += emotion_score
        total_interventions += intervention_count
        violations += violation_count

        if health_score < complete_results["summary"]["min_health_score"]:
            complete_results["summary"]["min_health_score"] = health_score
        if health_score > complete_results["summary"]["max_health_score"]:
            complete_results["summary"]["max_health_score"] = health_score
        if emotion_score < complete_results["summary"]["min_emotion_score"]:
            complete_results["summary"]["min_emotion_score"] = emotion_score
        if emotion_score > complete_results["summary"]["max_emotion_score"]:
            complete_results["summary"]["max_emotion_score"] = emotion_score
        if emotion_score < complete_results["summary"]["min_satisfaction_score"]:
            complete_results["summary"]["min_satisfaction_score"] = emotion_score
        if emotion_score > complete_results["summary"]["max_satisfaction_score"]:
            complete_results["summary"]["max_satisfaction_score"] = emotion_score

        complete_results["summary"]["intervention_by_level"][str(max_level)] += 1
        complete_results["trend_data"]["days"].append(day_num)
        complete_results["trend_data"]["health_scores"].append(health_score)
        complete_results["trend_data"]["emotion_scores"].append(emotion_score)
        complete_results["trend_data"]["satisfaction_scores"].append(emotion_score)
        complete_results["trend_data"]["intervention_levels"].append(max_level)

        if dynamic_phase in complete_results["phase_analysis"]:
            complete_results["phase_analysis"][dynamic_phase]["days"].append((health_score, emotion_score, day_num))
            complete_results["phase_analysis"][dynamic_phase]["interventions"] += intervention_count

    if daily_logs:
        complete_results["summary"]["average_health_score"] = total_score / len(daily_logs)
        complete_results["summary"]["average_emotion_score"] = total_emotion_score / len(daily_logs)
        complete_results["summary"]["average_satisfaction_score"] = total_emotion_score / len(daily_logs)
        complete_results["summary"]["total_interventions"] = total_interventions
        complete_results["summary"]["violation_count"] = violations
        complete_results["summary"]["compliance_rate"] = (len(daily_logs) - violations) / len(daily_logs)

    for phase_name, phase_data in complete_results["phase_analysis"].items():
        if phase_data["days"]:
            phase_data["avg_health"] = sum(d[0] for d in phase_data["days"]) / len(phase_data["days"])
            phase_data["avg_emotion"] = sum(d[1] for d in phase_data["days"]) / len(phase_data["days"])
            day_numbers = [d[2] for d in phase_data["days"]]
            phase_data["day_range"] = f"{min(day_numbers)}-{max(day_numbers)}"
            phase_data["total_days"] = len(day_numbers)

    with open(existing_results_file, 'w', encoding='utf-8') as f:
        json.dump(complete_results, f, ensure_ascii=False, indent=2)
    print(f"Saved complete_results.json")

    try:
        import pandas as pd
        csv_data = [{
            "Day": e["day"], "Date": e["date"], "Health Score": e["health_score"],
            "Emotion Score": e["emotion_score"], "Interventions": e["interventions"],
            "Max Level": e["max_intervention_level"], "Violations": e["violations"], "Phase": e["dynamic_phase"],
        } for e in complete_results["daily_data"]]
        df = pd.DataFrame(csv_data)
        df.to_csv(run_dir / "results_summary.csv", index=False, encoding='utf-8-sig')
        print(f"Saved results_summary.csv")
    except ImportError:
        print("pandas not available, skipping CSV generation")

    state_file = run_dir / "simulation_state.json"
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except:
            state = {}
        state["current_day"] = len(daily_logs)
        state["daily_logs"] = daily_logs
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"Updated simulation_state.json")

    return complete_results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_dir = Path(sys.argv[1])
    else:
        run_dir = Path(r"E:\data\pythoncode\GenerativeAgentsCN\generative_agents\results\health\diabetes\init60_low_20260507_204320")
    rebuild_results(run_dir)
