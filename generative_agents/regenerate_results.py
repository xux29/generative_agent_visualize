#!/usr/bin/env python3
"""从 checkpoint 数据重新生成 complete_results.json 并提取 CSV。

用法：
    python regenerate_results.py --run init90_medium_20260324_120916_linear --scenario diabetes
"""

import os
import sys
import json
import csv
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Regenerator:
    """从 day_XX.json checkpoint 重新生成 complete_results.json。"""

    def __init__(self, run_path, scenario):
        self.run_path = Path(run_path)
        self.scenario = scenario
        self.day_files = sorted(
            [f for f in self.run_path.iterdir() if f.name.startswith("day_") and f.name.endswith(".json")],
            key=lambda x: int(x.stem.split("_")[1])
        )

    def load_day_logs(self):
        """加载所有 day_XX.json checkpoint 文件。"""
        daily_logs = []
        for f in self.day_files:
            with open(f, 'r', encoding='utf-8') as fh:
                daily_logs.append(json.load(fh))
        return daily_logs

    def regenerate_complete_results(self):
        """重新生成 complete_results.json，包含 agents 字段。"""
        daily_logs = self.load_day_logs()
        if not daily_logs:
            print("No day files found")
            return None

        # 尝试从 simulation_state.json 获取元数据
        state_file = self.run_path / "simulation_state.json"
        metadata = {
            "scenario_name": self.scenario,
            "scenario_display_name": self.scenario,
            "target_agent": "克劳斯" if "diabetes" in self.scenario else "亚瑟",
            "manager_agent": "伊莎贝拉",
            "total_days": len(daily_logs),
            "export_time": datetime.now().isoformat()
        }
        profile_config = {
            "target_profile": {},
            "manager_profile": {}
        }

        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                metadata["scenario_name"] = state.get("scenario_name", self.scenario)
                metadata["total_days"] = state.get("total_days_target", len(daily_logs))
                if "profile_config" in state:
                    profile_config = state["profile_config"]

        complete_results = {
            "metadata": metadata,
            "profile_config": profile_config,
            "daily_data": [],
            "summary": {
                "total_days_completed": len(daily_logs),
                "min_health_score": float('inf'),
                "max_health_score": float('-inf'),
                "min_emotion_score": float('inf'),
                "max_emotion_score": float('-inf'),
                "min_satisfaction_score": float('inf'),
                "max_satisfaction_score": float('-inf'),
                "average_health_score": 0,
                "average_emotion_score": 0,
                "average_satisfaction_score": 0,
                "total_interventions": 0,
                "intervention_by_level": {"0": 0, "1": 0, "2": 0, "3": 0},
                "compliance_rate": 0,
                "violation_count": 0,
            },
            "phase_analysis": {
                "honeymoon": {"days": [], "interventions": 0, "avg_health": None, "avg_emotion": None, "day_range": None, "total_days": 0},
                "adjustment": {"days": [], "interventions": 0, "avg_health": None, "avg_emotion": None, "day_range": None, "total_days": 0},
                "fatigue": {"days": [], "interventions": 0, "avg_health": None, "avg_emotion": None, "day_range": None, "total_days": 0},
                "stable": {"days": [], "interventions": 0, "avg_health": None, "avg_emotion": None, "day_range": None, "total_days": 0},
                "relapse": {"days": [], "interventions": 0, "avg_health": None, "avg_emotion": None, "day_range": None, "total_days": 0},
            },
            "trend_data": {
                "days": [],
                "health_scores": [],
                "emotion_scores": [],
                "satisfaction_scores": [],
                "intervention_levels": [],
            },
        }

        total_health = 0
        total_emotion = 0
        total_interventions = 0
        violations = 0

        for day_log in daily_logs:
            day_num = day_log.get("day", 0)
            health_score = day_log.get("health_score", 0)
            emotion_score = day_log.get(
                "satisfaction_score",
                day_log.get("emotion_score", 0),
            )
            satisfaction_breakdown = day_log.get(
                "satisfaction_breakdown",
                day_log.get("emotion_breakdown", {}),
            )
            events = day_log.get("events", [])
            interventions = day_log.get("interventions", [])
            dynamic_phase = day_log.get("dynamic_phase", "honeymoon")

            # 构建 daily_entry，关键：包含 agents 字段
            daily_entry = {
                "day": day_num,
                "date": day_log.get("date", ""),
                "health_score": health_score,
                "emotion_score": emotion_score,
                "satisfaction_score": emotion_score,
                "emotion_breakdown": satisfaction_breakdown,
                "satisfaction_breakdown": satisfaction_breakdown,
                "events": events,
                "interventions": interventions,
                "reflection": day_log.get("reflection", {}),
                "target_behaviors": day_log.get("target_behaviors", []),
                "dynamic_phase": dynamic_phase,
                "agents": day_log.get("agents", {}),  # 关键：真实埋点数据
                "agent_positions": day_log.get("agent_positions", []),
                "manager_positions": day_log.get("manager_positions", []),
                "turnaround_summary": day_log.get("turnaround_summary", {}),
            }
            complete_results["daily_data"].append(daily_entry)

            # 统计
            complete_results["summary"]["min_health_score"] = min(
                complete_results["summary"]["min_health_score"], health_score)
            complete_results["summary"]["max_health_score"] = max(
                complete_results["summary"]["max_health_score"], health_score)
            complete_results["summary"]["min_emotion_score"] = min(
                complete_results["summary"]["min_emotion_score"], emotion_score)
            complete_results["summary"]["max_emotion_score"] = max(
                complete_results["summary"]["max_emotion_score"], emotion_score)
            complete_results["summary"]["min_satisfaction_score"] = min(
                complete_results["summary"]["min_satisfaction_score"], emotion_score)
            complete_results["summary"]["max_satisfaction_score"] = max(
                complete_results["summary"]["max_satisfaction_score"], emotion_score)

            total_health += health_score
            total_emotion += emotion_score

            # 干预统计
            for inv in interventions:
                level = str(inv.get("level", 0))
                complete_results["summary"]["intervention_by_level"][level] += 1
                total_interventions += 1
                if inv.get("level", 0) >= 2:
                    violations += 1

            # 趋势
            complete_results["trend_data"]["days"].append(day_num)
            complete_results["trend_data"]["health_scores"].append(health_score)
            complete_results["trend_data"]["emotion_scores"].append(emotion_score)
            complete_results["trend_data"]["satisfaction_scores"].append(emotion_score)
            max_level = max([i.get("level", 0) for i in interventions]) if interventions else 0
            complete_results["trend_data"]["intervention_levels"].append(max_level)

            # 阶段
            if dynamic_phase in complete_results["phase_analysis"]:
                complete_results["phase_analysis"][dynamic_phase]["days"].append(
                    (health_score, emotion_score, day_num))
                complete_results["phase_analysis"][dynamic_phase]["interventions"] += len(interventions)

        # 汇总
        n = len(daily_logs)
        if n > 0:
            complete_results["summary"]["average_health_score"] = total_health / n
            complete_results["summary"]["average_emotion_score"] = total_emotion / n
            complete_results["summary"]["average_satisfaction_score"] = total_emotion / n
            complete_results["summary"]["total_interventions"] = total_interventions
            complete_results["summary"]["violation_count"] = violations
            complete_results["summary"]["compliance_rate"] = (n - violations) / n

        # 阶段平均
        for phase_name in complete_results["phase_analysis"]:
            phase_data = complete_results["phase_analysis"][phase_name]["days"]
            if phase_data:
                hs = [d[0] for d in phase_data]
                es = [d[1] for d in phase_data]
                ds = [d[2] for d in phase_data]
                complete_results["phase_analysis"][phase_name]["avg_health"] = sum(hs) / len(hs)
                complete_results["phase_analysis"][phase_name]["avg_emotion"] = sum(es) / len(es)
                complete_results["phase_analysis"][phase_name]["day_range"] = f"{min(ds)}-{max(ds)}"
                complete_results["phase_analysis"][phase_name]["total_days"] = len(ds)

        # 保存
        output_file = self.run_path / "complete_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(complete_results, f, ensure_ascii=False, indent=2)
        print(f"  [OK] Regenerated: {output_file}")
        return complete_results


def extract_csv(complete_results, output_dir="results/csv"):
    """用 HealthAnalyzer 提取 CSV。"""
    from analyze_health import HealthAnalyzer
    analyzer = HealthAnalyzer(csv_dir=output_dir)

    # 从 metadata 推断 scenario 和 run
    metadata = complete_results.get("metadata", {})
    scenario = metadata.get("scenario_name", "unknown")
    run_name = Path(complete_results.get("_run_path", "unknown")).name
    scoring_mode = metadata.get("scoring_mode")

    metrics = analyzer.extract_metrics(complete_results)
    if not metrics:
        print("  [FAIL] No metrics extracted")
        return None

    csv_path = analyzer.export_to_csv(scenario, run_name, metrics, scoring_mode)
    return csv_path


def main():
    parser = argparse.ArgumentParser(description='Regenerate complete_results.json from checkpoints and extract CSV')
    parser.add_argument('--run', type=str, required=True,
                        help='Run directory name, e.g. init90_medium_20260324_120916_linear')
    parser.add_argument('--scenario', type=str, default='diabetes',
                        help='Scenario name (default: diabetes)')
    parser.add_argument('--results-dir', type=str, default='results/health',
                        help='Parent results directory')
    parser.add_argument('--output-dir', type=str, default='results/csv',
                        help='CSV output directory')
    args = parser.parse_args()

    run_path = Path(args.results_dir) / args.scenario / args.run
    if not run_path.exists():
        print(f"Run path not found: {run_path}")
        return

    print(f"Regenerating from: {run_path}")
    print("=" * 60)

    # Step 1: 重新生成 complete_results.json
    print("\n[1/2] Regenerating complete_results.json ...")
    regenerator = Regenerator(run_path, args.scenario)
    results = regenerator.regenerate_complete_results()

    if not results:
        return

    # Step 2: 提取 CSV
    print("\n[2/2] Extracting CSV ...")
    results["_run_path"] = str(run_path)
    csv_path = extract_csv(results, args.output_dir)

    print("\n" + "=" * 60)
    if csv_path:
        print(f"Done! CSV: {csv_path}")
    else:
        print("Done! (CSV extraction failed)")


if __name__ == "__main__":
    main()
