"""generative_agents.scorer_nonlinear

非线性健康分计算系统

核心改进（相比 scorer.py 的线性系统）：
1. 阈值效应：不同健康区间有不同的敏感度和恢复速度
2. 边际递减：恢复速度随距离目标的距离而变化
3. 累积效应：连续违规产生复合影响
4. 随机波动：模拟日常生理/心理变异
5. 个体差异：同等级内参数有分布范围

详细设计文档：../HEALTH_SCORING_NONLINEAR_ANALYSIS.md
"""

import random
import math
from enum import Enum
from typing import Dict, Tuple, Optional, List


class SelfDisciplineLevel(Enum):
    """自律程度枚举"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HealthZone(Enum):
    """健康区间枚举"""
    EMERGENCY = "emergency"  # 0-29: 紧急
    DANGER = "danger"        # 30-49: 危险
    WARNING = "warning"      # 50-69: 预警
    NORMAL = "normal"        # 70-89: 正常
    SAFE = "safe"            # 90-100: 安全


class NonlinearHealthScorer:
    """非线性健康分计算器

    核心设计理念：
    - 模拟真实人类健康指标的非线性动态
    - 基于生理学原理的阈值效应、累积损伤、边际递减
    - 引入随机性以增加真实感和实验多样性
    """

    # 健康区间定义（进一步平衡 - 第3次调整）
    HEALTH_ZONES = {
        HealthZone.EMERGENCY: {
            "range": (0, 29),
            "sensitivity": 1.4,      # 从1.6降至1.4
            "recovery_mult": 0.4,    # 从0.3提升至0.4
            "description": "紧急：需要医疗干预，恢复极其缓慢"
        },
        HealthZone.DANGER: {
            "range": (30, 49),
            "sensitivity": 1.2,      # 从1.3降至1.2
            "recovery_mult": 0.7,    # 从0.6提升至0.7
            "description": "危险：接近生理极限，微小违规可能崩溃"
        },
        HealthZone.WARNING: {
            "range": (50, 69),
            "sensitivity": 1.1,      # 从1.15降至1.1
            "recovery_mult": 0.9,    # 从0.85提升至0.9
            "description": "预警：缓冲减少，敏感度上升"
        },
        HealthZone.NORMAL: {
            "range": (70, 89),
            "sensitivity": 1.0,
            "recovery_mult": 1.0,
            "description": "正常：基线状态"
        },
        HealthZone.SAFE: {
            "range": (90, 100),
            "sensitivity": 0.9,      # 从0.85提升至0.9（进一步减少差异）
            "recovery_mult": 1.1,    # 从1.15降至1.1
            "description": "安全：生理缓冲充足，小违规影响小"
        },
    }

    # 自律程度参数（第4次调整：平衡 + 底线保护）
    DISCIPLINE_PARAMS = {
        SelfDisciplineLevel.HIGH: {
            # 违规惩罚范围（每次违规的基础扣分）
            "violation_penalty_range": (7, 10),
            # 自然恢复范围（每天无违规时的基础恢复分）
            "natural_recovery_range": (4.5, 6.5),
            # 累积系数（连续违规的复合影响系数）
            "cumulative_factor": 0.04,  # 从0.05降至0.04
            # 日常波动标准差（生理/心理变异）
            "noise_sigma": 0.3,
            # 韧性（抗压能力）
            "resilience": 1.3,
            # 平台期持续天数（用于潮汐周期）
            "plateau_duration": 14,
            "description": "高自律：波动小、恢复快、抗压强"
        },
        SelfDisciplineLevel.MEDIUM: {
            "violation_penalty_range": (4.0, 5.0),  # 从(3.5,4.5)提升至(4.0,5.0)
            "natural_recovery_range": (3.5, 4.5),   # 从(3.0,4.0)提升至(3.5,4.5)
            "cumulative_factor": 0.03,  # 从0.02提升至0.03
            "noise_sigma": 0.5,
            "resilience": 1.2,
            "plateau_duration": 7,
            "description": "中自律：中等波动和恢复"
        },
        SelfDisciplineLevel.LOW: {
            "violation_penalty_range": (3.5, 4.5),  # 从(2.5,3.5)提升至(3.5,4.5)，略高于恢复
            "natural_recovery_range": (2.5, 3.5),   # 保持不变
            "cumulative_factor": 0.01,  # 从0.0提升至0.01（添加轻微累积）
            "noise_sigma": 0.6,         # 从0.5提升至0.6（增加波动）
            "resilience": 1.3,          # 从1.5降至1.3
            "plateau_duration": 3,
            "description": "低自律：波动大、恢复慢、抗压弱"
        },
    }

    # 警戒线
    WARNING_LINE = 30

    def __init__(
        self,
        initial_score: int = 75,
        discipline_level: str = "medium",
        scenario: str = "diabetes",
        random_seed: Optional[int] = None
    ):
        """初始化非线性健康分计算器

        Args:
            initial_score: 初始健康分（60/75/90）
            discipline_level: 自律程度（high/medium/low）
            scenario: 场景类型（diabetes/weight-loss/phone-addiction）
            random_seed: 随机种子（用于可复现性，默认None为完全随机）
        """
        self.initial_score = initial_score
        self.current_score = float(initial_score)
        self.scenario = scenario

        if random_seed is not None:
            random.seed(random_seed)

        # 解析自律程度
        if isinstance(discipline_level, SelfDisciplineLevel):
            self.discipline_level = discipline_level
        else:
            self.discipline_level = SelfDisciplineLevel(discipline_level.lower())

        self.params = self.DISCIPLINE_PARAMS[self.discipline_level]

        # 追踪状态
        self.day_count = 0
        self.consecutive_good_days = 0
        self.consecutive_bad_days = 0
        self.consecutive_violations = 0  # 新增：连续违规次数（用于累积效应）
        self.plateau_days = 0
        self.in_plateau = False
        self.history: List[Dict] = []

        # 潮汐周期追踪
        self.last_trough_day = 0
        self.last_peak_day = 0
        self.trough_count = 0

    def calculate_daily_change(
        self,
        agent_data: Dict,
        had_violation: bool,
        intervention_count: int,
        intervention_success: bool,
        unblocked_violation_count: int = 0
    ) -> Tuple[float, Dict]:
        """计算每日健康分变化（非线性版本）

        Args:
            agent_data: 当日行为数据
            had_violation: 是否有违规行为
            intervention_count: 干预次数
            intervention_success: 干预是否成功
            unblocked_violation_count: 未被阻止的违规次数

        Returns:
            Tuple[float, Dict]: (健康分变化值, 详细分解)
        """
        self.day_count += 1
        change = 0.0
        breakdown = {
            "day": self.day_count,
            "initial_score": self.current_score,
            "components": {},
            "zone": self._get_current_zone().name,
        }

        # 实际违规次数
        actual_violations = max(1, unblocked_violation_count) if had_violation else 0

        # 1. 违规惩罚（非线性）
        if had_violation:
            if intervention_success and unblocked_violation_count == 0:
                # 干预成功阻止 - 小幅惩罚
                penalty = self._calculate_blocked_violation_penalty()
                change += penalty
                breakdown["components"]["blocked_violation"] = penalty
                self.consecutive_bad_days = 0
                self.consecutive_violations = 0
            else:
                # 违规发生 - 非线性惩罚
                penalty = self._calculate_violation_penalty(
                    violation_count=actual_violations,
                    current_score=self.current_score
                )
                change += penalty
                breakdown["components"]["violation"] = penalty
                breakdown["components"]["violation_count"] = actual_violations

                # 更新连续违规计数
                self.consecutive_violations += actual_violations
                self.consecutive_bad_days += 1
                self.consecutive_good_days = 0

                # 记录累积效应
                if self.consecutive_violations > 1:
                    cumulative_mult = 1.0 + (self.consecutive_violations - 1) * self.params["cumulative_factor"]
                    breakdown["components"]["cumulative_multiplier"] = cumulative_mult

                # 平台期跌落
                if self.in_plateau:
                    self.in_plateau = False
                    self.plateau_days = 0
                    self.trough_count += 1
                    self.last_trough_day = self.day_count
                    breakdown["components"]["plateau_fall"] = True
        else:
            # 无违规行为
            self.consecutive_good_days += 1
            self.consecutive_bad_days = 0
            self.consecutive_violations = 0  # 重置累积违规计数

            # 2. 自然恢复（非线性）
            if self.current_score < self.initial_score:
                recovery = self._calculate_natural_recovery(
                    current_score=self.current_score,
                    initial_score=self.initial_score,
                    consecutive_good_days=self.consecutive_good_days
                )
                change += recovery
                breakdown["components"]["natural_recovery"] = recovery
                breakdown["components"]["recovery_components"] = {
                    "distance_factor": self._calculate_distance_factor(
                        self.current_score, self.initial_score
                    ),
                    "zone_mult": self._get_zone_recovery_mult(self.current_score),
                    "habit_bonus": self._calculate_habit_bonus(self.consecutive_good_days)
                }

            # 3. 遵从奖励（只在低于初始分时生效）
            if intervention_count > 0 and intervention_success:
                if self.current_score < self.initial_score:
                    bonus = self._calculate_compliance_bonus(
                        self.current_score,
                        self.initial_score,
                        change
                    )
                    if bonus > 0:
                        change += bonus
                        breakdown["components"]["compliance_bonus"] = bonus

        # 4. 平台期检测
        if self.consecutive_good_days >= self.params["plateau_duration"]:
            if not self.in_plateau:
                self.in_plateau = True
                self.last_peak_day = self.day_count
                breakdown["components"]["entered_plateau"] = True
            self.plateau_days += 1

        # 5. 持续恶化的加速下滑（非线性）
        if self.consecutive_bad_days >= 3:
            acceleration = self._calculate_decline_acceleration(
                self.consecutive_bad_days,
                self.current_score
            )
            change += acceleration
            breakdown["components"]["decline_acceleration"] = acceleration

        # 6. 添加日常波动（随机性）
        noise = self._add_daily_noise(change)
        if abs(noise) > 0.01:  # 只在噪声显著时记录
            change += noise
            breakdown["components"]["daily_noise"] = noise

        # 7. 更新当前分数
        new_score = self.current_score + change

        # 确保分数在合理范围内
        new_score = max(0, min(self.initial_score, new_score))

        # 记录
        breakdown["change"] = change
        breakdown["new_score"] = new_score
        breakdown["below_warning"] = new_score < self.WARNING_LINE
        breakdown["consecutive_good_days"] = self.consecutive_good_days
        breakdown["consecutive_bad_days"] = self.consecutive_bad_days
        breakdown["consecutive_violations"] = self.consecutive_violations
        breakdown["in_plateau"] = self.in_plateau
        breakdown["plateau_days"] = self.plateau_days

        self.history.append(breakdown)
        self.current_score = new_score

        return change, breakdown

    def _get_current_zone(self) -> HealthZone:
        """获取当前分数所在的健康区间"""
        for zone, info in self.HEALTH_ZONES.items():
            min_val, max_val = info["range"]
            if min_val <= self.current_score <= max_val:
                return zone
        return HealthZone.NORMAL

    def _get_zone_sensitivity(self, score: float) -> float:
        """获取指定分数所在区间的违规敏感度"""
        for zone, info in self.HEALTH_ZONES.items():
            min_val, max_val = info["range"]
            if min_val <= score <= max_val:
                return info["sensitivity"]
        return 1.0

    def _get_zone_recovery_mult(self, score: float) -> float:
        """获取指定分数所在区间的恢复速度倍数"""
        for zone, info in self.HEALTH_ZONES.items():
            min_val, max_val = info["range"]
            if min_val <= score <= max_val:
                return info["recovery_mult"]
        return 1.0

    def _calculate_violation_penalty(
        self,
        violation_count: int,
        current_score: float
    ) -> float:
        """计算非线性违规惩罚（含底线保护）

        公式：
        penalty = -base_penalty * cumulative_mult * zone_sensitivity * resilience_mult * floor_protection * violation_count

        where:
            base_penalty ~ Uniform(min, max)  # 个体差异
            cumulative_mult = 1.0 + (consecutive_violations - 1) * cumulative_factor
            zone_sensitivity = 健康区间敏感度
            resilience_mult = 1.0 +/- N(0, 0.1) * resilience  # 抗压能力波动
            floor_protection = 底线保护系数（健康分越低，惩罚越小）
        """
        params = self.params

        # 1. 随机基础惩罚（个体差异）
        penalty_min, penalty_max = params["violation_penalty_range"]
        base_penalty = random.uniform(penalty_min, penalty_max)

        # 2. 累积系数（连续违规的复合影响）
        if self.consecutive_violations > 0:
            cumulative_mult = 1.0 + self.consecutive_violations * params["cumulative_factor"]
        else:
            cumulative_mult = 1.0

        # 3. 阈值敏感度（健康区间影响）
        zone_sensitivity = self._get_zone_sensitivity(current_score)

        # 4. 韧性修正（抗压能力的个体波动）
        resilience_noise = random.gauss(0, 0.1) * params["resilience"]
        resilience_mult = 1.0 - resilience_noise
        resilience_mult = max(0.5, min(1.5, resilience_mult))

        # 5. 【新增】底线保护：健康分越低，惩罚越小（防止雪崩）
        if current_score < 15:
            floor_protection = 0.1  # 惩罚降至10%（"濒死状态"）
        elif current_score < 30:
            floor_protection = 0.3  # 惩罚降至30%（"危险状态"）
        elif current_score < 50:
            floor_protection = 0.6  # 惩罚降至60%（"警戒状态"）
        else:
            floor_protection = 1.0  # 正常惩罚

        # 6. 综合计算
        total_penalty = (
            base_penalty
            * cumulative_mult
            * zone_sensitivity
            * resilience_mult
            * floor_protection
            * violation_count
        )

        return -total_penalty

    def _calculate_blocked_violation_penalty(self) -> float:
        """计算被阻止的违规的小幅惩罚"""
        penalty_min, penalty_max = self.params["violation_penalty_range"]
        base_penalty = random.uniform(penalty_min, penalty_max)
        return -base_penalty * 0.3

    def _calculate_natural_recovery(
        self,
        current_score: float,
        initial_score: float,
        consecutive_good_days: int
    ) -> float:
        """计算非线性自然恢复（含底线增强）

        公式：
        recovery = base_recovery * distance_factor * zone_mult * habit_mult * floor_boost

        where:
            base_recovery ~ Uniform(min, max)
            distance_factor = sqrt(1 - current / initial)  # 边际递减
            zone_mult = 健康区间恢复速度倍数
            habit_mult = 1.0 + min(0.3, consecutive_good_days * 0.02)
            floor_boost = 底线增强系数（健康分越低，恢复越强）
        """
        params = self.params

        # 1. 随机基础恢复（个体差异）
        recovery_min, recovery_max = params["natural_recovery_range"]
        base_recovery = random.uniform(recovery_min, recovery_max)

        # 2. 边际递减系数（距离目标越远，恢复潜力越大）
        distance_factor = self._calculate_distance_factor(current_score, initial_score)

        # 3. 阈值恢复速度
        zone_recovery_mult = self._get_zone_recovery_mult(current_score)

        # 4. 习惯养成加成
        habit_mult = 1.0 + self._calculate_habit_bonus(consecutive_good_days)

        # 5. 【新增】底线增强：健康分越低，恢复越强（模拟医疗干预）
        if current_score < 15:
            floor_boost = 5.0  # 5倍恢复（"重症监护"）
        elif current_score < 30:
            floor_boost = 3.0  # 3倍恢复（"住院治疗"）
        elif current_score < 50:
            floor_boost = 1.5  # 1.5倍恢复（"门诊治疗"）
        else:
            floor_boost = 1.0  # 正常恢复

        # 6. 综合计算
        recovery = (
            base_recovery
            * distance_factor
            * zone_recovery_mult
            * habit_mult
            * floor_boost
        )

        # 确保不超过初始分
        recovery = max(0, min(recovery, initial_score - current_score))

        return recovery

    def _calculate_distance_factor(self, current: float, target: float) -> float:
        """计算边际递减因子

        使用平方根函数：越接近目标，改善越困难
        """
        if current >= target:
            return 0.0

        distance_ratio = 1.0 - (current / target)
        return math.sqrt(distance_ratio)

    def _calculate_habit_bonus(self, consecutive_good_days: int) -> float:
        """计算习惯养成加成（最多+30%）"""
        return min(0.3, consecutive_good_days * 0.02)

    def _calculate_compliance_bonus(
        self,
        current_score: float,
        initial_score: float,
        current_change: float
    ) -> float:
        """计算遵从奖励

        小幅奖励，且不超过初始分
        """
        bonus_range = (1.0, 2.0)
        bonus = random.uniform(*bonus_range)

        # 确保不超过初始分
        max_bonus = initial_score - current_score - current_change
        bonus = max(0, min(bonus, max_bonus))

        return bonus

    def _calculate_decline_acceleration(
        self,
        consecutive_bad_days: int,
        current_score: float
    ) -> float:
        """计算持续恶化的加速下滑

        连续违规时间越长，下滑越快（非线性）
        """
        # 基础加速（指数增长）
        base_acceleration = -0.5 * (consecutive_bad_days - 2) ** 1.3

        # 区间修正（越接近警戒线，加速越快）
        zone_sensitivity = self._get_zone_sensitivity(current_score)

        return base_acceleration * zone_sensitivity

    def _add_daily_noise(self, change: float) -> float:
        """添加日常生理/心理波动

        模拟真实健康指标的随机变异
        """
        noise = random.gauss(0, self.params["noise_sigma"])

        # 限制波动幅度（防止噪声主导信号）
        # 调整为±0.8分，避免噪声过大
        max_noise = 0.8
        noise = max(-max_noise, min(max_noise, noise))

        return noise

    def get_health_status(self) -> str:
        """获取当前健康状态描述"""
        zone = self._get_current_zone()
        if zone == HealthZone.SAFE:
            return "excellent"
        elif zone == HealthZone.NORMAL:
            return "good"
        elif zone == HealthZone.WARNING:
            return "fair"
        elif zone == HealthZone.DANGER:
            return "poor"
        else:  # EMERGENCY
            return "critical"

    def get_tide_phase(self) -> str:
        """获取当前潮汐周期阶段"""
        if self.in_plateau:
            return "plateau"
        elif self.consecutive_bad_days >= 3:
            return "declining"
        elif self.consecutive_good_days >= 2:
            return "recovering"
        else:
            return "fluctuating"

    def get_summary(self) -> Dict:
        """获取健康分摘要"""
        return {
            "initial_score": self.initial_score,
            "current_score": round(self.current_score, 1),
            "discipline_level": self.discipline_level.value,
            "day_count": self.day_count,
            "status": self.get_health_status(),
            "zone": self._get_current_zone().name,
            "tide_phase": self.get_tide_phase(),
            "consecutive_good_days": self.consecutive_good_days,
            "consecutive_bad_days": self.consecutive_bad_days,
            "consecutive_violations": self.consecutive_violations,
            "in_plateau": self.in_plateau,
            "plateau_days": self.plateau_days,
            "trough_count": self.trough_count,
            "below_warning": self.current_score < self.WARNING_LINE,
            "distance_to_warning": round(self.current_score - self.WARNING_LINE, 1),
        }

    def to_dict(self) -> Dict:
        """序列化为字典（用于checkpoint）"""
        return {
            "initial_score": self.initial_score,
            "current_score": self.current_score,
            "discipline_level": self.discipline_level.value,
            "scenario": self.scenario,
            "day_count": self.day_count,
            "consecutive_good_days": self.consecutive_good_days,
            "consecutive_bad_days": self.consecutive_bad_days,
            "consecutive_violations": self.consecutive_violations,
            "plateau_days": self.plateau_days,
            "in_plateau": self.in_plateau,
            "last_trough_day": self.last_trough_day,
            "last_peak_day": self.last_peak_day,
            "trough_count": self.trough_count,
            "history": self.history[-30:],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "NonlinearHealthScorer":
        """从字典恢复"""
        scorer = cls(
            initial_score=data.get("initial_score", 75),
            discipline_level=data.get("discipline_level", "medium"),
            scenario=data.get("scenario", "diabetes"),
        )
        scorer.current_score = data.get("current_score", scorer.initial_score)
        scorer.day_count = data.get("day_count", 0)
        scorer.consecutive_good_days = data.get("consecutive_good_days", 0)
        scorer.consecutive_bad_days = data.get("consecutive_bad_days", 0)
        scorer.consecutive_violations = data.get("consecutive_violations", 0)
        scorer.plateau_days = data.get("plateau_days", 0)
        scorer.in_plateau = data.get("in_plateau", False)
        scorer.last_trough_day = data.get("last_trough_day", 0)
        scorer.last_peak_day = data.get("last_peak_day", 0)
        scorer.trough_count = data.get("trough_count", 0)
        scorer.history = data.get("history", [])
        return scorer
