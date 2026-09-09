"""Health management prompt templates and builders.

Templates live in ``data/mechanism/prompts/health_*.txt``.
Mixed into ``modules.prompt.scratch.Scratch`` via ``HealthPromptsMixin``.
"""

from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from string import Template
from typing import List, Optional

from pydantic import BaseModel, Field

from modules import utils

# Same shape as modules.prompt.scratch.Result (avoid circular import)
Result = namedtuple("Result", ["prompt", "callback", "failsafe", "return_type"])

HEALTH_PROMPT_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "mechanism" / "prompts"
)


class HealthPromptsMixin:
    """Mixin providing prompt_health_* methods for Scratch."""

    def build_health_prompt(self, template: str, data: dict) -> str:
        """Load a health prompt from data/mechanism/prompts/."""
        path = HEALTH_PROMPT_DIR / f"{template}.txt"
        if not path.exists():
            # fallback: legacy data/prompts/
            legacy = Path("data/prompts") / f"{template}.txt"
            if legacy.exists():
                path = legacy
            else:
                raise FileNotFoundError(f"Health prompt not found: {path}")
        with open(path, "r", encoding="utf-8") as file:
            file_content = file.read()
        return Template(file_content).substitute(data)


    # ===== Health Management Prompts =====

    def prompt_health_generate_intention(self, health_status, forbidden_activities, retrieved_concepts, self_discipline, environment_constraints="无特殊限制", behavior_tendency="stable", is_in_relapse=False):
        """Generate Target's behavioral intention"""
        # 将复发状态转换为中文描述
        relapse_str = "是（正处于复发期，冲动强烈）" if is_in_relapse else "否"

        # 将行为倾向转换为中文描述
        tendency_map = {
            "improving": "improving（改善中）",
            "stable": "stable（稳定）",
            "declining": "declining（恶化中）",
            "relapsing": "relapsing（复发中）",
        }
        tendency_str = tendency_map.get(behavior_tendency, behavior_tendency)

        prompt = self.build_health_prompt(
            "health_generate_intention",
            {
                "name": self.name,
                "current_time": utils.get_timer().daily_format_cn(),
                "innate": self.config["innate"],
                "learned": self.config["learned"],
                "currently": self.currently,
                "health_status": health_status,
                "forbidden_activities": ", ".join(forbidden_activities),
                "retrieved_concepts": "\n".join([f"- {c}" for c in retrieved_concepts]),
                "self_discipline": self_discipline,
                "environment_constraints": environment_constraints,
                "behavior_tendency": tendency_str,
                "is_in_relapse": relapse_str,
            }
        )

        class HealthIntentionRes(BaseModel):
            activity: str
            duration: int = Field(ge=1, le=240)
            compliance_threshold: int = Field(ge=0, le=3)
            inner_monologue: str
            target_location: Optional[str] = None
            is_sleep_related: bool = False

        class HealthIntentionResponse(BaseModel):
            res: HealthIntentionRes

        failsafe = {
            "activity": "休息",
            "duration": 30,
            "compliance_threshold": 1,
            "inner_monologue": "我应该休息一下"
        }

        def _callback(response):
            return {
                "activity": response.activity,
                "duration": response.duration,
                "compliance_threshold": response.compliance_threshold,
                "inner_monologue": response.inner_monologue,
                "target_location": response.target_location,
                "is_sleep_related": response.is_sleep_related,
            }

        return Result(prompt, _callback, failsafe, HealthIntentionResponse)

    def prompt_health_evaluate_strategy(self, target_name, relationship, target_health_status,
                                       target_intention, compliance_threshold, inner_monologue,
                                       target_today_log, strategy_preference):
        """Evaluate Manager's intervention strategy"""
        prompt = self.build_health_prompt(
            "health_evaluate_strategy",
            {
                "name": self.name,
                "current_time": utils.get_timer().daily_format_cn(),
                "innate": self.config["innate"],
                "strategy_preference": strategy_preference,
                "target_name": target_name,
                "relationship": relationship,
                "target_health_status": target_health_status,
                "target_intention": target_intention,
                "compliance_threshold": compliance_threshold,
                "inner_monologue": inner_monologue,
                "target_today_log": target_today_log,
            }
        )

        class HealthStrategyRes(BaseModel):
            level: int = Field(ge=0, le=3)
            action: str
            timing: str
            reason: str

        class HealthStrategyResponse(BaseModel):
            res: HealthStrategyRes

        failsafe = {
            "level": 0,
            "action": "observe",
            "timing": "none",
            "reason": "继续观察"
        }

        def _callback(response):
            return {
                "level": response.level,
                "action": response.action,
                "timing": response.timing,
                "reason": response.reason
            }

        return Result(prompt, _callback, failsafe, HealthStrategyResponse)

    def prompt_health_generate_persuasion(self, target_name, target_intention, strategy_reason,
                                         relationship, target_personality):
        """Generate persuasion text"""
        prompt = self.build_health_prompt(
            "health_generate_persuasion",
            {
                "name": self.name,
                "target_name": target_name,
                "target_intention": target_intention,
                "strategy_reason": strategy_reason,
                "relationship": relationship,
                "your_personality": self.config["innate"],
                "target_personality": target_personality,
            }
        )

        class HealthPersuasionResponse(BaseModel):
            res: str

        failsafe = f"{target_name}，这样对你的健康不好。"

        return Result(prompt, None, failsafe, HealthPersuasionResponse)

    def prompt_health_react_persuasion(self, supervisor_name, your_intention, persuasion_text,
                                      strategy_reason, self_discipline, inner_monologue):
        """React to persuasion"""
        prompt = self.build_health_prompt(
            "health_react_persuasion",
            {
                "name": self.name,
                "your_intention": your_intention,
                "supervisor_name": supervisor_name,
                "persuasion_text": persuasion_text,
                "strategy_reason": strategy_reason,
                "your_personality": self.config["innate"],
                "self_discipline": self_discipline,
                "inner_monologue": inner_monologue,
            }
        )

        class HealthReactionRes(BaseModel):
            accept: bool
            response: str
            inner_thought: str

        class HealthReactionResponse(BaseModel):
            res: HealthReactionRes

        failsafe = {
            "accept": False,
            "response": "我知道了",
            "inner_thought": "我还是想做"
        }

        def _callback(response):
            return {
                "accept": response.accept,
                "response": response.response,
                "inner_thought": response.inner_thought
            }

        return Result(prompt, _callback, failsafe, HealthReactionResponse)

    def prompt_health_daily_reflection(self, day, target_name, monitoring_hours, day_log,
                                      intervention_log, health_score, score_breakdown):
        """Daily reflection for Manager"""
        prompt = self.build_health_prompt(
            "health_daily_reflection",
            {
                "name": self.name,
                "target_name": target_name,
                "day": day,
                "monitoring_hours": monitoring_hours,
                "day_log": day_log,
                "intervention_log": intervention_log,
                "health_score": health_score,
                "score_breakdown": score_breakdown,
            }
        )

        class HealthReflectionRes(BaseModel):
            today_summary: str
            strategy_effectiveness: str
            risk_patterns: List[str]
            tomorrow_focus: str
            strategy_adjustment: str

        class HealthReflectionResponse(BaseModel):
            res: HealthReflectionRes

        failsafe = {
            "today_summary": "今天的监督工作已完成",
            "strategy_effectiveness": "策略基本有效",
            "risk_patterns": [],
            "tomorrow_focus": "继续观察",
            "strategy_adjustment": "保持当前策略"
        }

        def _callback(response):
            return {
                "today_summary": response.today_summary,
                "strategy_effectiveness": response.strategy_effectiveness,
                "risk_patterns": response.risk_patterns,
                "tomorrow_focus": response.tomorrow_focus,
                "strategy_adjustment": response.strategy_adjustment
            }

        return Result(prompt, _callback, failsafe, HealthReflectionResponse)

    # ============================================================================
    # Batch Processing Prompts for Performance Optimization
    # ============================================================================

    def prompt_health_generate_intention_batch(self, day, num_slots, time_slots,
                                                health_status, forbidden_activities,
                                                self_discipline, environment_constraints,
                                                behavior_tendency, is_in_relapse,
                                                target_sleep_time="23:30",
                                                available_locations=None):
        """
        批量生成一整天所有时间点的意图（性能优化）

        Args:
            day: 当前天数
            num_slots: 时间点数量
            time_slots: 时间点列表，如 ["21:00", "21:30", ...]
            health_status: 健康状态
            forbidden_activities: 禁止活动
            self_discipline: 自律程度
            environment_constraints: 环境约束
            behavior_tendency: 行为倾向
            is_in_relapse: 是否复发
            target_sleep_time: 目标睡眠时间
            available_locations: 场景可用语义位置白名单
        """
        relapse_str = "是（正处于复发期，冲动强烈）" if is_in_relapse else "否"
        tendency_map = {
            "improving": "improving（改善中）",
            "stable": "stable（稳定）",
            "declining": "declining（恶化中）",
            "relapsing": "relapsing（复发中）",
        }
        tendency_str = tendency_map.get(behavior_tendency, behavior_tendency)

        # 构建时间点字符串
        time_slots_str = ", ".join(time_slots)
        location_keys = available_locations or ["living_room", "kitchen", "bedroom"]
        location_list_str = ", ".join(location_keys)
        location_rules_lines = []
        if "living_room" in location_keys:
            location_rules_lines.append('- 看电视、聊天、放松 -> "living_room"')
        if "kitchen" in location_keys:
            location_rules_lines.append('- 吃东西、找食物 -> "kitchen"')
        if "bedroom" in location_keys:
            location_rules_lines.append('- 睡觉、休息 -> "bedroom"')
        if "phone_area" in location_keys:
            location_rules_lines.append('- 手机相关活动 -> "phone_area"')
        location_rules = "\n".join(location_rules_lines) if location_rules_lines else "- 使用最匹配的可用位置"

        prompt = self.build_health_prompt(
            "health_generate_intention_batch",
            {
                "name": self.name,
                "current_date": utils.get_timer().get_date().strftime("%Y-%m-%d"),
                "day": day,
                "start_time": time_slots[0] if time_slots else "21:00",
                "end_time": time_slots[-1] if time_slots else "02:00",
                "num_slots": num_slots,
                "innate": self.config["innate"],
                "learned": self.config["learned"],
                "currently": self.currently,
                "health_status": health_status,
                "forbidden_activities": ", ".join(forbidden_activities),
                "self_discipline": self_discipline,
                "environment_constraints": environment_constraints,
                "behavior_tendency": tendency_str,
                "is_in_relapse": relapse_str,
                "time_slots": time_slots_str,
                "target_sleep_time": target_sleep_time,
                "available_locations": location_list_str,
                "location_rules": location_rules,
            }
        )

        class IntentionItem(BaseModel):
            time_slot: int
            time: str
            activity: str
            duration: int = Field(ge=1, le=240)
            compliance_threshold: int = Field(ge=0, le=3)
            inner_monologue: str
            target_location: Optional[str] = None
            is_sleep_related: bool = False

        class BatchIntentionResponse(BaseModel):
            res: List[IntentionItem]

        # 生成默认的failsafe
        default_location = "living_room" if "living_room" in location_keys else location_keys[0]
        failsafe = [
            {
                "time_slot": i,
                "time": time_slots[i] if i < len(time_slots) else f"{21 + i//2}:{(i%2)*30:02d}",
                "activity": "休息",
                "duration": 30,
                "compliance_threshold": 1,
                "inner_monologue": "我应该休息",
                "target_location": default_location,
                "is_sleep_related": False
            }
            for i in range(num_slots)
        ]

        def _callback(response):
            return [
                {
                    "time_slot": item.time_slot,
                    "time": item.time,
                    "activity": item.activity,
                    "duration": item.duration,
                    "compliance_threshold": item.compliance_threshold,
                    "inner_monologue": item.inner_monologue,
                    "target_location": item.target_location,
                    "is_sleep_related": item.is_sleep_related
                }
                for item in response
            ]

        return Result(prompt, _callback, failsafe, BatchIntentionResponse)

    def prompt_health_generate_turnaround(self, original_activity, target_location_desc,
                                           block_reason, environment_constraints,
                                           self_discipline):
        """
        生成折返时的内心独白和替代活动

        Args:
            original_activity: 原本想做的事
            target_location_desc: 目标位置描述
            block_reason: 被阻止的原因
            environment_constraints: 当前环境限制
            self_discipline: 自律程度
        """
        prompt = self.build_health_prompt(
            "health_generate_turnaround",
            {
                "name": self.name,
                "original_activity": original_activity,
                "target_location_desc": target_location_desc,
                "block_reason": block_reason,
                "environment_constraints": environment_constraints,
                "self_discipline": self_discipline,
                "innate": self.config["innate"],
            }
        )

        class TurnaroundResponse(BaseModel):
            turnaround_monologue: str
            redirect_activity: str
            redirect_location: str
            emotional_reaction: str

        class TurnaroundResult(BaseModel):
            res: TurnaroundResponse

        failsafe = {
            "turnaround_monologue": f"想{original_activity}，但是{block_reason}。算了，只能做点别的了。",
            "redirect_activity": "去客厅看电视",
            "redirect_location": "living_room",
            "emotional_reaction": "resigned"
        }

        def _callback(response):
            return {
                "turnaround_monologue": response.turnaround_monologue,
                "redirect_activity": response.redirect_activity,
                "redirect_location": response.redirect_location,
                "emotional_reaction": response.emotional_reaction
            }

        return Result(prompt, _callback, failsafe, TurnaroundResult)

    def prompt_health_evaluate_strategy_batch(self, day, target_name, target_profile,
                                               forbidden_activities, intentions_list,
                                               supervision_style, relationship,
                                               escalation_threshold,
                                               self_discipline="medium",
                                               health_score=75.0):
        """
        批量评估一整天所有意图的干预策略（性能优化）

        Args:
            day: 当前天数
            target_name: 被监督者名称
            target_profile: 被监督者档案
            forbidden_activities: 禁止活动
            intentions_list: 所有意图列表
            supervision_style: 监督风格
            relationship: 关系
            escalation_threshold: 升级阈值
            self_discipline: 被监督者自律程度
            health_score: 当前健康分
        """
        # 构建意图列表字符串
        intentions_str = "\n".join([
            f"- [{item['time']}] 意图: {item['activity']} (位置: {item.get('target_location') or '未指定'}, 遵守难度: {item['compliance_threshold']}, 内心独白: {item['inner_monologue']})"
            for item in intentions_list
        ])

        prompt = self.build_health_prompt(
            "health_evaluate_strategy_batch",
            {
                "name": self.name,
                "day": day,
                "target_name": target_name,
                "target_profile": target_profile,
                "forbidden_activities": ", ".join(forbidden_activities),
                "intentions_list": intentions_str,
                "supervision_style": supervision_style,
                "relationship": relationship,
                "escalation_threshold": escalation_threshold,
                "self_discipline": self_discipline,
                "health_score": f"{health_score:.1f}",
            }
        )

        class TurnaroundItem(BaseModel):
            turnaround_monologue: str
            redirect_activity: str
            redirect_location: str
            emotional_reaction: str

        class StrategyItem(BaseModel):
            time_slot: int
            time: str
            level: int = Field(ge=0, le=3)
            action: str
            reason: str
            predicted_blocked: bool = False
            turnaround_if_blocked: Optional[TurnaroundItem] = None

        class BatchStrategyResponse(BaseModel):
            res: List[StrategyItem]

        # 生成默认的failsafe
        failsafe = [
            {
                "time_slot": i,
                "time": item.get("time", f"{21 + i//2}:{(i%2)*30:02d}"),
                "level": 0,
                "action": "观察",
                "reason": "行为正常，无需干预",
                "predicted_blocked": False,
                "turnaround_if_blocked": None
            }
            for i, item in enumerate(intentions_list)
        ]

        def _callback(response):
            return [
                {
                    "time_slot": item.time_slot,
                    "time": item.time,
                    "level": item.level,
                    "action": item.action,
                    "reason": item.reason,
                    "predicted_blocked": item.predicted_blocked,
                    "turnaround_if_blocked": {
                        "turnaround_monologue": item.turnaround_if_blocked.turnaround_monologue,
                        "redirect_activity": item.turnaround_if_blocked.redirect_activity,
                        "redirect_location": item.turnaround_if_blocked.redirect_location,
                        "emotional_reaction": item.turnaround_if_blocked.emotional_reaction
                    } if item.turnaround_if_blocked else None
                }
                for item in response
            ]

        return Result(prompt, _callback, failsafe, BatchStrategyResponse)
