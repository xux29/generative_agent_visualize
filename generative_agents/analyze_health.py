#!/usr/bin/env python3
"""健康模拟统计分析器。

从健康模拟结果中提取并分析指标，包括：
- 健康分及其变化
- 情绪/心情与满意度分数
- 干预级别、类型与成功率
- 信任资本与信誉分
- 不良行为/违规次数与模式
- 策略阶段与阶段迁移
- 反思洞察
- 长期行为模式

用法：
    # 列出所有可用场景和运行
    python analyze_health.py --list

    # 分析某个场景的最新运行
    python analyze_health.py --scenario weight-loss

    # 分析指定运行
    python analyze_health.py --scenario weight-loss --run init75_medium_20260320_120241

    # 同时分析多个场景
    python analyze_health.py --scenario diabetes phone-addiction weight-loss

输出：
    CSV 文件：results/csv/health_analysis_{scenario}_{run}_{timestamp}.csv
    汇总报告：results/csv/health_analysis_{timestamp}_summary.csv
"""

import os
import sys
import json
import csv
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 将父目录加入路径，保证本地模块可正常导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class HealthAnalyzer:
    """分析健康模拟结果并提取统计指标。"""

    BAD_BEHAVIOR_KEYWORDS = (
        "吃夜宵", "偷吃", "甜食", "吃零食", "暴食", "高糖", "高脂", "夜间加餐",
        "玩手机", "刷视频", "打游戏", "熬夜", "喝酒", "snack", "eat", "phone", "game"
    )

    def __init__(self, results_dir="results/health", csv_dir="results/csv"):
        self.results_dir = Path(results_dir)
        self.csv_dir = Path(csv_dir)
        self.csv_dir.mkdir(parents=True, exist_ok=True)

    def list_available_scenarios(self):
        """列出所有可用的健康模拟场景与运行。"""
        if not self.results_dir.exists():
            print(f"Results directory not found: {self.results_dir}")
            return {}

        scenarios = {}
        for scenario_dir in self.results_dir.iterdir():
            if scenario_dir.is_dir() and not scenario_dir.name.startswith('_'):
                runs = []
                for run_dir in scenario_dir.iterdir():
                    if run_dir.is_dir() and (run_dir / "complete_results.json").exists():
                        runs.append({
                            "name": run_dir.name,
                            "path": str(run_dir),
                            "timestamp": run_dir.stat().st_mtime
                        })
                if runs:
                    scenarios[scenario_dir.name] = sorted(runs, key=lambda x: x['timestamp'], reverse=True)

        return scenarios

    def find_latest_run(self, scenario_name):
        """获取指定场景的最新一次运行目录。"""
        if not self.results_dir.exists():
            return None

        scenario_dir = self.results_dir / scenario_name
        if not scenario_dir.exists():
            return None

        runs = []
        for run_dir in scenario_dir.iterdir():
            if run_dir.is_dir() and (run_dir / "complete_results.json").exists():
                runs.append((run_dir, run_dir.stat().st_mtime))

        if runs:
            return max(runs, key=lambda x: x[1])[0]
        return None

    def load_results(self, run_path):
        """从运行目录加载完整结果数据。"""
        results_file = Path(run_path) / "complete_results.json"
        if not results_file.exists():
            print(f"Results file not found: {results_file}")
            return None

        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading results: {e}")
            return None

    def _build_weekly_day_maps(self, long_term_mechanism):
        """将周级别统计映射为逐日查找表。"""
        trust_by_day = {}
        habit_stage_by_day = {}
        week_by_day = {}

        weekly = (long_term_mechanism or {}).get("weekly_reflections", [])
        for row in weekly:
            day_range = row.get("day_range", [])
            if not isinstance(day_range, list) or len(day_range) != 2:
                continue

            start_day, end_day = day_range
            trust_val = row.get("trust_capital")
            stage_val = row.get("habit_stage")
            week_val = row.get("week")

            if start_day is None or end_day is None:
                continue

            for day in range(int(start_day), int(end_day) + 1):
                if trust_val is not None:
                    trust_by_day[day] = trust_val
                if stage_val is not None:
                    habit_stage_by_day[day] = stage_val
                if week_val is not None:
                    week_by_day[day] = week_val

        return trust_by_day, habit_stage_by_day, week_by_day

    def _is_bad_intention(self, content):
        """判断意图文本是否属于潜在不良行为。"""
        text = str(content or "").lower()
        return any(k.lower() in text for k in self.BAD_BEHAVIOR_KEYWORDS)

    def _get_time_period(self, time_str):
        """根据时间字符串获取时间段

        Args:
            time_str: 时间字符串，格式如 "21:00", "23:30"

        Returns:
            str: 时间段名称（凌晨/早上/上午/中午/下午/傍晚/晚上/深夜）
        """
        try:
            hour = int(time_str.split(":")[0])
        except (ValueError, IndexError):
            return "未知"

        if 2 <= hour < 6:
            return "凌晨"
        elif 6 <= hour < 9:
            return "早上"
        elif 9 <= hour < 12:
            return "上午"
        elif 12 <= hour < 14:
            return "中午"
        elif 14 <= hour < 18:
            return "下午"
        elif 18 <= hour < 20:
            return "傍晚"
        elif 20 <= hour < 23:
            return "晚上"
        else:  # 23 or 0, 1
            return "深夜"

    def _get_hour_from_time(self, time_str):
        """从时间字符串提取小时数

        Args:
            time_str: 时间字符串，格式如 "21:00"

        Returns:
            int: 小时数（0-23），失败返回 -1
        """
        try:
            return int(time_str.split(":")[0])
        except (ValueError, IndexError):
            return -1

    def _extract_location_stats(self, agent_positions, events):
        """从位置轨迹和事件中提取位置统计

        Args:
            agent_positions: agent_positions 列表
            events: events 列表

        Returns:
            dict: 位置统计信息
        """
        location_stats = {
            "primary_location": "unknown",
            "location_counts": {},
            "location_sequence": [],
            "violation_location": None,
            "violation_hour": -1,  # Use -1 instead of None to indicate no violation
        }

        # 从 agent_positions 统计位置
        if agent_positions:
            for pos in agent_positions:
                location = pos.get("location", "unknown")
                location_stats["location_counts"][location] = location_stats["location_counts"].get(location, 0) + 1
                location_stats["location_sequence"].append({
                    "time": pos.get("time", ""),
                    "location": location,
                    "status": pos.get("status", "")
                })

            # 找出最频繁的位置
            if location_stats["location_counts"]:
                location_stats["primary_location"] = max(
                    location_stats["location_counts"].items(),
                    key=lambda x: x[1]
                )[0]

        # 从 events 中提取违规位置和时间
        for event in events:
            if event.get("type") == "intention" and not event.get("blocked", False):
                # 检查是否违规意图
                if self._is_bad_intention(event.get("content", "")):
                    location_stats["violation_location"] = event.get("target_location", "unknown")
                    # Fix: handle None time value
                    time_val = event.get("time")
                    location_stats["violation_hour"] = self._get_hour_from_time(time_val if time_val else "")

        return location_stats

    def _extract_time_distribution(self, agent_positions):
        """提取时间分布统计

        Args:
            agent_positions: agent_positions 列表

        Returns:
            dict: 时间段分布统计
        """
        time_dist = {
            "morning": 0,    # 早上(6-9)
            "afternoon": 0,  # 下午(14-18)
            "evening": 0,    # 晚上(20-23)
            "night": 0,      # 深夜(23-2)
            "other": 0,
        }

        if not agent_positions:
            return time_dist

        for pos in agent_positions:
            time_str = pos.get("time", "")
            hour = self._get_hour_from_time(time_str)

            if 6 <= hour < 9:
                time_dist["morning"] += 1
            elif 14 <= hour < 18:
                time_dist["afternoon"] += 1
            elif 20 <= hour < 24 or hour == 0:
                time_dist["evening"] += 1
            elif 0 <= hour < 2 or 23 <= hour < 24:
                time_dist["night"] += 1
            else:
                time_dist["other"] += 1

        return time_dist

    def extract_metrics(self, results):
        """从结果数据中提取逐日指标。"""
        if not results or 'daily_data' not in results:
            return None

        metrics = []
        daily_data = results.get('daily_data', [])
        long_term_mechanism = results.get('long_term_mechanism', {})

        trust_by_day, habit_stage_by_day, week_by_day = self._build_weekly_day_maps(long_term_mechanism)
        trust_fallback = ((long_term_mechanism.get("trust_capital") or {}).get("current_capital"))
        habit_fallback = ((long_term_mechanism.get("habit_consolidation") or {}).get("stage", "unknown"))

        for day_data in daily_data:
            day = day_data.get('day')
            date = day_data.get('date', '')

            # 健康指标
            health_score = day_data.get('health_score', 0)

            # 健康分变化：优先可直接计算
            health_change = 0
            if day > 1 and len(metrics) > 0:
                health_change = health_score - metrics[-1].get('health_score', health_score)

            # 情绪/心情指标
            emotion_score = day_data.get('emotion_score', 0)
            emotion_breakdown = day_data.get('emotion_breakdown', {})

            # 兼容不同结果版本的满意度字段命名
            satisfaction = (
                emotion_breakdown.get('satisfaction_score')
                if emotion_breakdown.get('satisfaction_score') is not None
                else emotion_breakdown.get('final_score')
            )
            if satisfaction is None:
                satisfaction = emotion_score

            mood = emotion_breakdown.get('mood', 'normal')

            # 干预指标
            interventions = day_data.get('interventions', [])
            
            # 事件统计（后续违规统计会用到）
            events = day_data.get('events', [])
            event_count = len(events)
            turnaround_count = sum(1 for e in events if e.get('type') == 'turnaround')
            
            # 违规/不良行为指标
            # 优先从 agents 字段读取真实收集的数据（phone_duration_before_sleep, snacking_count 等）
            agents_data = day_data.get('agents', {})
            target_behaviors = day_data.get('target_behaviors', [])
            violation_count = 0
            misbehavior_count = 0
            snacking_count = 0
            phone_duration = 0

            if isinstance(agents_data, dict) and agents_data:
                # 从 agents 中提取真实埋点数据（agent名字可能是中文key）
                # 尝试找第一个非manager的agent数据
                for k, v in agents_data.items():
                    if k != 'manager' and isinstance(v, dict):
                        target_agent_data = v
                        break
                else:
                    target_agent_data = {}
                if target_agent_data:
                    violation_count = target_agent_data.get('violation_count', 0)
                    misbehavior_count = target_agent_data.get('misbehavior_count', 0)
                    snacking_count = target_agent_data.get('snacking_count', 0)
                    phone_duration = target_agent_data.get('phone_duration_before_sleep', 0)

            # 从 turnarounds 事件统计实际违规次数（折返=被阻止的违规尝试）
            turnarounds = [e for e in events if e.get('type') == 'turnaround']
            turnaround_count = len(turnarounds)
            # 使用 had_violation 和 unblocked_violation_count 字段
            had_violation = day_data.get('had_violation', False)
            unblocked_violation_count = day_data.get('unblocked_violation_count', 0)

            # 优先使用 had_violation 和 unblocked_violation_count（更准确的违规数据）
            # 如果 agents 字典有 violation_count 且 > 0，使用它；否则使用推算值
            if violation_count == 0:
                if had_violation:
                    violation_count = max(1, unblocked_violation_count)
                # 如果没有 had_violation 标记，用 turnarounds 推算（厨房相关的折返视为偷吃尝试）
                else:
                    kitchen_turnarounds = len([e for e in turnarounds if '厨房' in str(e.get('blocked_at', '')) or '厨房' in str(e.get('target_location', ''))])
                    violation_count = kitchen_turnarounds if kitchen_turnarounds > 0 else turnaround_count

            # 偷吃次数：从 turnarounds 中统计厨房相关事件
            if snacking_count == 0:
                kitchen_turnarounds = [e for e in turnarounds if '厨房' in str(e.get('blocked_at', '')) or '厨房' in str(e.get('target_location', ''))]
                snacking_count = len(kitchen_turnarounds) if kitchen_turnarounds else 0

            # 保持 misbehavior_count 与 violation_count 一致
            if misbehavior_count == 0:
                misbehavior_count = violation_count

            bad_intentions = [
                e for e in events
                if e.get('type') == 'intention' and self._is_bad_intention(e.get('content', ''))
            ]
            bad_behavior_sent_count = len(bad_intentions)
            blocked_bad_behavior_count = sum(1 for e in bad_intentions if e.get('blocked', False))
            unblocked_bad_behavior_count = bad_behavior_sent_count - blocked_bad_behavior_count
            
            # 干预统计补充
            intervention_count = len(interventions)
            intervention_levels = [inv.get('level', 0) for inv in interventions]
            max_intervention_level = max(intervention_levels) if intervention_levels else 0
            avg_intervention_level = sum(intervention_levels) / len(intervention_levels) if intervention_levels else 0
            successful_interventions = sum(1 for inv in interventions if inv.get('succeeded', True))
            intervention_success_rate = (successful_interventions / intervention_count * 100) if intervention_count > 0 else 0

            # 干预类型分布
            intervention_types = defaultdict(int)
            for inv in interventions:
                action = inv.get('action', 'unknown')
                intervention_types[action] += 1

            # 策略相关指标
            # 注意：dynamic_phase 可能是字符串（阶段名），也可能是字典
            dynamic_phase_val = day_data.get('dynamic_phase', 'unknown')
            strategy_phase = dynamic_phase_val if isinstance(dynamic_phase_val, str) else dynamic_phase_val.get('current_phase', 'unknown')
            
            # 以下字段在 daily_data 中可能缺失，先给默认值
            strategy_level = 0
            trust_capital = None
            reputation_score = None
            habit_stage = habit_stage_by_day.get(day, habit_fallback)
            
            # 备选：用干预级别推断策略级别
            intervention_levels = [inv.get('level', 0) for inv in interventions]
            strategy_level = max(intervention_levels) if intervention_levels else 0

            # 信任资本：优先日级字段，其次周映射，最后总览当前值
            if isinstance(dynamic_phase_val, dict):
                trust_capital = dynamic_phase_val.get('trust_capital')
                reputation_score = dynamic_phase_val.get('reputation_score')
                habit_stage = dynamic_phase_val.get('habit_internalization_stage', habit_stage)

            if trust_capital is None:
                trust_capital = trust_by_day.get(day, trust_fallback)
            if trust_capital is None:
                trust_capital = 0

            # 信誉分：若结果中无独立字段，按历史画图脚本逻辑映射为 trust_capital
            if reputation_score is None:
                reputation_score = trust_capital

            trust_level = max(0.0, min(1.0, float(trust_capital) / 100.0))

            # 参照公式文档新增派生指标
            health_score_10 = max(0.0, min(10.0, float(health_score) / 10.0))
            # 依从率：基于违规次数计算，无违规=1.0，有违规则递减
            if violation_count == 0:
                compliance_rate = 1.0
            else:
                # 每次违规降低10%依从率，最低0%
                compliance_rate = max(0.0, 1.0 - (violation_count * 0.1))
            intervention_success_rate = (successful_interventions / intervention_count * 100) if intervention_count > 0 else 0.0
            health_change_score = max(0.0, min(4.0, (float(health_change) + 5.0) * 0.4))
            compliance_score = max(0.0, min(3.0, compliance_rate * 3.0))
            if intervention_count > 0:
                improvement = max(0.0, float(health_change))
                efficiency_score = max(0.0, min(3.0, ((improvement / intervention_count) + 1.0) * 0.75))
            else:
                efficiency_score = 0.0
            effectiveness_score = max(0.0, min(10.0, health_change_score + compliance_score + efficiency_score))
            composite_score = max(
                0.0,
                min(10.0, 0.5 * health_score_10 + 0.3 * float(satisfaction) + 0.2 * effectiveness_score)
            )

            # 反思/洞察
            reflection = day_data.get('reflection', {})
            key_insights = reflection.get('key_insights', [])
            insight_text = '; '.join(key_insights[:3]) if key_insights else ''

            # 位置和时间统计
            agent_positions = day_data.get('agent_positions', [])
            manager_positions = day_data.get('manager_positions', [])
            location_stats = self._extract_location_stats(agent_positions, events)
            time_distribution = self._extract_time_distribution(agent_positions)

            # 从 events 中提取第一时间段
            first_time_period = "未知"
            first_hour = -1
            if events:
                first_event_time = events[0].get('time', '')
                if first_event_time:
                    first_hour = self._get_hour_from_time(first_event_time)
                    first_time_period = self._get_time_period(first_event_time)

            # 违规时间（如果有）
            violation_hour = location_stats.get('violation_hour', -1)
            violation_time_period = self._get_time_period(f"{violation_hour}:00") if violation_hour >= 0 else "无违规"

            metric = {
                'day': day,
                'date': date,
                'health_score': round(health_score, 2),
                'health_change': round(health_change, 2),
                'emotion_score': round(emotion_score, 2),
                'satisfaction': round(satisfaction, 2),
                'mood': mood,
                'health_score_10': round(health_score_10, 2),
                'intervention_count': intervention_count,
                'max_intervention_level': max_intervention_level,
                'avg_intervention_level': round(avg_intervention_level, 2),
                'successful_interventions': successful_interventions,
                'intervention_success_rate': round(intervention_success_rate, 1),
                'compliance_rate': round(compliance_rate, 4),
                'intervention_types': ', '.join([f"{k}:{v}" for k, v in sorted(intervention_types.items())]),
                'violation_count': violation_count,
                'misbehavior_count': misbehavior_count,
                'snacking_count': snacking_count,
                'phone_duration_minutes': phone_duration,
                'bad_behavior_sent_count': bad_behavior_sent_count,
                'blocked_bad_behavior_count': blocked_bad_behavior_count,
                'unblocked_bad_behavior_count': unblocked_bad_behavior_count,
                'strategy_level': strategy_level,
                'strategy_phase': strategy_phase,
                'trust_capital': round(trust_capital, 2),
                'trust_level': round(trust_level, 4),
                'reputation_score': round(reputation_score, 2),
                'habit_stage': habit_stage,
                'week_index': week_by_day.get(day),
                'event_count': event_count,
                'turnaround_count': turnaround_count,
                'health_change_score': round(health_change_score, 2),
                'compliance_score': round(compliance_score, 2),
                'efficiency_score': round(efficiency_score, 2),
                'effectiveness_score': round(effectiveness_score, 2),
                'composite_score': round(composite_score, 2),
                'key_insights': insight_text,
                # 位置和时间信息
                'primary_location': location_stats.get('primary_location', 'unknown'),
                'violation_location': location_stats.get('violation_location', '无违规'),
                'first_hour': first_hour,
                'first_time_period': first_time_period,
                'violation_hour': violation_hour if violation_hour >= 0 else -1,
                'violation_time_period': violation_time_period,
                'location_distribution': '; '.join([f"{k}:{v}" for k, v in location_stats.get('location_counts', {}).items()]),
                'time_morning': time_distribution.get('morning', 0),
                'time_afternoon': time_distribution.get('afternoon', 0),
                'time_evening': time_distribution.get('evening', 0),
                'time_night': time_distribution.get('night', 0),
            }

            metrics.append(metric)

        return metrics

    def export_to_csv(self, scenario, run_name, metrics, scoring_mode=None):
        """将逐日指标导出为 CSV 文件。

        Args:
            scenario: 场景名称
            run_name: 运行名称
            metrics: 指标数据
            scoring_mode: 评分模式（linear/nonlinear），如果为None则不包含在文件名中
        """
        if not metrics:
            print(f"No metrics to export for {scenario}/{run_name}")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 根据是否有scoring_mode生成文件名
        if scoring_mode:
            csv_filename = f"health_analysis_{scenario}_{run_name}_{scoring_mode}_{timestamp}.csv"
        else:
            csv_filename = f"health_analysis_{scenario}_{run_name}_{timestamp}.csv"
        csv_path = self.csv_dir / csv_filename

        # 输出字段清单
        fieldnames = [
            'day', 'date',
            'health_score', 'health_change', 'health_score_10',
            'emotion_score', 'satisfaction', 'mood',
            'intervention_count', 'max_intervention_level', 'avg_intervention_level',
            'successful_interventions', 'intervention_success_rate', 'compliance_rate',
            'intervention_types',
            'violation_count', 'misbehavior_count', 'snacking_count', 'phone_duration_minutes',
            'bad_behavior_sent_count', 'blocked_bad_behavior_count', 'unblocked_bad_behavior_count',
            'strategy_level', 'strategy_phase', 'trust_capital', 'trust_level', 'reputation_score', 'habit_stage', 'week_index',
            'event_count', 'turnaround_count',
            'health_change_score', 'compliance_score', 'efficiency_score', 'effectiveness_score', 'composite_score',
            'key_insights',
            # 位置和时间字段
            'primary_location', 'violation_location',
            'first_hour', 'first_time_period', 'violation_hour', 'violation_time_period',
            'location_distribution',
            'time_morning', 'time_afternoon', 'time_evening', 'time_night',
        ]

        try:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for metric in metrics:
                    writer.writerow(metric)

            print(f"  [OK] Exported: {csv_filename}")
            return str(csv_path)

        except Exception as e:
            print(f"  [FAIL] Error exporting CSV: {e}")
            return None

    def generate_summary(self, all_metrics_by_scenario):
        """生成跨场景的汇总统计 CSV。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_filename = f"health_analysis_summary_{timestamp}.csv"
        summary_path = self.csv_dir / summary_filename

        summary_rows = []

        for scenario, metrics_by_run in all_metrics_by_scenario.items():
            for run_name, metrics in metrics_by_run.items():
                if not metrics:
                    continue

                # 计算该运行的汇总指标
                avg_health = sum(m['health_score'] for m in metrics) / len(metrics)
                final_health = metrics[-1]['health_score']
                total_interventions = sum(m['intervention_count'] for m in metrics)
                avg_intervention_level = sum(m['avg_intervention_level'] for m in metrics) / len(metrics)
                total_violations = sum(m['violation_count'] for m in metrics)
                total_turnarounds = sum(m['turnaround_count'] for m in metrics)
                avg_satisfaction = sum(m['satisfaction'] for m in metrics) / len(metrics)

                summary_rows.append({
                    'scenario': scenario,
                    'run': run_name,
                    'days': len(metrics),
                    'initial_health': metrics[0]['health_score'],
                    'final_health': final_health,
                    'avg_health': round(avg_health, 2),
                    'health_trend': 'up' if final_health > metrics[0]['health_score'] else 'down' if final_health < metrics[0]['health_score'] else 'stable',
                    'total_interventions': total_interventions,
                    'avg_intervention_level': round(avg_intervention_level, 2),
                    'total_violations': total_violations,
                    'total_turnarounds': total_turnarounds,
                    'avg_satisfaction': round(avg_satisfaction, 2),
                })

        # 写入汇总文件
        if summary_rows:
            summary_fieldnames = [
                'scenario', 'run', 'days',
                'initial_health', 'final_health', 'avg_health', 'health_trend',
                'total_interventions', 'avg_intervention_level',
                'total_violations', 'total_turnarounds',
                'avg_satisfaction',
            ]

            try:
                with open(summary_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=summary_fieldnames)
                    writer.writeheader()
                    for row in summary_rows:
                        writer.writerow(row)

                print(f"\n[OK] Summary exported: {summary_filename}")
                return str(summary_path)
            except Exception as e:
                print(f"Error exporting summary: {e}")
                return None

        return None


def main():
    parser = argparse.ArgumentParser(
        description='Analyze health simulation results and export metrics to CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze_health.py --list
  python analyze_health.py --scenario weight-loss
  python analyze_health.py --scenario weight-loss --run init75_medium_20260320_120241
  python analyze_health.py --scenario diabetes phone-addiction
        """
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available scenarios and runs'
    )
    parser.add_argument(
        '--scenario',
        type=str,
        nargs='*',
        default=[],
        help='Scenario name(s) to analyze (default: all) - space-separated'
    )
    parser.add_argument(
        '--run',
        type=str,
        default=None,
        help='Specific run name (optional - if not specified, uses the latest run)'
    )
    parser.add_argument(
        '--results-dir',
        type=str,
        default='results/health',
        help='Path to results directory'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results/csv',
        help='Path to output CSV directory'
    )

    args = parser.parse_args()

    analyzer = HealthAnalyzer(
        results_dir=args.results_dir,
        csv_dir=args.output_dir
    )

    print("=" * 70)
    print("Health Simulation Statistics Analyzer")
    print("=" * 70)

    # 读取可用场景
    available_scenarios = analyzer.list_available_scenarios()

    if not available_scenarios:
        print("\nNo simulation results found.")
        print(f"Looking in: {analyzer.results_dir}")
        return

    if args.list or not args.scenario:
        # 列表模式
        print("\nAvailable Scenarios and Runs:")
        print("-" * 70)
        for scenario, runs in sorted(available_scenarios.items()):
            print(f"\n  {scenario}:")
            for run in runs:
                run_time = datetime.fromtimestamp(run['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
                print(f"    • {run['name']} ({run_time})")
        return

    # 分析模式
    print("\n[1/3] Selecting scenarios...")
    scenarios_to_analyze = args.scenario if args.scenario else list(available_scenarios.keys())
    print(f"  Selected: {', '.join(scenarios_to_analyze)}")

    print("\n[2/3] Extracting metrics from individual runs...")
    all_metrics_by_scenario = {}
    csv_files = []

    for scenario in scenarios_to_analyze:
        if scenario not in available_scenarios:
            print(f"  ⚠ Warning: Scenario '{scenario}' not found")
            continue

        all_metrics_by_scenario[scenario] = {}
        runs = available_scenarios[scenario]

        if args.run:
            # 指定了 run 时，仅处理匹配的运行
            matching_runs = [r for r in runs if r['name'] == args.run]
            if not matching_runs:
                print(f"  [FAIL] Run '{args.run}' not found for scenario '{scenario}'")
                continue
            runs = matching_runs

        for run in runs:
            print(f"  Processing: {scenario}/{run['name']}...")
            results = analyzer.load_results(run['path'])
            if results:
                metrics = analyzer.extract_metrics(results)
                if metrics:
                    all_metrics_by_scenario[scenario][run['name']] = metrics
                    # 从元数据获取评分模式
                    scoring_mode = None
                    if 'metadata' in results:
                        scoring_mode = results['metadata'].get('scoring_mode')
                    csv_path = analyzer.export_to_csv(scenario, run['name'], metrics, scoring_mode)
                    if csv_path:
                        csv_files.append(csv_path)

    if not csv_files:
        print("  [FAIL] No metrics extracted")
        return

    print("\n[3/3] Generating summary report...")
    summary_path = analyzer.generate_summary(all_metrics_by_scenario)

    print("\n" + "=" * 70)
    print("Analysis Complete!")
    print("=" * 70)
    print(f"\nGenerated {len(csv_files)} metric file(s):")
    for csv_file in csv_files:
        print(f"  • {csv_file}")

    if summary_path:
        print(f"\nSummary report: {summary_path}")

    print(f"\nAll files saved to: {analyzer.csv_dir}")


if __name__ == "__main__":
    main()
