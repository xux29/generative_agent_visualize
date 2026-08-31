"""generative_agents.strategy

策略系统：Manager Agent 的干预策略

核心机制（基于会议讨论 2026-01-22）：
- 潮汐性/锯齿型动态调整：不好→严管→变好→放松→可能又变坏→又严管
- 跨时间策略调整：根据被管者状态动态升降档
- 信任度机制：连续表现好建立信任，过度干预破坏信任

长期机制（2026-01-22 扩展）：
1. 阶段性策略规划：蜜月期→调整期→倦怠期→稳定期
2. 周期性反思与调整：周回顾、月总结
3. 信任资本积累：可以"花"的信任资本
4. 习惯巩固识别：区分暂时顺从 vs 真正内化
5. 长期目标调整：阶段性目标调整
"""

from copy import deepcopy
from enum import Enum
from typing import List, Dict, Optional, Tuple
import random

from modules.mechanism_config import get_path


def _mgmt(dotted: str, default=None):
    """读取 management.* 配置；缺失时返回 default。"""
    return get_path(f"management.{dotted}", default)


class Strategy:
    """表示 Manager 的干预策略"""

    # 策略等级常量
    LEVEL_0_OBSERVE = 0  # 观察，不干预
    LEVEL_1_PERSUADE = 1  # 劝说，温和提醒
    LEVEL_2_REMOVE = 2  # 移除物品（拿走手机/零食）
    LEVEL_3_LOCK = 3  # 封锁空间（锁门）

    # 时机常量
    TIMING_NONE = "none"  # 不干预
    TIMING_IMMEDIATE = "immediate"  # 立即干预
    TIMING_DELAYED = "delayed"  # 延迟干预

    def __init__(self, level, action="observe", timing="none", reason="", delay_minutes=0):
        """
        初始化策略

        Args:
            level: 策略等级（0-3）
            action: 具体动作，如"observe", "persuade", "remove_phone", "lock_kitchen"
            timing: 干预时机，"none", "immediate", "delayed"
            reason: 选择该策略的理由
            delay_minutes: 如果是延迟干预，延迟多少分钟
        """
        self.level = level
        self.action = action
        self.timing = timing
        self.reason = reason
        self.delay_minutes = delay_minutes

    @staticmethod
    def observe(reason="正常行为，无需干预"):
        """创建观察策略"""
        return Strategy(
            level=Strategy.LEVEL_0_OBSERVE,
            action="observe",
            timing=Strategy.TIMING_NONE,
            reason=reason
        )

    @staticmethod
    def persuade(reason="温和劝说", immediate=True):
        """创建劝说策略"""
        return Strategy(
            level=Strategy.LEVEL_1_PERSUADE,
            action="persuade",
            timing=Strategy.TIMING_IMMEDIATE if immediate else Strategy.TIMING_DELAYED,
            reason=reason
        )

    @staticmethod
    def remove_object(obj_type, reason="移除诱惑物品", immediate=True):
        """创建移除物品策略"""
        action_map = {
            "phone": "remove_phone",
            "snack": "remove_snack",
            "food": "remove_food"
        }
        return Strategy(
            level=Strategy.LEVEL_2_REMOVE,
            action=action_map.get(obj_type, "remove_object"),
            timing=Strategy.TIMING_IMMEDIATE if immediate else Strategy.TIMING_DELAYED,
            reason=reason
        )

    @staticmethod
    def lock_space(space_type, reason="封锁空间", immediate=True):
        """创建锁定空间策略"""
        action_map = {
            "kitchen": "lock_kitchen",
            "device_room": "lock_device_room",
            "bedroom": "lock_bedroom"
        }
        return Strategy(
            level=Strategy.LEVEL_3_LOCK,
            action=action_map.get(space_type, "lock_space"),
            timing=Strategy.TIMING_IMMEDIATE if immediate else Strategy.TIMING_DELAYED,
            reason=reason
        )

    def is_intervention_needed(self):
        """是否需要干预"""
        return self.level > 0 and self.timing != Strategy.TIMING_NONE

    def to_dict(self):
        """转换为字典"""
        return {
            "level": self.level,
            "action": self.action,
            "timing": self.timing,
            "reason": self.reason,
            "delay_minutes": self.delay_minutes
        }

    def __str__(self):
        level_names = ["观察", "劝说", "移除物品", "锁定空间"]
        level_name = level_names[self.level] if 0 <= self.level <= 3 else "未知"
        return f"Strategy(Level {self.level}: {level_name}, action='{self.action}', timing={self.timing})"


class StrategyManager:
    """
    策略管理器：实现跨时间的动态策略调整（潮汐性/锯齿型变化）

    核心机制：
    1. 松-紧循环：不好→严管→变好→放松→可能又变坏→又严管
    2. 信任度机制：连续表现好建立信任，过度干预破坏信任
    3. 场景差异化：糖尿病(敏感)、减肥(中等)、睡眠(宽松)
    """

    # 场景严重程度配置（影响阈值和响应速度）
    SCENARIO_SEVERITY = {
        "diabetes": {
            "name": "糖尿病",
            "health_threshold_bad": 5,      # 低于此值视为"不好"
            "health_threshold_good": 7,     # 高于此值视为"好"
            "consecutive_good_days_to_relax": 3,   # 连续多少天好才能放松
            "consecutive_bad_days_to_escalate": 1, # 连续多少天不好就升档（糖尿病一天就要管）
            "relapse_probability_base": 0.4,       # 放松后复发基础概率
            "severity_weight": 1.5,                # 严重程度权重（影响响应速度）
        },
        "weight_loss": {
            "name": "减肥",
            "health_threshold_bad": 4,
            "health_threshold_good": 6,
            "consecutive_good_days_to_relax": 5,
            "consecutive_bad_days_to_escalate": 2,
            "relapse_probability_base": 0.3,
            "severity_weight": 1.0,
        },
        "sleep": {
            "name": "睡眠",
            "health_threshold_bad": 4,
            "health_threshold_good": 6,
            "consecutive_good_days_to_relax": 7,
            "consecutive_bad_days_to_escalate": 3,
            "relapse_probability_base": 0.25,
            "severity_weight": 0.7,
        },
    }

    def __init__(self, scenario="diabetes"):
        """
        初始化策略管理器

        Args:
            scenario: 场景类型 ("diabetes", "weight_loss", "sleep")
        """
        self.scenario = scenario.lower().replace("-", "_").replace("home_", "")
        scenarios = _mgmt("tidal.scenarios") or self.SCENARIO_SEVERITY
        if self.scenario not in scenarios:
            self.scenario = "diabetes"  # 默认

        scenario_cfg = scenarios.get(self.scenario) or self.SCENARIO_SEVERITY.get(
            self.scenario, self.SCENARIO_SEVERITY["diabetes"]
        )
        self.config = deepcopy(scenario_cfg)

        # 潮汐信任度参数（management.tidal.trust_level）
        trust = _mgmt("tidal.trust_level") or {}
        self.trust_cfg = {
            "initial": trust.get("initial", 0.5),
            "good_delta": trust.get("good_delta", 0.1),
            "bad_delta": trust.get("bad_delta", -0.15),
            "over_intervention_delta": trust.get("over_intervention_delta", -0.2),
            "relax_min": trust.get("relax_min", 0.6),
            "good_streak_bonus_per_day": trust.get("good_streak_bonus_per_day", 0.02),
            "good_streak_bonus_cap": trust.get("good_streak_bonus_cap", 0.1),
            "good_streak_bonus_min_days": trust.get("good_streak_bonus_min_days", 2),
        }

        # 干预等级（management.intervention）
        interv = _mgmt("intervention") or {}
        self.max_intervention_level = interv.get("max_level", 3)
        self.intervention_levels = interv.get("levels") or {
            "0": "observe", "1": "persuade", "2": "remove", "3": "lock",
        }

        # 状态追踪
        self.current_level = 0           # 当前策略等级
        self.consecutive_good_days = 0   # 连续良好天数
        self.consecutive_bad_days = 0    # 连续不良天数
        self.trust_level = self.trust_cfg["initial"]  # 信任度 (0-1)
        self.health_history = []         # 健康分历史
        self.intervention_history = []   # 干预历史
        self.relaxation_day = None       # 开始放松的日期
        self.is_relaxed = False          # 当前是否处于放松状态

    def update_state(self, day, health_score, intervention_count):
        """
        根据当日数据更新状态

        Args:
            day: 当前天数
            health_score: 当日健康分 (0-10)
            intervention_count: 当日干预次数

        Returns:
            dict: 状态更新结果
        """
        self.health_history.append({"day": day, "score": health_score})
        self.intervention_history.append({"day": day, "count": intervention_count})

        threshold_bad = self.config["health_threshold_bad"]
        threshold_good = self.config["health_threshold_good"]

        # 判断今天表现好还是不好
        if health_score >= threshold_good:
            self.consecutive_good_days += 1
            self.consecutive_bad_days = 0
            is_good_today = True
        elif health_score < threshold_bad:
            self.consecutive_bad_days += 1
            self.consecutive_good_days = 0
            is_good_today = False
        else:
            # 中等表现，不重置连续天数
            is_good_today = None

        # 更新信任度
        self._update_trust(health_score, intervention_count)

        return {
            "is_good_today": is_good_today,
            "consecutive_good_days": self.consecutive_good_days,
            "consecutive_bad_days": self.consecutive_bad_days,
            "trust_level": self.trust_level,
            "current_level": self.current_level,
            "is_relaxed": self.is_relaxed,
        }

    def _update_trust(self, health_score, intervention_count):
        """
        更新信任度

        规则：
        - 表现好：信任度 +0.1（最高1.0）
        - 连续表现好多天：额外增加信任（激励持续良好行为）
        - 表现差：信任度 -0.15
        - 过度干预（>=3次且健康分>=6）：信任度 -0.2（好了还严管）
          但如果是复发后的恢复期（consecutive_good_days < 需要天数），不扣减

        核心理念：
        - 复发后需要一段恢复期重建信任
        - 恢复期内的严格管控是必要的，不应惩罚信任
        - 只有长期表现好后还被过度干预才扣信任
        """
        threshold_good = self.config["health_threshold_good"]
        required_good_days = self.config["consecutive_good_days_to_relax"]
        tc = self.trust_cfg

        if health_score >= threshold_good:
            # 表现好，增加信任
            base_trust_gain = tc["good_delta"]

            # 连续表现好时，信任增长更快
            if self.consecutive_good_days >= tc["good_streak_bonus_min_days"]:
                bonus = min(
                    tc["good_streak_bonus_cap"],
                    self.consecutive_good_days * tc["good_streak_bonus_per_day"],
                )
                base_trust_gain += bonus

            self.trust_level = min(1.0, self.trust_level + base_trust_gain)

            # 过度干预惩罚：只有在已经持续表现好足够长时间后才适用
            # 这样复发后的恢复期内不会被不公平地扣分
            if intervention_count >= 3 and self.consecutive_good_days >= required_good_days:
                # over_intervention_delta 为负值（如 -0.2）
                self.trust_level = max(0.0, self.trust_level + tc["over_intervention_delta"])

        elif health_score < self.config["health_threshold_bad"]:
            # 表现差，减少信任（bad_delta 为负值）
            self.trust_level = max(0.0, self.trust_level + tc["bad_delta"])

    def should_escalate(self):
        """
        判断是否应该升档（加严管控）

        Returns:
            bool: 是否应该升档
        """
        required_bad_days = self.config["consecutive_bad_days_to_escalate"]
        return (
            self.consecutive_bad_days >= required_bad_days
            and self.current_level < self.max_intervention_level
        )

    def should_relax(self):
        """
        判断是否应该放松管控

        Returns:
            bool: 是否应该放松
        """
        required_good_days = self.config["consecutive_good_days_to_relax"]
        return (
            self.consecutive_good_days >= required_good_days
            and self.current_level > 0
            and self.trust_level >= self.trust_cfg["relax_min"]
        )

    def get_recommended_level(self, day):
        """
        获取推荐的策略等级（核心的动态调整逻辑）

        实现潮汐性变化：
        - 不好 → 升档严管
        - 变好且持续一段时间 → 降档放松
        - 放松后如果又变坏 → 重新升档

        Args:
            day: 当前天数

        Returns:
            tuple: (推荐等级, 调整原因)
        """
        old_level = self.current_level

        # 情况1：应该升档（表现持续不好）
        if self.should_escalate():
            self.current_level = min(self.max_intervention_level, self.current_level + 1)
            self.is_relaxed = False
            self.relaxation_day = None
            reason = f"连续{self.consecutive_bad_days}天表现不佳，升档至Level {self.current_level}"
            return self.current_level, reason

        # 情况2：应该放松（表现持续好）
        if self.should_relax():
            self.current_level = max(0, self.current_level - 1)
            if not self.is_relaxed:
                self.is_relaxed = True
                self.relaxation_day = day
            reason = f"连续{self.consecutive_good_days}天表现良好，降档至Level {self.current_level}"
            return self.current_level, reason

        # 情况3：维持当前等级
        if self.current_level == old_level:
            if self.is_relaxed:
                reason = f"放松观察中，维持Level {self.current_level}"
            else:
                reason = f"维持当前策略Level {self.current_level}"
        else:
            reason = f"调整至Level {self.current_level}"

        return self.current_level, reason

    def calculate_relapse_probability(self, self_discipline="medium"):
        """
        计算放松后的复发概率（被管者"干坏事"的概率）

        公式：
        relapse_prob = base_prob * (1 - trust_level * 0.3) * discipline_modifier * time_modifier

        Args:
            self_discipline: 被管者的自律程度

        Returns:
            float: 复发概率 (0-1)
        """
        if not self.is_relaxed:
            return 0.0

        base_prob = self.config["relapse_probability_base"]

        # 自律程度修正
        discipline_modifiers = {
            "very_low": 1.5,   # 自律极低，更容易复发
            "low": 1.3,
            "medium": 1.0,
            "high": 0.7,
            "very_high": 0.4,
        }
        discipline_mod = discipline_modifiers.get(self_discipline, 1.0)

        # 信任度修正（信任度高，复发概率低）
        trust_mod = 1 - self.trust_level * 0.3

        # 放松时间修正（放松越久，复发概率越高）
        if self.relaxation_day and len(self.health_history) > 0:
            current_day = self.health_history[-1]["day"]
            days_since_relax = current_day - self.relaxation_day
            # 每放松5天，概率增加10%
            time_mod = 1 + (days_since_relax / 5) * 0.1
        else:
            time_mod = 1.0

        relapse_prob = base_prob * trust_mod * discipline_mod * time_mod
        return min(1.0, max(0.0, relapse_prob))

    def on_relapse(self):
        """
        处理复发事件（被管者又开始"干坏事"）

        Returns:
            int: 新的策略等级
        """
        self.is_relaxed = False
        self.relaxation_day = None
        self.consecutive_good_days = 0
        self.consecutive_bad_days = 1

        # 复发后根据场景严重程度决定升档幅度
        max_lv = self.max_intervention_level
        severity = self.config["severity_weight"]
        if severity >= 1.5:
            # 糖尿病：直接升到最高档
            self.current_level = max_lv
        elif severity >= 1.0:
            # 减肥：升2档或到最高
            self.current_level = min(max_lv, self.current_level + 2)
        else:
            # 睡眠：升1档
            self.current_level = min(max_lv, self.current_level + 1)

        return self.current_level

    def get_status_summary(self):
        """
        获取当前状态摘要

        Returns:
            dict: 状态摘要
        """
        return {
            "scenario": self.config["name"],
            "current_level": self.current_level,
            "trust_level": round(self.trust_level, 2),
            "consecutive_good_days": self.consecutive_good_days,
            "consecutive_bad_days": self.consecutive_bad_days,
            "is_relaxed": self.is_relaxed,
            "relaxation_day": self.relaxation_day,
            "health_trend": self._get_health_trend(),
        }

    def _get_health_trend(self, window=7):
        """计算健康分趋势"""
        if len(self.health_history) < 2:
            return 0.0
        recent = self.health_history[-window:] if len(self.health_history) >= window else self.health_history
        return recent[-1]["score"] - recent[0]["score"]

    def to_dict(self):
        """序列化为字典（用于保存检查点）"""
        return {
            "scenario": self.scenario,
            "current_level": self.current_level,
            "consecutive_good_days": self.consecutive_good_days,
            "consecutive_bad_days": self.consecutive_bad_days,
            "trust_level": self.trust_level,
            "health_history": self.health_history,
            "intervention_history": self.intervention_history,
            "relaxation_day": self.relaxation_day,
            "is_relaxed": self.is_relaxed,
        }

    @classmethod
    def from_dict(cls, data):
        """从字典恢复（用于加载检查点）"""
        manager = cls(scenario=data.get("scenario", "diabetes"))
        manager.current_level = data.get("current_level", 0)
        manager.consecutive_good_days = data.get("consecutive_good_days", 0)
        manager.consecutive_bad_days = data.get("consecutive_bad_days", 0)
        manager.trust_level = data.get("trust_level", 0.5)
        manager.health_history = data.get("health_history", [])
        manager.intervention_history = data.get("intervention_history", [])
        manager.relaxation_day = data.get("relaxation_day")
        manager.is_relaxed = data.get("is_relaxed", False)
        return manager


# ============================================================================
# 长期监管机制扩展
# ============================================================================

class RelationshipPhase(Enum):
    """关系阶段枚举"""
    HONEYMOON = "honeymoon"      # 蜜月期：刚开始，双方都有动力
    ADJUSTMENT = "adjustment"    # 调整期：磨合，冲突出现
    FATIGUE = "fatigue"          # 倦怠期：疲劳，可能放松或对抗
    STABLE = "stable"            # 稳定期：习惯已形成，自主性高
    RELAPSE = "relapse"          # 复发期：旧习惯回归，需要重新管理


class HabitConsolidation:
    """
    习惯巩固识别器：区分"暂时顺从"vs"真正内化"

    核心指标：
    1. 无干预自觉率：没有被提醒/干预时的自觉行为比例
    2. 抵抗衰减率：放松后抵抗诱惑的能力衰减速度
    3. 主动性指标：主动表达健康意愿的频率
    4. 情绪一致性：行为与情绪是否一致（被迫vs主动）
    """

    # 习惯内化阶段
    STAGE_FORCED = "forced"           # 被迫阶段：完全依赖外部管控
    STAGE_COMPLIANT = "compliant"     # 顺从阶段：配合但没内化
    STAGE_INTERNALIZED = "internalized"  # 内化阶段：开始自我管理
    STAGE_AUTONOMOUS = "autonomous"   # 自主阶段：完全自律

    def __init__(self):
        self.no_intervention_compliance_rate = 0.0  # 无干预自觉率
        self.proactive_health_actions = 0           # 主动健康行为次数
        self.total_opportunities = 0                # 总机会数
        self.resistance_after_relax = []            # 放松后的抵抗记录
        self.emotion_behavior_alignment = []        # 情绪行为一致性记录

        hc = _mgmt("habit_consolidation") or {}
        weights = hc.get("weights") or {}
        self.score_weights = {
            "no_intervention": weights.get("no_intervention", 0.4),
            "proactive": weights.get("proactive", 0.3),
            "emotion": weights.get("emotion", 0.3),
        }
        self.min_opportunities = hc.get("min_opportunities", 7)
        thresholds = hc.get("stage_thresholds") or {}
        self.stage_thresholds = {
            "autonomous": thresholds.get("autonomous", 0.8),
            "internalized": thresholds.get("internalized", 0.6),
            "compliant": thresholds.get("compliant", 0.3),
        }

    def record_opportunity(self, day: int, intervention_level: int, complied: bool,
                           was_proactive: bool = False, emotion_positive: bool = None):
        """
        记录一次行为机会

        Args:
            day: 天数
            intervention_level: 干预等级（0=无干预）
            complied: 是否遵从健康行为
            was_proactive: 是否主动（非被动顺从）
            emotion_positive: 情绪是否积极（None表示未知）
        """
        self.total_opportunities += 1

        if intervention_level == 0 and complied:
            # 无干预时自觉遵从
            self.no_intervention_compliance_rate = (
                (self.no_intervention_compliance_rate * (self.total_opportunities - 1) + 1)
                / self.total_opportunities
            )
        elif intervention_level == 0:
            self.no_intervention_compliance_rate = (
                self.no_intervention_compliance_rate * (self.total_opportunities - 1)
                / self.total_opportunities
            )

        if was_proactive:
            self.proactive_health_actions += 1

        if emotion_positive is not None:
            self.emotion_behavior_alignment.append({
                "day": day,
                "complied": complied,
                "emotion_positive": emotion_positive,
                "aligned": complied == emotion_positive  # 行为与情绪一致
            })

    def record_relax_resistance(self, day: int, resisted_temptation: bool):
        """记录放松期间的抵抗情况"""
        self.resistance_after_relax.append({
            "day": day,
            "resisted": resisted_temptation
        })

    def get_internalization_stage(self) -> str:
        """
        判断当前习惯内化阶段

        Returns:
            str: 内化阶段
        """
        if self.total_opportunities < self.min_opportunities:
            return self.STAGE_FORCED  # 数据太少

        # 计算关键指标
        proactive_rate = self.proactive_health_actions / max(1, self.total_opportunities)
        no_interv_rate = self.no_intervention_compliance_rate

        # 计算情绪一致率
        if self.emotion_behavior_alignment:
            aligned_count = sum(1 for r in self.emotion_behavior_alignment if r["aligned"])
            emotion_alignment = aligned_count / len(self.emotion_behavior_alignment)
        else:
            emotion_alignment = 0.0

        # 综合评分（权重来自 management.habit_consolidation）
        w = self.score_weights
        score = (
            no_interv_rate * w["no_intervention"]
            + proactive_rate * w["proactive"]
            + emotion_alignment * w["emotion"]
        )

        th = self.stage_thresholds
        if score >= th["autonomous"]:
            return self.STAGE_AUTONOMOUS
        elif score >= th["internalized"]:
            return self.STAGE_INTERNALIZED
        elif score >= th["compliant"]:
            return self.STAGE_COMPLIANT
        else:
            return self.STAGE_FORCED

    def get_summary(self) -> Dict:
        """获取习惯巩固摘要"""
        stage = self.get_internalization_stage()
        stage_names = {
            self.STAGE_FORCED: "被迫阶段",
            self.STAGE_COMPLIANT: "顺从阶段",
            self.STAGE_INTERNALIZED: "内化阶段",
            self.STAGE_AUTONOMOUS: "自主阶段",
        }
        return {
            "stage": stage,
            "stage_name": stage_names.get(stage, "未知"),
            "no_intervention_compliance_rate": round(self.no_intervention_compliance_rate, 2),
            "proactive_rate": round(self.proactive_health_actions / max(1, self.total_opportunities), 2),
            "total_opportunities": self.total_opportunities,
        }

    def to_dict(self) -> Dict:
        return {
            "no_intervention_compliance_rate": self.no_intervention_compliance_rate,
            "proactive_health_actions": self.proactive_health_actions,
            "total_opportunities": self.total_opportunities,
            "resistance_after_relax": self.resistance_after_relax,
            "emotion_behavior_alignment": self.emotion_behavior_alignment,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "HabitConsolidation":
        obj = cls()
        obj.no_intervention_compliance_rate = data.get("no_intervention_compliance_rate", 0.0)
        obj.proactive_health_actions = data.get("proactive_health_actions", 0)
        obj.total_opportunities = data.get("total_opportunities", 0)
        obj.resistance_after_relax = data.get("resistance_after_relax", [])
        obj.emotion_behavior_alignment = data.get("emotion_behavior_alignment", [])
        return obj


class TrustCapital:
    """
    信任资本系统：可积累、可消耗的信任

    核心概念：
    - 信任资本是"可花费"的资源
    - 严格管控消耗信任资本
    - 宽松对待需要"花"信任资本
    - 高信任资本允许更多自主权
    - 低信任资本需要更严格管控
    """

    def __init__(self, initial_capital: float = None):
        tc = _mgmt("trust_capital") or {}
        if initial_capital is None:
            initial_capital = tc.get("initial_capital", 50.0)
        self.capital = initial_capital       # 当前信任资本
        self.max_capital = tc.get("max_capital", 100.0)
        self.min_capital = tc.get("min_capital", 0.0)
        autonomy = tc.get("autonomy_thresholds") or {}
        self.autonomy_thresholds = {
            "high": autonomy.get("high", 80),
            "medium": autonomy.get("medium", 50),
            "low": autonomy.get("low", 20),
        }
        daily = tc.get("daily") or {}
        self.daily = {
            "good_earn": daily.get("good_earn", 2),
            "proactive_earn": daily.get("proactive_earn", 3),
            "no_intervention_earn": daily.get("no_intervention_earn", 2),
            "bad_loss": daily.get("bad_loss", 5),
            "stable_bad_loss": daily.get("stable_bad_loss", 8),
            "relapse_loss": daily.get("relapse_loss", 10),
        }
        self.capital_history = []            # 资本变化历史
        self.spent_capital = 0.0             # 累计花费的信任资本
        self.earned_capital = 0.0            # 累计赚取的信任资本

    def earn(self, amount: float, reason: str = ""):
        """
        赚取信任资本

        触发条件：
        - 自觉遵守规则：+2
        - 主动表达健康意愿：+3
        - 连续多天表现好：+1每天（复利）
        - 成功抵抗诱惑：+5
        """
        actual_earn = min(amount, self.max_capital - self.capital)
        self.capital += actual_earn
        self.earned_capital += actual_earn
        self.capital_history.append({
            "type": "earn",
            "amount": actual_earn,
            "reason": reason,
            "balance": self.capital
        })
        return actual_earn

    def spend(self, amount: float, reason: str = "") -> bool:
        """
        花费信任资本（用于获得更多自主权）

        Returns:
            bool: 是否成功花费
        """
        if self.capital >= amount:
            self.capital -= amount
            self.spent_capital += amount
            self.capital_history.append({
                "type": "spend",
                "amount": amount,
                "reason": reason,
                "balance": self.capital
            })
            return True
        return False

    def lose(self, amount: float, reason: str = ""):
        """
        损失信任资本（因违规行为）

        触发条件：
        - 违规行为：-5
        - 复发：-10
        - 欺骗/隐瞒：-15
        - 对抗干预：-8
        """
        actual_loss = min(amount, self.capital - self.min_capital)
        self.capital -= actual_loss
        self.capital_history.append({
            "type": "lose",
            "amount": actual_loss,
            "reason": reason,
            "balance": self.capital
        })
        return actual_loss

    def can_afford(self, amount: float) -> bool:
        """检查是否有足够资本"""
        return self.capital >= amount

    def get_autonomy_level(self) -> str:
        """
        根据信任资本获取自主权等级

        Returns:
            str: autonomy level
        """
        t = self.autonomy_thresholds
        if self.capital >= t["high"]:
            return "high"        # 高自主权：最低干预
        elif self.capital >= t["medium"]:
            return "medium"      # 中等自主权：适度干预
        elif self.capital >= t["low"]:
            return "low"         # 低自主权：较多干预
        else:
            return "minimal"     # 最低自主权：严格管控

    def get_summary(self) -> Dict:
        return {
            "current_capital": round(self.capital, 1),
            "max_capital": self.max_capital,
            "autonomy_level": self.get_autonomy_level(),
            "total_earned": round(self.earned_capital, 1),
            "total_spent": round(self.spent_capital, 1),
            "recent_changes": self.capital_history[-5:] if self.capital_history else []
        }

    def to_dict(self) -> Dict:
        return {
            "capital": self.capital,
            "max_capital": self.max_capital,
            "min_capital": self.min_capital,
            "autonomy_thresholds": self.autonomy_thresholds,
            "daily": self.daily,
            "capital_history": self.capital_history,
            "spent_capital": self.spent_capital,
            "earned_capital": self.earned_capital,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TrustCapital":
        obj = cls(initial_capital=data.get("capital", 50.0))
        obj.max_capital = data.get("max_capital", obj.max_capital)
        obj.min_capital = data.get("min_capital", obj.min_capital)
        if "autonomy_thresholds" in data:
            obj.autonomy_thresholds = data["autonomy_thresholds"]
        if "daily" in data:
            obj.daily = data["daily"]
        obj.capital_history = data.get("capital_history", [])
        obj.spent_capital = data.get("spent_capital", 0.0)
        obj.earned_capital = data.get("earned_capital", 0.0)
        return obj


class ManagerLearning:
    """管理者学习曲线：记录管理者对被管理者的了解程度

    核心设计理念（基于会议 2026-01-23）：
    1. 管理者通过多次循环学习，越来越了解被管理者
    2. 学习程度越高，干预越早（更高健康分就开始介入）
    3. 学习程度越高，干预越高效（同样效果需要更低等级的干预）
    4. 形成正向循环：了解→早期干预→问题小→处理快→更了解
    """

    def __init__(self):
        ml = _mgmt("manager_learning") or {}
        downgrade = ml.get("efficiency_downgrade") or {}
        self._ml_cfg = {
            "success_understanding_delta_factor": ml.get(
                "success_understanding_delta_factor", 0.02
            ),
            "fail_understanding_delta": ml.get("fail_understanding_delta", 0.005),
            "cycle_understanding_delta_factor": ml.get(
                "cycle_understanding_delta_factor", 0.05
            ),
            "efficiency_delta_low_level": ml.get("efficiency_delta_low_level", 0.02),
            "efficiency_delta_high_level": ml.get("efficiency_delta_high_level", 0.01),
            "early_intervention_base": ml.get("early_intervention_base", 50.0),
            "early_intervention_understanding_scale": ml.get(
                "early_intervention_understanding_scale", 20.0
            ),
            "efficiency_from_understanding_scale": ml.get(
                "efficiency_from_understanding_scale", 0.5
            ),
            "efficiency_downgrade": {
                "high": downgrade.get("high", 1.3),
                "medium": downgrade.get("medium", 1.1),
                "medium_min_base_level": downgrade.get("medium_min_base_level", 2),
            },
            "trend_understanding_min": ml.get("trend_understanding_min", 0.5),
            "trend_avg_delta_threshold": ml.get("trend_avg_delta_threshold", -1),
        }
        # 学习程度 (0.0-1.0)，越高表示越了解
        self.understanding_level: float = 0.0
        # 干预效率 (1.0 = 基准，>1 表示更高效)
        self.intervention_efficiency: float = 1.0
        # 早期介入阈值（健康分高于此值就开始介入）
        self.early_intervention_threshold: float = self._ml_cfg["early_intervention_base"]
        # 学习历史
        self.learning_events: List[Dict] = []
        # 成功干预次数
        self.successful_interventions: int = 0
        # 失败干预次数
        self.failed_interventions: int = 0
        # 周期计数（每次从低谷恢复算一个周期）
        self.cycle_count: int = 0

    def record_intervention(self, day: int, level: int, success: bool,
                           health_before: float, health_after: float):
        """记录一次干预并更新学习状态

        Args:
            day: 天数
            level: 干预等级
            success: 是否成功
            health_before: 干预前健康分
            health_after: 干预后健康分
        """
        cfg = self._ml_cfg
        event = {
            "day": day,
            "level": level,
            "success": success,
            "health_before": health_before,
            "health_after": health_after,
            "health_delta": health_after - health_before
        }
        self.learning_events.append(event)

        if success:
            self.successful_interventions += 1
            # 成功干预增加理解程度
            learn_delta = cfg["success_understanding_delta_factor"] * (
                1 - self.understanding_level
            )
            self.understanding_level = min(1.0, self.understanding_level + learn_delta)

            # 低级别干预成功说明更了解对方，效率提升更多
            if level <= 1:
                self.intervention_efficiency += cfg["efficiency_delta_low_level"]
            else:
                self.intervention_efficiency += cfg["efficiency_delta_high_level"]
        else:
            self.failed_interventions += 1
            # 失败干预说明还需要学习
            # 但也可以从失败中学习
            self.understanding_level += cfg["fail_understanding_delta"]

    def record_cycle_completion(self, day: int, peak_health: float, trough_health: float):
        """记录一个完整周期（从低谷到高峰再到低谷）

        Args:
            day: 当前天数
            peak_health: 周期最高健康分
            trough_health: 周期最低健康分
        """
        cfg = self._ml_cfg
        self.cycle_count += 1

        # 每完成一个周期，管理者更了解被管理者
        cycle_learning = cfg["cycle_understanding_delta_factor"] * (
            1 - self.understanding_level
        )
        self.understanding_level = min(1.0, self.understanding_level + cycle_learning)

        # 更新早期介入阈值（越了解，阈值越高）
        self.early_intervention_threshold = (
            cfg["early_intervention_base"]
            + self.understanding_level * cfg["early_intervention_understanding_scale"]
        )

        # 更新干预效率
        self.intervention_efficiency = (
            1.0 + self.understanding_level * cfg["efficiency_from_understanding_scale"]
        )

        self.learning_events.append({
            "type": "cycle_completion",
            "day": day,
            "cycle": self.cycle_count,
            "peak_health": peak_health,
            "trough_health": trough_health,
            "new_threshold": self.early_intervention_threshold,
            "new_efficiency": self.intervention_efficiency
        })

    def get_recommended_intervention_level(self, base_level: int) -> int:
        """根据学习程度调整推荐干预等级

        高效的管理者可以用更低等级的干预达到相同效果

        Args:
            base_level: 基础推荐等级

        Returns:
            int: 调整后的等级
        """
        dg = self._ml_cfg["efficiency_downgrade"]
        if self.intervention_efficiency >= dg["high"]:
            # 高效率：可以降级干预
            return max(0, base_level - 1)
        elif self.intervention_efficiency >= dg["medium"]:
            # 中等效率：偶尔降级
            if base_level >= dg["medium_min_base_level"]:
                return base_level - 1
        return base_level

    def should_intervene_early(self, current_health: float) -> Tuple[bool, str]:
        """判断是否应该提前介入

        Args:
            current_health: 当前健康分

        Returns:
            Tuple[bool, str]: (是否应该介入, 原因)
        """
        cfg = self._ml_cfg
        if current_health <= self.early_intervention_threshold:
            return True, f"健康分{current_health:.1f}已低于学习阈值{self.early_intervention_threshold:.1f}"

        # 经验丰富的管理者能识别下滑趋势
        if self.understanding_level >= cfg["trend_understanding_min"]:
            # 检查最近的健康分趋势
            recent_events = [e for e in self.learning_events if "health_after" in e][-5:]
            if len(recent_events) >= 3:
                avg_delta = sum(e.get("health_delta", 0) for e in recent_events) / len(recent_events)
                if avg_delta < cfg["trend_avg_delta_threshold"]:
                    return True, f"检测到下滑趋势(平均变化{avg_delta:+.1f})，提前介入"

        return False, ""

    def get_summary(self) -> Dict:
        """获取学习状态摘要"""
        success_rate = (
            self.successful_interventions /
            (self.successful_interventions + self.failed_interventions)
            if (self.successful_interventions + self.failed_interventions) > 0
            else 0.5
        )
        return {
            "understanding_level": round(self.understanding_level, 3),
            "intervention_efficiency": round(self.intervention_efficiency, 3),
            "early_threshold": round(self.early_intervention_threshold, 1),
            "cycle_count": self.cycle_count,
            "success_rate": round(success_rate, 3),
            "total_interventions": self.successful_interventions + self.failed_interventions
        }

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "understanding_level": self.understanding_level,
            "intervention_efficiency": self.intervention_efficiency,
            "early_intervention_threshold": self.early_intervention_threshold,
            "successful_interventions": self.successful_interventions,
            "failed_interventions": self.failed_interventions,
            "cycle_count": self.cycle_count,
            "learning_events": self.learning_events[-50:],  # 只保留最近50条
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ManagerLearning":
        obj = cls()
        obj.understanding_level = data.get("understanding_level", 0.0)
        obj.intervention_efficiency = data.get("intervention_efficiency", 1.0)
        obj.early_intervention_threshold = data.get("early_intervention_threshold", 50.0)
        obj.successful_interventions = data.get("successful_interventions", 0)
        obj.failed_interventions = data.get("failed_interventions", 0)
        obj.cycle_count = data.get("cycle_count", 0)
        obj.learning_events = data.get("learning_events", [])
        return obj


class LongTermStrategyManager(StrategyManager):
    """
    长期策略管理器：扩展 StrategyManager，添加长期机制

    新增功能：
    1. 关系阶段管理
    2. 周期性反思（周/月）
    3. 信任资本系统
    4. 习惯巩固追踪
    5. 阶段性目标调整
    6. 情绪感知的干预调整（v2新增）
    7. 过度干预保护机制（v2新增）
    """

    # 过度干预保护阈值（v2新增；实例可被 mechanism config 覆盖）
    OVER_INTERVENTION_CONFIG = {
        "emotion_warning_threshold": 3.0,    # 情绪分低于此值触发警告
        "emotion_critical_threshold": 2.5,   # 情绪分低于此值强制降级
        "high_trust_threshold": 80,          # 信任资本高于此值启用宽松模式
        "medium_trust_threshold": 50,        # 信任资本中等阈值
        "health_safe_threshold": 6,          # 健康分高于此值时可以放松干预
        "max_consecutive_high_interventions": 5,  # 连续高强度干预超过此天数触发保护
        "forced_relaxation": {
            "low_emotion_days": 3,
            "duration_days": 3,
        },
        "high_intensity_min_level": 2,
        "soften_min_health": 5,
    }

    # 关系阶段配置（基于行为识别，而非固定天数）
    PHASE_CONFIG = {
        RelationshipPhase.HONEYMOON: {
            "goal": "建立关系和规则",
            "recommended_style": "supportive",
            "intervention_modifier": 0.8,  # 干预倾向降低（给面子）
            "trust_earn_bonus": 1.5,       # 信任赚取加成
            # 识别条件：刚开始，冲突少，配合度高
            "exit_conditions": {
                "min_days": 3,              # 至少3天
                "conflict_threshold": 2,     # 出现2次以上对抗/不配合则结束蜜月
                "intervention_resistance": 0.3,  # 对干预的抵抗率超过30%
            }
        },
        RelationshipPhase.ADJUSTMENT: {
            "goal": "形成习惯，处理冲突",
            "recommended_style": "firm_but_caring",
            "intervention_modifier": 1.0,
            "trust_earn_bonus": 1.0,
            # 识别条件：冲突出现但在处理，习惯在形成
            "exit_conditions": {
                "min_days": 7,
                "habit_compliance_rate": 0.6,  # 无干预自觉率达到60%
                "consecutive_good_days": 5,     # 连续5天表现好
            }
        },
        RelationshipPhase.FATIGUE: {
            "goal": "维持动力，防止倦怠",
            "recommended_style": "adaptive",
            "intervention_modifier": 0.9,
            "trust_earn_bonus": 1.2,
            # 识别条件：出现疲态（积极性下降、偶尔违规）
            "exit_conditions": {
                "min_days": 14,
                "habit_internalization": "internalized",  # 习惯内化
                "autonomy_level": "high",                  # 高自主权
            }
        },
        RelationshipPhase.STABLE: {
            "goal": "维持自主，偶尔提醒",
            "recommended_style": "gentle",
            "intervention_modifier": 0.6,
            "trust_earn_bonus": 0.8,
            # 稳定期：习惯已形成，自主性高
            "exit_conditions": None  # 除非复发，否则保持
        },
        RelationshipPhase.RELAPSE: {
            "goal": "重建习惯，恢复信任",
            "recommended_style": "strict",
            "intervention_modifier": 1.3,
            "trust_earn_bonus": 0.5,
            # 复发期：需要重建
            "exit_conditions": {
                "consecutive_good_days": 5,  # 连续5天好转则退出复发期
            }
        },
    }

    def __init__(self, scenario="diabetes"):
        super().__init__(scenario)

        # 从 mechanism config 加载阶段 / 过度干预 / 反思参数（类常量作默认）
        self.PHASE_CONFIG = self._load_phase_config()
        self.OVER_INTERVENTION_CONFIG = self._load_over_intervention_config()
        ref = _mgmt("reflection") or {}
        self.reflection_cfg = {
            "weekly_period_days": ref.get("weekly_period_days", 7),
            "monthly_period_days": ref.get("monthly_period_days", 30),
            "weekly_high_intervention_threshold": ref.get(
                "weekly_high_intervention_threshold", 20
            ),
            "weekly_low_intervention_threshold": ref.get(
                "weekly_low_intervention_threshold", 5
            ),
        }

        # 长期状态
        self.current_phase = RelationshipPhase.HONEYMOON
        self.phase_start_day = 1
        self.relapse_count = 0           # 复发次数

        # 新增组件（内部自行读 management.trust_capital / habit / learning）
        self.trust_capital = TrustCapital()
        self.habit_tracker = HabitConsolidation()
        self.manager_learning = ManagerLearning()  # 管理者学习曲线

        # 周期性反思记录
        self.weekly_reflections = []
        self.monthly_summaries = []

        # 长期目标
        honeymoon_goal = self.PHASE_CONFIG.get(
            RelationshipPhase.HONEYMOON, {}
        ).get("goal", "建立关系和规则")
        self.current_goal = honeymoon_goal
        self.goal_progress = 0.0

        # 行为指标追踪（实例级别）
        self.behavior_indicators = {
            "conflict_count": 0,              # 冲突/对抗次数
            "total_interventions": 0,          # 总干预次数
            "intervention_resistance_count": 0, # 抵抗干预次数
            "motivation_decline_days": 0,      # 动力下降天数
            "proactive_compliance_count": 0,   # 主动遵从次数
            "forced_compliance_count": 0,      # 被迫遵从次数
            "days_in_phase": 0,                # 当前阶段已过天数
        }

        # v2新增：情绪感知和过度干预保护
        self._emotion_context = {
            "current_emotion": 5.0,           # 当前情绪分（默认中等）
            "emotion_history": [],            # 情绪历史
            "consecutive_low_emotion_days": 0, # 连续低情绪天数
        }
        self._intervention_protection = {
            "consecutive_high_intervention_days": 0,  # 连续高强度干预天数
            "over_intervention_warnings": 0,          # 过度干预警告次数
            "forced_relaxation_active": False,        # 强制放松模式是否激活
            "forced_relaxation_until_day": None,      # 强制放松到哪天
        }

    @classmethod
    def _load_phase_config(cls) -> Dict:
        """从 management.relationship_phases 加载阶段配置。"""
        raw = _mgmt("relationship_phases")
        loaded = {}
        for phase, default_cfg in cls.PHASE_CONFIG.items():
            if isinstance(raw, dict) and phase.value in raw:
                loaded[phase] = deepcopy(raw[phase.value])
            else:
                loaded[phase] = deepcopy(default_cfg)
        return loaded

    @classmethod
    def _load_over_intervention_config(cls) -> Dict:
        """从 management.over_intervention 加载过度干预保护配置。"""
        cfg = deepcopy(cls.OVER_INTERVENTION_CONFIG)
        raw = _mgmt("over_intervention")
        if not isinstance(raw, dict):
            return cfg
        for key, value in raw.items():
            if key == "forced_relaxation" and isinstance(value, dict):
                merged = deepcopy(cfg.get("forced_relaxation") or {})
                merged.update(value)
                cfg["forced_relaxation"] = merged
            else:
                cfg[key] = deepcopy(value)
        return cfg

    def set_emotion_context(self, emotion_score: float, day: int):
        """
        v2新增：设置情绪上下文，供策略调整使用

        Args:
            emotion_score: 当日情绪分 (0-10)
            day: 当前天数
        """
        self._emotion_context["current_emotion"] = emotion_score
        self._emotion_context["emotion_history"].append({
            "day": day,
            "score": emotion_score
        })

        # 更新连续低情绪天数
        warning_threshold = self.OVER_INTERVENTION_CONFIG["emotion_warning_threshold"]
        if emotion_score < warning_threshold:
            self._emotion_context["consecutive_low_emotion_days"] += 1
        else:
            self._emotion_context["consecutive_low_emotion_days"] = 0

    def _check_over_intervention_protection(self, day: int, health_score: float) -> Tuple[bool, str]:
        """
        v2新增：检查是否需要触发过度干预保护

        Returns:
            (是否需要保护, 保护原因)
        """
        config = self.OVER_INTERVENTION_CONFIG
        emotion = self._emotion_context["current_emotion"]
        trust = self.trust_capital.capital
        protection = self._intervention_protection

        # 条件1：强制放松模式激活中
        if protection["forced_relaxation_active"]:
            if protection["forced_relaxation_until_day"] and day <= protection["forced_relaxation_until_day"]:
                return True, "强制放松模式生效中"
            else:
                # 放松期结束
                protection["forced_relaxation_active"] = False
                protection["forced_relaxation_until_day"] = None

        # 条件2：情绪分极低 + 健康分尚可 = 过度干预信号
        fr = config.get("forced_relaxation") or {}
        low_emotion_days = fr.get("low_emotion_days", 3)
        duration_days = fr.get("duration_days", 3)
        if emotion < config["emotion_critical_threshold"] and health_score >= config["health_safe_threshold"]:
            protection["over_intervention_warnings"] += 1
            if self._emotion_context["consecutive_low_emotion_days"] >= low_emotion_days:
                protection["forced_relaxation_active"] = True
                protection["forced_relaxation_until_day"] = day + duration_days
                return True, (
                    f"情绪过低({emotion:.1f})且健康尚可，强制放松{duration_days}天"
                )
            return True, f"情绪过低警告({emotion:.1f})，建议减少干预"

        # 条件3：高信任资本 + 健康尚可 = 应该放松
        if trust >= config["high_trust_threshold"] and health_score >= config["health_safe_threshold"]:
            return True, f"高信任({trust:.0f}) + 健康良好({health_score})，优先观察"

        # 条件4：连续高强度干预太多天
        soften_min = config.get("soften_min_health", 5)
        if protection["consecutive_high_intervention_days"] >= config["max_consecutive_high_interventions"]:
            if health_score >= soften_min:
                return True, f"连续{protection['consecutive_high_intervention_days']}天高强度干预，需要缓和"

        return False, ""

    def _update_intervention_tracking(self, level: int, day: int):
        """v2新增：更新干预追踪"""
        min_high = self.OVER_INTERVENTION_CONFIG.get("high_intensity_min_level", 2)
        if level >= min_high:
            self._intervention_protection["consecutive_high_intervention_days"] += 1
        else:
            self._intervention_protection["consecutive_high_intervention_days"] = 0

    def get_emotion_adjusted_level(self, base_level: int, health_score: float) -> Tuple[int, str]:
        """
        v2新增：根据情绪状态调整干预等级

        核心逻辑：
        - 情绪低 + 健康好 → 过度干预，强制降级
        - 情绪低 + 健康差 → 需要干预但要温和
        - 情绪好 + 健康好 → 可以观察
        - 情绪好 + 健康差 → 正常干预

        Returns:
            (调整后等级, 调整原因)
        """
        emotion = self._emotion_context["current_emotion"]
        config = self.OVER_INTERVENTION_CONFIG

        # 情绪极低 + 健康尚可 = 过度干预，强制降到观察
        if emotion < config["emotion_critical_threshold"] and health_score >= config["health_safe_threshold"]:
            return 0, f"情绪过低({emotion:.1f})，强制观察"

        # 情绪警告 + 健康尚可 = 降级
        if emotion < config["emotion_warning_threshold"] and health_score >= config["health_safe_threshold"]:
            new_level = max(0, base_level - 1)
            if new_level != base_level:
                return new_level, f"情绪低({emotion:.1f})，降级至Level {new_level}"
            return base_level, ""

        # 情绪好 + 健康好 = 可以更宽松
        if emotion >= 4.0 and health_score >= 7:
            if base_level > 1:
                return max(1, base_level - 1), "情绪健康均佳，适度放松"

        return base_level, ""

    def update_phase(self, day: int):
        """
        更新关系阶段（基于行为识别，而非固定天数）

        关系阶段不是按天数固定的，而是从用户行为反应中动态识别：
        - 蜜月期：冲突少，配合度高，还在建立关系
        - 调整期：出现冲突但在磨合，习惯在逐步形成
        - 倦怠期：出现疲态（积极性下降、偶尔违规）
        - 稳定期：习惯已内化，自主性高
        - 复发期：旧习惯回归

        Args:
            day: 当前天数
        """
        old_phase = self.current_phase

        # 更新阶段内天数
        self.behavior_indicators["days_in_phase"] = day - self.phase_start_day + 1

        # 检查是否复发（从稳定/倦怠期跌回）
        if self._check_relapse_trigger(day):
            if old_phase != self.current_phase:
                self._on_phase_change(old_phase, self.current_phase, day)
            return

        # 复发恢复检查
        if self.current_phase == RelationshipPhase.RELAPSE:
            if self._check_relapse_recovery():
                self.current_phase = RelationshipPhase.ADJUSTMENT
                self.phase_start_day = day
                self._reset_phase_indicators()
                self._on_phase_change(old_phase, self.current_phase, day)
            return

        # 基于行为检查是否应该进入下一阶段
        phase_config = self.PHASE_CONFIG.get(self.current_phase, {})
        exit_conditions = phase_config.get("exit_conditions")

        if exit_conditions and self._check_exit_conditions(exit_conditions):
            next_phase = self._get_next_phase()
            if next_phase and next_phase != self.current_phase:
                self.current_phase = next_phase
                self.phase_start_day = day
                self.current_goal = self.PHASE_CONFIG[next_phase]["goal"]
                self._reset_phase_indicators()
                self._on_phase_change(old_phase, self.current_phase, day)

    def _check_relapse_trigger(self, day: int) -> bool:
        """
        检查是否触发复发

        复发条件：
        - 当前在稳定期或倦怠期
        - 连续3天以上表现差
        - 或者健康分急剧下降
        """
        if self.current_phase not in [RelationshipPhase.STABLE, RelationshipPhase.FATIGUE]:
            return False

        # 条件1：连续表现差
        if self.consecutive_bad_days >= 3:
            self.current_phase = RelationshipPhase.RELAPSE
            self.phase_start_day = day
            self.relapse_count += 1
            relapse_loss = self.trust_capital.daily.get("relapse_loss", 10)
            self.trust_capital.lose(relapse_loss, f"第{self.relapse_count}次复发")
            self._reset_phase_indicators()
            return True

        # 条件2：健康分急剧下降（最近3天平均比之前7天平均下降超过2分）
        if len(self.health_history) >= 10:
            recent_avg = sum(h["score"] for h in self.health_history[-3:]) / 3
            previous_avg = sum(h["score"] for h in self.health_history[-10:-3]) / 7
            if previous_avg - recent_avg >= 2.0:
                self.current_phase = RelationshipPhase.RELAPSE
                self.phase_start_day = day
                self.relapse_count += 1
                relapse_loss = self.trust_capital.daily.get("relapse_loss", 10)
                self.trust_capital.lose(
                    relapse_loss, f"第{self.relapse_count}次复发（健康急降）"
                )
                self._reset_phase_indicators()
                return True

        return False

    def _check_relapse_recovery(self) -> bool:
        """检查复发后是否恢复"""
        exit_conditions = self.PHASE_CONFIG[RelationshipPhase.RELAPSE].get("exit_conditions", {})
        required_good_days = exit_conditions.get("consecutive_good_days", 5)
        return self.consecutive_good_days >= required_good_days

    def _check_exit_conditions(self, exit_conditions: Dict) -> bool:
        """
        检查是否满足退出当前阶段的条件

        Args:
            exit_conditions: 退出条件配置

        Returns:
            bool: 是否满足退出条件
        """
        days_in_phase = self.behavior_indicators["days_in_phase"]

        # 最少天数要求
        min_days = exit_conditions.get("min_days", 0)
        if days_in_phase < min_days:
            return False

        # 根据当前阶段检查特定条件
        if self.current_phase == RelationshipPhase.HONEYMOON:
            # 蜜月期结束条件：出现足够多冲突或抵抗
            conflict_threshold = exit_conditions.get("conflict_threshold", 2)
            resistance_threshold = exit_conditions.get("intervention_resistance", 0.3)

            # 计算干预抵抗率
            total_interventions = self.behavior_indicators["total_interventions"]
            resistance_count = self.behavior_indicators["intervention_resistance_count"]
            resistance_rate = resistance_count / max(1, total_interventions)

            # 任一条件满足即结束蜜月期
            if self.behavior_indicators["conflict_count"] >= conflict_threshold:
                return True
            if resistance_rate >= resistance_threshold and total_interventions >= 5:
                return True

        elif self.current_phase == RelationshipPhase.ADJUSTMENT:
            # 调整期结束条件：习惯初步形成
            compliance_threshold = exit_conditions.get("habit_compliance_rate", 0.6)
            required_good_days = exit_conditions.get("consecutive_good_days", 5)

            # 兜底：调整期超过21天仍未满足条件，强制进入倦怠期
            max_adjustment_days = exit_conditions.get("max_days", 21)
            if days_in_phase >= max_adjustment_days:
                return True

            # 检查无干预自觉率
            compliance_rate = self.habit_tracker.no_intervention_compliance_rate
            if (compliance_rate >= compliance_threshold and
                self.consecutive_good_days >= required_good_days):
                return True

        elif self.current_phase == RelationshipPhase.FATIGUE:
            # 倦怠期结束条件：习惯内化且自主权高
            required_internalization = exit_conditions.get("habit_internalization", "internalized")
            required_autonomy = exit_conditions.get("autonomy_level", "high")

            current_habit = self.habit_tracker.get_internalization_stage()
            current_autonomy = self.trust_capital.get_autonomy_level()

            # 习惯内化等级映射
            habit_levels = {
                HabitConsolidation.STAGE_FORCED: 0,
                HabitConsolidation.STAGE_COMPLIANT: 1,
                HabitConsolidation.STAGE_INTERNALIZED: 2,
                HabitConsolidation.STAGE_AUTONOMOUS: 3,
            }
            required_level = {"forced": 0, "compliant": 1, "internalized": 2, "autonomous": 3}
            autonomy_levels = {"minimal": 0, "low": 1, "medium": 2, "high": 3}

            current_habit_level = habit_levels.get(current_habit, 0)
            required_habit_level = required_level.get(required_internalization, 2)
            current_autonomy_level = autonomy_levels.get(current_autonomy, 0)
            required_autonomy_level = autonomy_levels.get(required_autonomy, 3)

            if (current_habit_level >= required_habit_level and
                current_autonomy_level >= required_autonomy_level):
                return True

        return False

    def _get_next_phase(self) -> Optional[RelationshipPhase]:
        """获取下一个阶段"""
        phase_order = [
            RelationshipPhase.HONEYMOON,
            RelationshipPhase.ADJUSTMENT,
            RelationshipPhase.FATIGUE,
            RelationshipPhase.STABLE,
        ]
        try:
            current_index = phase_order.index(self.current_phase)
            if current_index < len(phase_order) - 1:
                return phase_order[current_index + 1]
        except ValueError:
            pass
        return None

    def _reset_phase_indicators(self):
        """重置阶段相关的行为指标"""
        self.behavior_indicators["days_in_phase"] = 0
        # 保留累计指标，只重置阶段内指标
        # conflict_count 不重置，用于长期追踪

    def update_behavior_indicators(self, day: int, intervention_count: int,
                                    complied: bool, was_proactive: bool,
                                    resisted_intervention: bool = False,
                                    had_conflict: bool = False):
        """
        更新行为指标

        Args:
            day: 当前天数
            intervention_count: 当日干预次数
            complied: 是否遵从
            was_proactive: 是否主动
            resisted_intervention: 是否抵抗干预
            had_conflict: 是否发生冲突
        """
        self.behavior_indicators["total_interventions"] += intervention_count

        if resisted_intervention:
            self.behavior_indicators["intervention_resistance_count"] += 1

        if had_conflict:
            self.behavior_indicators["conflict_count"] += 1

        if complied:
            if was_proactive:
                self.behavior_indicators["proactive_compliance_count"] += 1
            else:
                self.behavior_indicators["forced_compliance_count"] += 1

        # 检测动力下降：连续2天表现中等或差
        if self.consecutive_bad_days >= 2 or (
            len(self.health_history) >= 2 and
            all(h["score"] < self.config["health_threshold_good"]
                for h in self.health_history[-2:])
        ):
            self.behavior_indicators["motivation_decline_days"] += 1
        else:
            self.behavior_indicators["motivation_decline_days"] = 0

    def _on_phase_change(self, old_phase: RelationshipPhase, new_phase: RelationshipPhase, day: int):
        """阶段变化处理"""
        # 更新目标
        self.current_goal = self.PHASE_CONFIG[new_phase]["goal"]

        # 记录到周反思
        if self.weekly_reflections:
            self.weekly_reflections[-1]["phase_changes"] = self.weekly_reflections[-1].get("phase_changes", [])
            self.weekly_reflections[-1]["phase_changes"].append({
                "day": day,
                "from": old_phase.value,
                "to": new_phase.value
            })

    def update_state(self, day: int, health_score: float, intervention_count: int,
                     was_proactive: bool = False, emotion_positive: bool = None,
                     resisted_intervention: bool = False, had_conflict: bool = False) -> Dict:
        """
        扩展的状态更新

        Args:
            day: 当前天数
            health_score: 健康分
            intervention_count: 干预次数
            was_proactive: 是否主动遵守
            emotion_positive: 情绪是否积极
            resisted_intervention: 是否抵抗干预（对干预表示不满/不配合）
            had_conflict: 是否发生冲突（争吵、对抗）
        """
        # 调用父类更新
        result = super().update_state(day, health_score, intervention_count)

        # 判断是否遵从
        complied = health_score >= self.config["health_threshold_good"]

        # 更新行为指标（用于行为驱动的阶段识别）
        self.update_behavior_indicators(
            day=day,
            intervention_count=intervention_count,
            complied=complied,
            was_proactive=was_proactive,
            resisted_intervention=resisted_intervention,
            had_conflict=had_conflict
        )

        # 更新关系阶段（基于行为识别）
        self.update_phase(day)
        result["phase"] = self.current_phase.value
        result["phase_goal"] = self.current_goal
        result["days_in_phase"] = self.behavior_indicators["days_in_phase"]

        # 更新习惯追踪
        self.habit_tracker.record_opportunity(
            day=day,
            intervention_level=self.current_level,
            complied=complied,
            was_proactive=was_proactive,
            emotion_positive=emotion_positive
        )

        # 更新信任资本
        self._update_trust_capital(day, health_score, intervention_count, was_proactive)

        # 检查周期性反思
        self._check_periodic_reflection(day)

        # 添加新指标到结果
        result["habit_stage"] = self.habit_tracker.get_internalization_stage()
        result["trust_capital"] = self.trust_capital.capital
        result["autonomy_level"] = self.trust_capital.get_autonomy_level()
        result["behavior_indicators"] = self.behavior_indicators.copy()

        return result

    def _update_trust_capital(self, day: int, health_score: float,
                              intervention_count: int, was_proactive: bool):
        """更新信任资本"""
        threshold_good = self.config["health_threshold_good"]
        threshold_bad = self.config["health_threshold_bad"]
        phase_config = self.PHASE_CONFIG[self.current_phase]
        bonus = phase_config["trust_earn_bonus"]
        daily = self.trust_capital.daily

        if health_score >= threshold_good:
            # 表现好
            base_earn = daily["good_earn"] * bonus
            if was_proactive:
                base_earn += daily["proactive_earn"] * bonus  # 主动加成
            if intervention_count == 0:
                base_earn += daily["no_intervention_earn"] * bonus  # 无干预自觉
            self.trust_capital.earn(base_earn, f"Day {day}: 表现良好")

            # 连续天数复利
            if self.consecutive_good_days >= 3:
                streak_bonus = min(5, self.consecutive_good_days - 2) * bonus
                self.trust_capital.earn(streak_bonus, f"连续{self.consecutive_good_days}天")

        elif health_score < threshold_bad:
            # 表现差
            loss = daily["bad_loss"]
            if self.current_phase == RelationshipPhase.STABLE:
                loss = daily["stable_bad_loss"]  # 稳定期复发损失更大
            self.trust_capital.lose(loss, f"Day {day}: 表现不佳")

    def _check_periodic_reflection(self, day: int):
        """检查并触发周期性反思"""
        weekly = self.reflection_cfg["weekly_period_days"]
        monthly = self.reflection_cfg["monthly_period_days"]
        if day % weekly == 0:
            self._generate_weekly_reflection(day)

        if day % monthly == 0:
            self._generate_monthly_summary(day)

    def _generate_weekly_reflection(self, day: int) -> Dict:
        """
        生成周反思

        Returns:
            Dict: 周反思内容
        """
        weekly = self.reflection_cfg["weekly_period_days"]
        week_num = day // weekly
        start_day = (week_num - 1) * weekly + 1

        # 获取本周数据
        week_health = [h for h in self.health_history if start_day <= h["day"] <= day]
        week_interventions = [i for i in self.intervention_history if start_day <= i["day"] <= day]

        avg_health = sum(h["score"] for h in week_health) / len(week_health) if week_health else 0
        total_interventions = sum(i["count"] for i in week_interventions)
        health_trend = week_health[-1]["score"] - week_health[0]["score"] if len(week_health) >= 2 else 0

        # 识别模式
        patterns = []
        if avg_health >= self.config["health_threshold_good"]:
            patterns.append("本周整体表现良好")
        elif avg_health < self.config["health_threshold_bad"]:
            patterns.append("本周需要加强管控")

        high_th = self.reflection_cfg["weekly_high_intervention_threshold"]
        low_th = self.reflection_cfg["weekly_low_intervention_threshold"]
        if total_interventions > high_th:
            patterns.append("干预频率过高，可能引发抵触")
        elif total_interventions < low_th and avg_health >= 6:
            patterns.append("自主性增强，可考虑减少干预")

        reflection = {
            "week": week_num,
            "day_range": (start_day, day),
            "avg_health_score": round(avg_health, 2),
            "health_trend": round(health_trend, 2),
            "total_interventions": total_interventions,
            "phase": self.current_phase.value,
            "habit_stage": self.habit_tracker.get_internalization_stage(),
            "trust_capital": round(self.trust_capital.capital, 1),
            "patterns": patterns,
            "recommendation": self._get_weekly_recommendation(avg_health, total_interventions),
        }

        self.weekly_reflections.append(reflection)
        return reflection

    def _get_weekly_recommendation(self, avg_health: float, total_interventions: int) -> str:
        """获取周策略建议"""
        habit_stage = self.habit_tracker.get_internalization_stage()
        autonomy = self.trust_capital.get_autonomy_level()

        if habit_stage == HabitConsolidation.STAGE_AUTONOMOUS and autonomy == "high":
            return "可以大幅减少干预，转为定期检查模式"
        elif habit_stage == HabitConsolidation.STAGE_INTERNALIZED:
            return "习惯正在内化，保持适度支持，逐步增加自主权"
        elif habit_stage == HabitConsolidation.STAGE_COMPLIANT:
            if total_interventions > 15:
                return "虽然顺从但未内化，考虑增加正向激励减少强制"
            return "继续当前策略，关注内化进展"
        else:
            if avg_health < 5:
                return "需要加强管控，同时关注情绪变化避免对抗"
            return "初期阶段，保持坚定但避免过度干预"

    def _generate_monthly_summary(self, day: int) -> Dict:
        """生成月总结"""
        monthly = self.reflection_cfg["monthly_period_days"]
        month_num = day // monthly
        start_day = (month_num - 1) * monthly + 1

        # 获取本月数据
        month_health = [h for h in self.health_history if start_day <= h["day"] <= day]
        month_weeks = [w for w in self.weekly_reflections if start_day <= w["day_range"][0] <= day]

        avg_health = sum(h["score"] for h in month_health) / len(month_health) if month_health else 0

        # 月度趋势分析
        if len(month_weeks) >= 2:
            health_trajectory = month_weeks[-1]["avg_health_score"] - month_weeks[0]["avg_health_score"]
        else:
            health_trajectory = 0

        summary = {
            "month": month_num,
            "day_range": (start_day, day),
            "avg_health_score": round(avg_health, 2),
            "health_trajectory": round(health_trajectory, 2),
            "phase_at_start": month_weeks[0]["phase"] if month_weeks else self.current_phase.value,
            "phase_at_end": self.current_phase.value,
            "habit_progress": self.habit_tracker.get_summary(),
            "trust_capital_change": self._calculate_monthly_trust_change(start_day, day),
            "key_events": self._get_key_events(start_day, day),
            "next_month_focus": self._get_next_month_focus(),
        }

        self.monthly_summaries.append(summary)
        return summary

    def _calculate_monthly_trust_change(self, start_day: int, end_day: int) -> float:
        """计算月度信任资本变化"""
        relevant_history = [
            h for h in self.trust_capital.capital_history
            if "day" in str(h.get("reason", "")) and
               any(str(d) in h.get("reason", "") for d in range(start_day, end_day + 1))
        ]
        total_change = sum(
            h["amount"] if h["type"] == "earn" else -h["amount"]
            for h in relevant_history
        )
        return round(total_change, 1)

    def _get_key_events(self, start_day: int, end_day: int) -> List[str]:
        """获取关键事件"""
        events = []

        # 检查复发
        if self.relapse_count > 0:
            events.append(f"发生{self.relapse_count}次复发")

        # 检查阶段变化
        for reflection in self.weekly_reflections:
            if reflection["day_range"][0] >= start_day and reflection["day_range"][1] <= end_day:
                if "phase_changes" in reflection:
                    for change in reflection["phase_changes"]:
                        events.append(f"Day {change['day']}: 阶段从{change['from']}变为{change['to']}")

        return events

    def _get_next_month_focus(self) -> str:
        """获取下月重点"""
        phase = self.current_phase
        habit_stage = self.habit_tracker.get_internalization_stage()

        if phase == RelationshipPhase.HONEYMOON:
            return "继续建立信任关系，避免过早严格管控"
        elif phase == RelationshipPhase.ADJUSTMENT:
            return "处理冲突，保持规则一致性，关注情绪变化"
        elif phase == RelationshipPhase.FATIGUE:
            return "防止倦怠，增加正向激励，考虑适度放松"
        elif phase == RelationshipPhase.STABLE:
            return "维持成果，减少干预频率，鼓励自主管理"
        elif phase == RelationshipPhase.RELAPSE:
            return "重建习惯，恢复信任，避免惩罚性干预"
        else:
            return "根据实际情况调整策略"

    def get_recommended_level(self, day: int, health_score: float = None) -> Tuple[int, str]:
        """
        扩展的推荐等级（考虑长期因素）

        v2改进：
        - 信任资本高时强制降级（不再是概率性的）
        - 情绪低时触发保护机制
        - 过度干预保护

        Args:
            day: 当前天数
            health_score: 当前健康分（可选，用于更精确的判断）

        Returns:
            tuple: (推荐等级, 调整原因)
        """
        # 获取基础推荐
        base_level, base_reason = super().get_recommended_level(day)

        # 如果没有提供健康分，从历史中获取
        if health_score is None and self.health_history:
            health_score = self.health_history[-1].get("score", 5)
        elif health_score is None:
            health_score = 5  # 默认中等

        config = self.OVER_INTERVENTION_CONFIG

        # ========== v2核心改进：过度干预保护 ==========

        # 步骤1：检查是否需要强制保护
        need_protection, protection_reason = self._check_over_intervention_protection(day, health_score)
        if need_protection and health_score >= config["health_safe_threshold"]:
            # 健康分尚可时，强制降级到观察或劝说
            old_level = base_level
            base_level = min(base_level, 1)  # 最多Level 1
            if base_level != old_level:
                base_reason = f"{protection_reason}，从Level {old_level}降至Level {base_level}"
            else:
                base_reason += f"（{protection_reason}）"

        # 步骤2：情绪感知调整
        emotion_level, emotion_reason = self.get_emotion_adjusted_level(base_level, health_score)
        if emotion_level != base_level:
            base_level = emotion_level
            base_reason = emotion_reason

        # ========== 原有逻辑（微调） ==========

        # 根据阶段调整
        phase_config = self.PHASE_CONFIG[self.current_phase]
        intervention_modifier = phase_config["intervention_modifier"]

        # 根据信任资本调整（v2改进：强制降级而非概率性）
        trust = self.trust_capital.capital
        autonomy = self.trust_capital.get_autonomy_level()

        if trust >= config["high_trust_threshold"] and base_level > 0:
            # 高信任资本：强制降级（不再是30%概率）
            soften_min = config.get("soften_min_health", 5)
            if health_score >= config["health_safe_threshold"]:
                # 健康分尚可，强制降到观察
                base_level = 0
                base_reason = f"高信任({trust:.0f}) + 健康良好({health_score})，观察即可"
            elif health_score >= soften_min:
                # 健康分中等，最多劝说
                base_level = min(base_level, 1)
                base_reason += f"（高信任{trust:.0f}，温和提醒）"
            # 健康分差时不限制

        elif trust >= config["medium_trust_threshold"] and base_level > 1:
            # 中等信任资本：限制高强度干预
            if health_score >= config["health_safe_threshold"]:
                base_level = min(base_level, 1)
                base_reason += f"（中等信任{trust:.0f}，避免高强度干预）"

        elif autonomy == "minimal" and base_level < self.max_intervention_level:
            # 最低自主权，考虑加强干预（保持原逻辑）
            if health_score < 4:  # 只在健康分很差时才升级
                base_level = min(self.max_intervention_level, base_level + 1)
                base_reason += "（低信任资本，加强管控）"

        # 根据习惯内化阶段调整
        habit_stage = self.habit_tracker.get_internalization_stage()
        if habit_stage == HabitConsolidation.STAGE_AUTONOMOUS and base_level > 1:
            base_level = max(1, base_level - 1)
            base_reason += "（习惯已自主）"
        elif habit_stage == HabitConsolidation.STAGE_INTERNALIZED and base_level > 2:
            base_level = max(2, base_level - 1)
            base_reason += "（习惯正在内化）"

        # 【管理者学习曲线】根据学习程度调整干预策略
        # 学习程度越高，干预越早、越高效
        learning = self.manager_learning

        # 1. 检查是否应该提前介入（累积健康分模式下health_score范围更大）
        should_early, early_reason = learning.should_intervene_early(health_score)
        if should_early and base_level == 0:
            # 经验丰富的管理者会提前介入
            base_level = 1
            base_reason = f"[学习曲线]{early_reason}"

        # 2. 根据学习效率调整干预等级（更高效的管理者可以用更低等级达到效果）
        adjusted_level = learning.get_recommended_intervention_level(base_level)
        if adjusted_level < base_level:
            base_reason += f"（学习效率{learning.intervention_efficiency:.2f}，降级干预）"
            base_level = adjusted_level

        # 更新干预追踪
        self._update_intervention_tracking(base_level, day)

        self.current_level = base_level
        return base_level, base_reason

    def get_status_summary(self) -> Dict:
        """扩展的状态摘要"""
        base_summary = super().get_status_summary()
        base_summary.update({
            "phase": self.current_phase.value,
            "phase_goal": self.current_goal,
            "days_in_phase": self.behavior_indicators["days_in_phase"],
            "relapse_count": self.relapse_count,
            "trust_capital": self.trust_capital.get_summary(),
            "habit_consolidation": self.habit_tracker.get_summary(),
            "manager_learning": self.manager_learning.get_summary(),  # 管理者学习曲线
            "behavior_indicators": self.behavior_indicators.copy(),
            "weekly_reflections_count": len(self.weekly_reflections),
            "monthly_summaries_count": len(self.monthly_summaries),
            # v2新增
            "emotion_context": {
                "current_emotion": self._emotion_context["current_emotion"],
                "consecutive_low_emotion_days": self._emotion_context["consecutive_low_emotion_days"],
            },
            "intervention_protection": {
                "consecutive_high_intervention_days": self._intervention_protection["consecutive_high_intervention_days"],
                "over_intervention_warnings": self._intervention_protection["over_intervention_warnings"],
                "forced_relaxation_active": self._intervention_protection["forced_relaxation_active"],
            },
        })
        return base_summary

    def to_dict(self) -> Dict:
        """扩展的序列化"""
        base_dict = super().to_dict()
        base_dict.update({
            "current_phase": self.current_phase.value,
            "phase_start_day": self.phase_start_day,
            "relapse_count": self.relapse_count,
            "trust_capital": self.trust_capital.to_dict(),
            "habit_tracker": self.habit_tracker.to_dict(),
            "manager_learning": self.manager_learning.to_dict(),  # 管理者学习曲线
            "weekly_reflections": self.weekly_reflections,
            "monthly_summaries": self.monthly_summaries,
            "current_goal": self.current_goal,
            "goal_progress": self.goal_progress,
            "behavior_indicators": self.behavior_indicators,
            # v2新增
            "emotion_context": self._emotion_context,
            "intervention_protection": self._intervention_protection,
        })
        return base_dict

    @classmethod
    def from_dict(cls, data: Dict) -> "LongTermStrategyManager":
        """扩展的反序列化"""
        manager = cls(scenario=data.get("scenario", "diabetes"))

        # 恢复基类状态
        manager.current_level = data.get("current_level", 0)
        manager.consecutive_good_days = data.get("consecutive_good_days", 0)
        manager.consecutive_bad_days = data.get("consecutive_bad_days", 0)
        manager.trust_level = data.get("trust_level", 0.5)
        manager.health_history = data.get("health_history", [])
        manager.intervention_history = data.get("intervention_history", [])
        manager.relaxation_day = data.get("relaxation_day")
        manager.is_relaxed = data.get("is_relaxed", False)

        # 恢复长期状态
        phase_value = data.get("current_phase", "honeymoon")
        manager.current_phase = RelationshipPhase(phase_value)
        manager.phase_start_day = data.get("phase_start_day", 1)
        manager.relapse_count = data.get("relapse_count", 0)
        manager.current_goal = data.get("current_goal", "")
        manager.goal_progress = data.get("goal_progress", 0.0)

        # 恢复行为指标
        if "behavior_indicators" in data:
            manager.behavior_indicators = data["behavior_indicators"]

        # 恢复组件
        if "trust_capital" in data:
            manager.trust_capital = TrustCapital.from_dict(data["trust_capital"])
        if "habit_tracker" in data:
            manager.habit_tracker = HabitConsolidation.from_dict(data["habit_tracker"])
        if "manager_learning" in data:
            manager.manager_learning = ManagerLearning.from_dict(data["manager_learning"])

        manager.weekly_reflections = data.get("weekly_reflections", [])
        manager.monthly_summaries = data.get("monthly_summaries", [])

        # v2新增：恢复情绪和干预保护状态
        if "emotion_context" in data:
            manager._emotion_context = data["emotion_context"]
        if "intervention_protection" in data:
            manager._intervention_protection = data["intervention_protection"]

        return manager
