"""generative_agents.scorer_nonlinear

非线性健康分计算系统 + 满意度/行为分项/综合评估（Scorer）

健康分核心（NonlinearHealthScorer）：
1. 阈值效应：不同健康区间有不同的敏感度
2. 累积效应：连续违规产生复合影响
3. 随机波动：模拟日常生理/心理变异
4. 个体差异：同等级内参数有分布范围

满意度 / 行为扣分 / 综合评估：见本文件末尾 `Scorer` 类
（已从 scorer.py 迁入；后续只在本文件修改）。
原"心情分"已并入 `calculate_satisfaction_score`，不再独立输出。

详细设计文档：../HEALTH_SCORING_NONLINEAR_ANALYSIS.md
"""

import datetime
import random
import math
from copy import deepcopy
from enum import Enum
from typing import Any, Dict, Tuple, Optional, List

from modules.mechanism_config import get_path


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


_DEFAULT_FLOOR_PROTECTION = {
    "lt_30": 0.25,
    "lt_40": 0.4,
    "lt_50": 0.6,
    "lt_60": 0.8,
    "lt_70": 0.9,
    "else": 1.0,
}


def _resolve_nonlinear_discipline_params(
    level: SelfDisciplineLevel,
    hardcoded: Dict[str, Any],
) -> Dict[str, Any]:
    """合并 nonlinear 自律参数。"""
    cfg = get_path(
        f"simulation.health.nonlinear.discipline_params.{level.value}",
        default=None,
    )
    if not isinstance(cfg, dict):
        return dict(hardcoded)
    merged = dict(hardcoded)
    for key, value in cfg.items():
        if key in ("natural_recovery", "natural_recovery_range"):
            continue
        if key == "violation_penalty_range" and isinstance(value, list) and len(value) == 2:
            merged[key] = (value[0], value[1])
        else:
            merged[key] = value
    return merged


def _resolve_health_zones(hardcoded: Dict) -> Dict:
    """从 config 加载 HEALTH_ZONES，key 转为 HealthZone，range 转为 tuple。"""
    cfg = get_path("simulation.health.nonlinear.health_zones", default=None)
    if not isinstance(cfg, dict):
        return deepcopy(hardcoded)
    out = deepcopy(hardcoded)
    for name, info in cfg.items():
        try:
            zone = HealthZone(name)
        except ValueError:
            continue
        if not isinstance(info, dict):
            continue
        base = dict(out.get(zone, {}))
        merged = {**base, **info}
        rng = merged.get("range")
        if isinstance(rng, list) and len(rng) == 2:
            merged["range"] = (rng[0], rng[1])
        out[zone] = merged
    return out


class NonlinearHealthScorer:
    """非线性健康分计算器

    核心设计理念：
    - 模拟真实人类健康指标的非线性动态
    - 基于生理学原理的阈值效应、累积损伤、边际递减
    - 引入随机性以增加真实感和实验多样性
    """

    # 健康区间定义（平衡模式 - 降低敏感度差异）
    HEALTH_ZONES = {
        HealthZone.EMERGENCY: {
            "range": (0, 29),
            "sensitivity": 1.2,      # 降至1.2（原1.4）
            "recovery_mult": 0.5,    # 提升至0.5（原0.4）
            "description": "紧急：需要医疗干预，恢复极其缓慢"
        },
        HealthZone.DANGER: {
            "range": (30, 49),
            "sensitivity": 1.1,     # 降至1.1（原1.2）
            "recovery_mult": 0.8,   # 提升至0.8（原0.7）
            "description": "危险：接近生理极限，微小违规可能崩溃"
        },
        HealthZone.WARNING: {
            "range": (50, 69),
            "sensitivity": 1.05,    # 降至1.05（原1.1）
            "recovery_mult": 0.95,  # 调整至0.95（原0.9）
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
            "sensitivity": 0.95,    # 提升至0.95（原0.9）
            "recovery_mult": 1.05,   # 调整至1.05（原1.1）
            "description": "安全：生理缓冲充足，小违规影响小"
        },
    }

    # 自律程度参数（统一扣分范围，不同等级通过韧性、波动、平台期区分）
    DISCIPLINE_PARAMS = {
        SelfDisciplineLevel.HIGH: {
            # 违规惩罚范围（每次违规的基础扣分）
            "violation_penalty_range": (0.5, 1.5),      # 统一扣分范围
            # 累积系数（连续违规的复合影响系数）
            "cumulative_factor": 0.005,  # 极低累积效应
            # 日常波动标准差（生理/心理变异）
            "noise_sigma": 0.15,         # 波动较小
            # 韧性（抗压能力）
            "resilience": 2.5,           # 强抗压能力
            # 平台期持续天数（用于潮汐周期）
            "plateau_duration": 14,
            "description": "高自律：波动极小、净恢复为正、抗压强"
        },
        SelfDisciplineLevel.MEDIUM: {
            "violation_penalty_range": (0.5, 1.5),      # 统一扣分范围
            "cumulative_factor": 0.005,
            "noise_sigma": 0.3,
            "resilience": 1.4,
            "plateau_duration": 7,
            "description": "中自律：中等波动、净扣分基本为0"
        },
        SelfDisciplineLevel.LOW: {
            "violation_penalty_range": (0.5, 1.5),      # 统一扣分范围
            "cumulative_factor": 0.005,  # 极低累积效应（每多一天只+0.5%）
            "noise_sigma": 0.4,
            "resilience": 1.2,
            "plateau_duration": 3,
            "description": "低自律：波动较大、净扣分为负"
        },
    }

    # 警戒线
    WARNING_LINE = 30
    # 软地板（分数低于20时限制下降）
    SOFT_FLOOR = 20

    def __init__(
        self,
        initial_score: int = 75,
        discipline_level: str = "medium",
        scenario: str = "diabetes",
        random_seed: Optional[int] = None,
        floor_score: float = 0.0  # 分数底线，默认为0
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
        self.floor_score = floor_score  # 存储底线分数
        # 惩罚强度缩放（1.0 表示完全强度，被阻止的不扣分）
        self.penalty_scale = 1.0

        if random_seed is not None:
            random.seed(random_seed)

        # 解析自律程度
        if isinstance(discipline_level, SelfDisciplineLevel):
            self.discipline_level = discipline_level
        else:
            self.discipline_level = SelfDisciplineLevel(discipline_level.lower())

        # 从 mechanism config 读取可外置参数（硬编码为 default）
        self.WARNING_LINE = get_path(
            "simulation.health.nonlinear.warning_line",
            default=get_path(
                "simulation.health.warning_line",
                default=NonlinearHealthScorer.WARNING_LINE,
            ),
        )
        self.HEALTH_ZONES = _resolve_health_zones(self.HEALTH_ZONES)
        self._discipline_params_table = {
            level: _resolve_nonlinear_discipline_params(level, params)
            for level, params in self.DISCIPLINE_PARAMS.items()
        }
        self.params = self._discipline_params_table[self.discipline_level]
        self.max_penalty = get_path(
            "simulation.health.nonlinear.max_penalty",
            default=-10.0,
        )
        self.improvement_threshold = get_path(
            "simulation.health.nonlinear.improvement_threshold",
            default=10,
        )
        floor_cfg = get_path(
            "simulation.health.nonlinear.floor_protection",
            default=None,
        )
        self.floor_protection = {
            **_DEFAULT_FLOOR_PROTECTION,
            **(floor_cfg if isinstance(floor_cfg, dict) else {}),
        }

        # 追踪状态
        self.day_count = 0
        self.consecutive_good_days = 0
        self.consecutive_bad_days = 0
        self.consecutive_violations = 0  # 新增：连续违规次数（用于累积效应）
        self.plateau_days = 0
        self.in_plateau = False
        self.history: List[Dict] = []

        # 【新增】自律提升机制：追踪连续表现良好
        self.discipline_improvement_days = 0  # 连续表现良好天数
        # 记录原始自律等级（兼容传入 Enum）
        if isinstance(discipline_level, SelfDisciplineLevel):
            self.original_discipline = discipline_level
        else:
            self.original_discipline = SelfDisciplineLevel(discipline_level.lower())
        self.discipline_improved = False  # 是否已经提升过

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
                # 暴露底线保护系数以便诊断
                breakdown["components"]["floor_protection"] = getattr(self, '_last_floor_protection', None)
                breakdown["components"]["violation_count"] = actual_violations

                # 更新连续违规计数
                self.consecutive_violations += actual_violations
                self.consecutive_bad_days += 1
                self.consecutive_good_days = 0

                # 【新增】违规时重置自律提升进度
                self._check_discipline_improvement(had_violation=True)

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

            # 【新增】检查自律提升（连续表现好可提升自律等级）
            discipline_upgraded = self._check_discipline_improvement(had_violation=False)
            if discipline_upgraded:
                breakdown["components"]["discipline_improved"] = {
                    "from": self.original_discipline.value,
                    "to": self.discipline_level.value,
                    "consecutive_good_days": self.discipline_improvement_days
                }

            # 2. 遵从奖励（只在低于初始分时生效）
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
                        # 暴露遵从奖励规模因子以便诊断
                        breakdown["components"]["compliance_scale"] = getattr(self, '_last_compliance_scale', 1.0)

        # 3. 平台期检测
        if self.consecutive_good_days >= self.params["plateau_duration"]:
            if not self.in_plateau:
                self.in_plateau = True
                self.last_peak_day = self.day_count
                breakdown["components"]["entered_plateau"] = True
            self.plateau_days += 1

        # 4. 持续恶化的加速下滑（非线性）
        if self.consecutive_bad_days >= 3:
            # 【改进】计算预估的新分数，如果将低于35则禁用加速下滑
            projected_score = self.current_score + change
            acceleration = self._calculate_decline_acceleration(
                self.consecutive_bad_days,
                projected_score  # 使用预估分数判断
            )
            change += acceleration
            breakdown["components"]["decline_acceleration"] = acceleration

        # 5. 【新增】限制每日最大扣分（防止单日扣分过多）
        max_penalty = self.max_penalty  # 来自 mechanism config / 默认 -10
        if change < max_penalty:
            original_change = change
            change = max_penalty
            breakdown["components"]["daily_penalty_cap"] = {
                "original": original_change,
                "capped_to": max_penalty,
                "reduction": original_change - max_penalty
            }

        # 6. 添加日常波动（随机性）
        noise = self._add_daily_noise(change)
        if abs(noise) > 0.01:  # 只在噪声显著时记录
            change += noise
            breakdown["components"]["daily_noise"] = noise

        # 7. 更新当前分数
        new_score = self.current_score + change

        # 限制分数在 [max(floor_score, SOFT_FLOOR), 100] 之间，确保不会降到低于软地板20
        new_score = max(max(self.floor_score, self.SOFT_FLOOR), min(100, new_score))

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

        # 【已移除底线保护】低分时惩罚全额执行
        floor_protection = 1.0

        # 6. 综合计算
        total_penalty = (
            base_penalty
            * cumulative_mult
            * zone_sensitivity
            * resilience_mult
            * floor_protection
            * violation_count
        )

        # 记录用于诊断/分解的底线保护系数，便于上层把它放到 breakdown 中
        self._last_floor_protection = floor_protection

        # 应用全局惩罚缩放（用于调低整体扣分强度）
        total_penalty *= getattr(self, 'penalty_scale', 1.0)

        return -total_penalty

    def _calculate_blocked_violation_penalty(self) -> float:
        """计算被阻止的违规——不扣分（因为被阻止了）"""
        return 0.0

    def _check_discipline_improvement(self, had_violation: bool) -> bool:
        """【新增】检查并应用自律提升机制

        规则：
        - LOW自律：连续14天无违规 -> 提升至MEDIUM
        - MEDIUM自律：连续14天无违规 -> 提升至HIGH

        提升后会获得更强的恢复能力和更弱的惩罚承受能力

        Returns:
            True if discipline was upgraded
        """
        if had_violation:
            # 有违规，重置计数器
            self.discipline_improvement_days = 0
            return False

        # 无违规，累积表现良好天数
        self.discipline_improvement_days += 1

        # 检查是否可以提升自律等级（阈值可外置）
        improvement_threshold = self.improvement_threshold

        old_level = self.discipline_level
        new_level = old_level

        if old_level == SelfDisciplineLevel.LOW and self.discipline_improvement_days >= improvement_threshold:
            new_level = SelfDisciplineLevel.MEDIUM
        elif old_level == SelfDisciplineLevel.MEDIUM and self.discipline_improvement_days >= improvement_threshold:
            new_level = SelfDisciplineLevel.HIGH

        if new_level != old_level:
            self.discipline_level = new_level
            self.params = self._discipline_params_table[new_level]
            self.discipline_improved = True
            # 重置计数器，因为刚升级需要重新累积
            self.discipline_improvement_days = 0
            return True

        return False

    def _calculate_compliance_bonus(
        self,
        current_score: float,
        initial_score: float,
        current_change: float
    ) -> float:
        """计算遵从奖励

        小幅奖励，且不超过初始分
        """
        # 根据当前分数的严重程度放大遵从奖励：分数越低，遵从的边际价值越高
        severity = max(0.0, (initial_score - current_score) / float(initial_score))
        scale = 1.0 + min(1.0, severity * 1.0)  # 最多 2x

        bonus_range = (1.0, 2.0)
        bonus = random.uniform(*bonus_range) * scale

        # 确保不超过初始分
        max_bonus = initial_score - current_score - current_change
        bonus = max(0, min(bonus, max_bonus))

        # 记录上一次遵从奖励规模（便于诊断）
        self._last_compliance_scale = scale

        return bonus

    def _calculate_decline_acceleration(
        self,
        consecutive_bad_days: int,
        projected_score: float
    ) -> float:
        """计算持续恶化的加速下滑

        连续违规时间越长，下滑越快（非线性）

        注意：当健康分接近或低于警戒线时，禁用加速下滑机制，
        因为底线保护/恢复机制已经足够强
        """
        # 【底线】当预估分数将低于20时，禁用加速下滑（更温和处理临界状态）
        if projected_score < 20:
            return 0

        # 基础加速（指数增长，但更温和）
        base_acceleration = -0.12 * (consecutive_bad_days - 2) ** 1.3

        # 区间修正
        zone_sensitivity = self._get_zone_sensitivity(projected_score)

        acceleration = base_acceleration * zone_sensitivity

        # 限制加速度最大值
        acceleration = max(-2.5, min(0, acceleration))

        # 缩减加速下滑强度以匹配整体惩罚缩放
        acceleration *= getattr(self, 'penalty_scale', 1.0)

        return acceleration

    def _add_daily_noise(self, change: float) -> float:
        """添加日常生理/心理波动

        模拟真实健康指标的随机变异
        当分数低于20时，限制负向波动以保护底线
        """
        noise = random.gauss(0, self.params["noise_sigma"])

        # 限制波动幅度（防止噪声主导信号）
        max_noise = 1.2
        noise = max(-max_noise, min(max_noise, noise))

        # 【改进】当分数低于20时，限制负向波动但不完全禁止
        if self.current_score < 20:
            # 在低分区，主要允许正向噪声，但仍允许小幅负向波动
            noise = max(-0.8, min(noise, 0.8))  # 允许-0.8到+0.8的波动

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
            # 【新增】自律提升机制
            "discipline_improvement_days": getattr(self, 'discipline_improvement_days', 0),
            "original_discipline": getattr(self, 'original_discipline', None).value if getattr(self, 'original_discipline', None) else None,
            "discipline_improved": getattr(self, 'discipline_improved', False),
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
        # 【新增】自律提升机制
        scorer.discipline_improvement_days = data.get("discipline_improvement_days", 0)
        orig_disc = data.get("original_discipline")
        if orig_disc:
            scorer.original_discipline = SelfDisciplineLevel(orig_disc)
        scorer.discipline_improved = data.get("discipline_improved", False)
        return scorer


# =============================================================================
# 满意度 / 行为分项 / 综合评估（从 scorer.py 迁入）
# 后续只在本文件维护这些计算逻辑；线性 CumulativeHealthScorer 不再作为主路径。
# 原"心情分"已合并到满意度，不再单独输出。
# =============================================================================


def _deep_merge_dict(base: Dict, override: Optional[Dict]) -> Dict:
    """浅层 dict 合并：override 覆盖 base 的同名键；嵌套 dict 递归合并。"""
    if not override:
        return deepcopy(base)
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


class InitialHealthScore(Enum):
    """初始健康分枚举"""
    HIGH = 90
    MEDIUM = 75
    LOW = 60


class Scorer:
    """健康管理评分系统（基于医学循证标准）"""

    # ==================== 基础评分常量 ====================

    # 食物种类评分（睡眠、减肥、糖尿病）
    FOOD_TYPE_SCORES = {
        "high_sugar_fat": {"sleep": -1, "weight": -5, "diabetes": -4},  # 高糖高脂
        "low_sugar_fat": {"sleep": +1, "weight": +3, "diabetes": +2},   # 低糖低脂
        "high_gi": {"sleep": 0, "weight": -2, "diabetes": -5},          # 高GI
        "low_gi": {"sleep": 0, "weight": +2, "diabetes": +5},           # 低GI
        "none": {"sleep": 0, "weight": 0, "diabetes": 0},               # 未进食
        "processed": {"sleep": -1, "weight": -5, "diabetes": -4},       # 加工食品（等同高糖高脂）
        "healthy": {"sleep": 0, "weight": +2, "diabetes": +3},          # 健康食品
    }

    # 进食量评分
    FOOD_AMOUNT_SCORES = {
        "excessive": {"sleep": -2, "weight": -5, "diabetes": -4},  # 较多（超热量目标）
        "moderate": {"sleep": +1, "weight": +3, "diabetes": +3},   # 适中（符合目标）
        "insufficient": {"sleep": 0, "weight": +1, "diabetes": -1}, # 较少（低于基础需求）
        "none": {"sleep": 0, "weight": 0, "diabetes": 0},          # 未进食
    }

    # 玩手机结束时间评分（基于就寝时间推算）
    PHONE_END_TIME_SCORES = {
        "before_22": {"sleep": +5, "weight": +2, "diabetes": +2},   # 22:00前
        "22_to_24": {"sleep": +2, "weight": +1, "diabetes": +1},    # 22:00-24:00
        "0_to_1": {"sleep": -3, "weight": -1, "diabetes": -1},      # 0:00-1:00
        "after_1": {"sleep": -5, "weight": -2, "diabetes": -2},     # 1:00以后
    }

    # 玩手机种类评分（主要影响睡眠）
    PHONE_ACTIVITY_SCORES = {
        "work": {"sleep": -2, "weight": 0, "diabetes": 0},       # 办公
        "gaming": {"sleep": -5, "weight": 0, "diabetes": 0},     # 游戏
        "video": {"sleep": -3, "weight": 0, "diabetes": 0},      # 刷视频
        "social": {"sleep": -2, "weight": 0, "diabetes": 0},     # 社交/聊天
        "none": {"sleep": 0, "weight": 0, "diabetes": 0},        # 未使用
    }

    # ==================== mechanism config 解析 ====================

    @staticmethod
    def _behavior_table(section: str, default: Dict) -> Dict:
        cfg = get_path(f"simulation.behavior_scores.{section}", default=None)
        return _deep_merge_dict(default, cfg if isinstance(cfg, dict) else None)

    @staticmethod
    def _food_type_scores() -> Dict:
        return Scorer._behavior_table("food_type", Scorer.FOOD_TYPE_SCORES)

    @staticmethod
    def _food_amount_scores() -> Dict:
        return Scorer._behavior_table("food_amount", Scorer.FOOD_AMOUNT_SCORES)

    @staticmethod
    def _phone_end_time_scores() -> Dict:
        return Scorer._behavior_table("phone_end_time", Scorer.PHONE_END_TIME_SCORES)

    @staticmethod
    def _phone_activity_scores() -> Dict:
        return Scorer._behavior_table("phone_activity", Scorer.PHONE_ACTIVITY_SCORES)

    @staticmethod
    def _intervention_level_weights() -> Dict:
        cfg = get_path(
            "simulation.satisfaction.intervention_level_weights",
            default=None,
        )
        if not isinstance(cfg, dict):
            return Scorer.INTERVENTION_LEVEL_WEIGHTS
        out = dict(Scorer.INTERVENTION_LEVEL_WEIGHTS)
        for key, value in cfg.items():
            out[int(key)] = value
        return out

    @staticmethod
    def _intervention_reasonability() -> Dict:
        cfg = get_path(
            "simulation.satisfaction.intervention_reasonability",
            default=None,
        )
        return _deep_merge_dict(
            Scorer.INTERVENTION_REASONABILITY,
            cfg if isinstance(cfg, dict) else None,
        )

    @staticmethod
    def _discipline_phase_modifiers() -> Dict:
        cfg = get_path(
            "simulation.satisfaction.discipline_phase_modifiers",
            default=None,
        )
        return _deep_merge_dict(
            Scorer.DISCIPLINE_PHASE_MODIFIERS,
            cfg if isinstance(cfg, dict) else None,
        )

    @staticmethod
    def _composite_weights() -> Dict:
        cfg = get_path("simulation.composite.weights", default=None)
        return _deep_merge_dict(
            Scorer.COMPOSITE_WEIGHTS,
            cfg if isinstance(cfg, dict) else None,
        )

    @staticmethod
    def _effectiveness_thresholds() -> Dict:
        cfg = get_path("simulation.composite.effectiveness_thresholds", default=None)
        return _deep_merge_dict(
            Scorer.EFFECTIVENESS_THRESHOLDS,
            cfg if isinstance(cfg, dict) else None,
        )

    @staticmethod
    def _rating_thresholds() -> Dict:
        defaults = {"A": 8.0, "B": 6.5, "C": 5.0, "D": 3.5}
        cfg = get_path("simulation.composite.rating_thresholds", default=None)
        return _deep_merge_dict(defaults, cfg if isinstance(cfg, dict) else None)

    # ==================== 公式计算方法 ====================

    @staticmethod
    def calc_meal_sleep_interval_score(interval_minutes, scenario="diabetes"):
        """
        计算进餐到睡觉间隔时间的评分

        公式：(t-180)*coefficient
        - 睡眠: (t-180)*0.03
        - 减肥: (t-180)*0.02
        - 糖尿病: (t-180)*0.04

        Args:
            interval_minutes: 进餐结束到就寝的间隔（分钟）
            scenario: 场景类型

        Returns:
            float: 评分影响值
        """
        default_coefficients = {
            "sleep": 0.03,
            "weight": 0.02,
            "diabetes": 0.04
        }
        baseline = get_path(
            "simulation.behavior_scores.meal_sleep_interval.baseline_minutes",
            default=180,
        )
        coefficients = get_path(
            "simulation.behavior_scores.meal_sleep_interval.coefficients",
            default=None,
        )
        if not isinstance(coefficients, dict):
            coefficients = default_coefficients
        else:
            coefficients = {**default_coefficients, **coefficients}
        coef = coefficients.get(scenario, 0.03)
        return (interval_minutes - baseline) * coef

    @staticmethod
    def calc_continuous_phone_score(duration_minutes):
        """
        计算单次连续使用手机时长的睡眠影响评分

        公式：(30-t)*0.15
        超过30分钟开始对睡眠产生负面影响

        Args:
            duration_minutes: 连续使用时长（分钟）

        Returns:
            float: 睡眠评分影响值
        """
        baseline = get_path(
            "simulation.behavior_scores.continuous_phone.baseline_minutes",
            default=30,
        )
        coef = get_path(
            "simulation.behavior_scores.continuous_phone.coefficient",
            default=0.15,
        )
        return (baseline - duration_minutes) * coef

    @staticmethod
    def calc_total_phone_score(total_minutes, scenario="sleep"):
        """
        计算夜间使用手机总时长的评分

        公式：
        - 睡眠: (120-t)*0.1
        - 糖尿病: (120-t)*0.05 (仅当t>120时计算)

        Args:
            total_minutes: 每日使用总时长（分钟）
            scenario: 场景类型

        Returns:
            float: 评分影响值
        """
        if scenario == "sleep":
            return (120 - total_minutes) * 0.1
        elif scenario == "diabetes":
            if total_minutes > 120:
                return (120 - total_minutes) * 0.05
            return 0
        return 0

    @staticmethod
    def get_phone_end_time_category(end_time_str):
        """
        根据结束玩手机时间获取类别

        Args:
            end_time_str: 时间字符串 (HH:MM格式)

        Returns:
            str: 时间类别
        """
        if not end_time_str:
            return "none"

        try:
            if isinstance(end_time_str, str):
                time_obj = datetime.datetime.strptime(end_time_str, "%H:%M")
            else:
                time_obj = end_time_str

            hour = time_obj.hour
            if hour < 22 and hour >= 6:
                return "before_22"
            elif hour >= 22 or hour == 0:
                return "22_to_24"
            elif hour == 1:
                return "0_to_1"
            else:  # hour >= 2 and hour < 6
                return "after_1"
        except:
            return "22_to_24"

    # ==================== 场景评分计算 ====================

    @staticmethod
    def calculate_diabetes_health_score(agent_data):
        """
        计算糖尿病场景健康分

        基础分：5分
        评分维度（基于评分表）：
        1. 进餐食物种类：-5 ~ +5
        2. 进食量：-4 ~ +3
        3. 进餐-睡觉间隔：公式 (t-180)*0.04
        4. 玩手机结束时间：-2 ~ +2
        5. 夜间手机使用总时长：公式 (120-t)*0.05 (t>120)

        最终分数范围：0-10
        """
        base_score = 5.0

        # 1. 进餐食物种类
        food_type = agent_data.get("night_food_type", "none")
        food_score = Scorer._food_type_scores().get(food_type, {}).get("diabetes", 0)
        base_score += food_score

        # 2. 进食量
        food_amount = agent_data.get("food_amount", "none")
        amount_score = Scorer._food_amount_scores().get(food_amount, {}).get("diabetes", 0)
        base_score += amount_score

        # 3. 进餐-睡觉间隔
        last_eating_time = agent_data.get("last_eating_time")
        sleep_time = agent_data.get("sleep_time")
        if last_eating_time and sleep_time:
            interval = Scorer._calc_time_interval(last_eating_time, sleep_time)
            interval_score = Scorer.calc_meal_sleep_interval_score(interval, "diabetes")
            base_score += interval_score

        # 4. 玩手机结束时间
        phone_end_time = agent_data.get("phone_end_time")
        if phone_end_time:
            time_category = Scorer.get_phone_end_time_category(phone_end_time)
            time_score = Scorer._phone_end_time_scores().get(time_category, {}).get("diabetes", 0)
            base_score += time_score

        # 5. 夜间手机使用总时长
        phone_duration = agent_data.get("phone_duration_before_sleep", 0)
        if phone_duration > 120:
            phone_score = Scorer.calc_total_phone_score(phone_duration, "diabetes")
            base_score += phone_score

        # 偷吃行为额外惩罚
        snacking_count = agent_data.get("snacking_count", 0)
        if snacking_count > 0:
            snacking_type = agent_data.get("snacking_type", "processed")
            snack_score = Scorer._food_type_scores().get(snacking_type, {}).get("diabetes", -2)
            base_score += snack_score * min(snacking_count, 3)  # 最多计算3次

        # 限制分数范围在0-10
        return max(0, min(10, round(base_score)))

    @staticmethod
    def _calc_time_interval(start_time, end_time):
        """
        计算两个时间之间的间隔（分钟）

        Args:
            start_time: 开始时间（字符串HH:MM或datetime）
            end_time: 结束时间（字符串HH:MM或datetime）

        Returns:
            int: 间隔分钟数
        """
        if isinstance(start_time, str):
            start_time = datetime.datetime.strptime(start_time, "%H:%M")
        if isinstance(end_time, str):
            end_time = datetime.datetime.strptime(end_time, "%H:%M")

        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute

        diff = end_minutes - start_minutes
        if diff < 0:
            diff += 24 * 60  # 跨日处理

        return diff

    @staticmethod
    def calculate_weight_loss_health_score(agent_data):
        """
        计算减肥场景健康分

        基础分：5分
        评分维度（基于评分表）：
        1. 进餐食物种类：-5 ~ +3
        2. 进食量：-5 ~ +3
        3. 进餐-睡觉间隔：公式 (t-180)*0.02
        4. 玩手机结束时间：-2 ~ +2

        最终分数范围：0-10
        """
        base_score = 5.0

        # 1. 进餐食物种类
        food_type = agent_data.get("night_food_type", "none")
        food_score = Scorer._food_type_scores().get(food_type, {}).get("weight", 0)
        base_score += food_score

        # 2. 进食量
        food_amount = agent_data.get("food_amount", "none")
        amount_score = Scorer._food_amount_scores().get(food_amount, {}).get("weight", 0)
        base_score += amount_score

        # 3. 进餐-睡觉间隔
        last_eating_time = agent_data.get("last_eating_time")
        sleep_time = agent_data.get("sleep_time")
        if last_eating_time and sleep_time:
            interval = Scorer._calc_time_interval(last_eating_time, sleep_time)
            interval_score = Scorer.calc_meal_sleep_interval_score(interval, "weight")
            base_score += interval_score

        # 4. 玩手机结束时间
        phone_end_time = agent_data.get("phone_end_time")
        if phone_end_time:
            time_category = Scorer.get_phone_end_time_category(phone_end_time)
            time_score = Scorer._phone_end_time_scores().get(time_category, {}).get("weight", 0)
            base_score += time_score

        # 偷吃行为额外惩罚
        snacking_count = agent_data.get("snacking_count", 0)
        if snacking_count > 0:
            snacking_type = agent_data.get("snacking_type", "processed")
            snack_score = Scorer._food_type_scores().get(snacking_type, {}).get("weight", -3)
            base_score += snack_score * min(snacking_count, 3)  # 最多计算3次

        # 限制分数范围在0-10
        return max(0, min(10, round(base_score)))

    @staticmethod
    def calculate_phone_addiction_health_score(agent_data):
        """
        计算手机依赖场景健康分（主要评估睡眠影响）

        基础分：5分
        评分维度（基于评分表）：
        1. 玩手机结束时间：-5 ~ +5
        2. 玩手机种类：-5 ~ 0
        3. 连续使用时长：公式 (30-t)*0.15
        4. 夜间使用总时长：公式 (120-t)*0.1

        最终分数范围：0-10
        """
        base_score = 5.0

        # 1. 玩手机结束时间
        phone_end_time = agent_data.get("phone_end_time")
        if phone_end_time:
            time_category = Scorer.get_phone_end_time_category(phone_end_time)
            time_score = Scorer._phone_end_time_scores().get(time_category, {}).get("sleep", 0)
            base_score += time_score

        # 2. 玩手机种类
        phone_activity = agent_data.get("phone_activity", "none")
        activity_score = Scorer._phone_activity_scores().get(phone_activity, {}).get("sleep", 0)
        base_score += activity_score

        # 3. 连续使用时长
        continuous_duration = agent_data.get("continuous_phone_duration", 0)
        if continuous_duration > 0:
            continuous_score = Scorer.calc_continuous_phone_score(continuous_duration)
            base_score += continuous_score

        # 4. 夜间使用总时长
        total_duration = agent_data.get("phone_duration_before_sleep", 0)
        if total_duration > 0:
            total_score = Scorer.calc_total_phone_score(total_duration, "sleep")
            base_score += total_score

        # 限制分数范围在0-10
        return max(0, min(10, round(base_score)))

    @staticmethod
    def calculate_sleep_health_score(agent_data):
        """
        计算睡眠健康分（综合评分）

        基础分：5分
        评分维度（基于评分表）：
        1. 进餐食物种类对睡眠影响：-1 ~ +1
        2. 进食量对睡眠影响：-2 ~ +1
        3. 玩手机结束时间：-5 ~ +5
        4. 玩手机种类：-5 ~ 0
        5. 进餐-睡觉间隔：公式 (t-180)*0.03
        6. 连续使用时长：公式 (30-t)*0.15
        7. 夜间使用总时长：公式 (120-t)*0.1

        最终分数范围：0-10
        """
        base_score = 5.0

        # 1. 进餐食物种类
        food_type = agent_data.get("night_food_type", "none")
        food_score = Scorer._food_type_scores().get(food_type, {}).get("sleep", 0)
        base_score += food_score

        # 2. 进食量
        food_amount = agent_data.get("food_amount", "none")
        amount_score = Scorer._food_amount_scores().get(food_amount, {}).get("sleep", 0)
        base_score += amount_score

        # 3. 玩手机结束时间
        phone_end_time = agent_data.get("phone_end_time")
        if phone_end_time:
            time_category = Scorer.get_phone_end_time_category(phone_end_time)
            time_score = Scorer._phone_end_time_scores().get(time_category, {}).get("sleep", 0)
            base_score += time_score

        # 4. 玩手机种类
        phone_activity = agent_data.get("phone_activity", "none")
        activity_score = Scorer._phone_activity_scores().get(phone_activity, {}).get("sleep", 0)
        base_score += activity_score

        # 5. 进餐-睡觉间隔
        last_eating_time = agent_data.get("last_eating_time")
        sleep_time = agent_data.get("sleep_time")
        if last_eating_time and sleep_time:
            interval = Scorer._calc_time_interval(last_eating_time, sleep_time)
            interval_score = Scorer.calc_meal_sleep_interval_score(interval, "sleep")
            base_score += interval_score

        # 6. 连续使用时长
        continuous_duration = agent_data.get("continuous_phone_duration", 0)
        if continuous_duration > 0:
            continuous_score = Scorer.calc_continuous_phone_score(continuous_duration)
            base_score += continuous_score

        # 7. 夜间使用总时长
        total_duration = agent_data.get("phone_duration_before_sleep", 0)
        if total_duration > 0:
            total_score = Scorer.calc_total_phone_score(total_duration, "sleep")
            base_score += total_score

        # 限制分数范围在0-10
        return max(0, min(10, round(base_score)))

    @staticmethod
    def calculate_health_score(agent_data, scenario="diabetes"):
        """
        根据场景计算健康分

        Args:
            agent_data: 包含当日数据的字典
            scenario: 场景类型（"diabetes", "weight_loss", "weight-loss",
                      "phone_addiction", "phone-addiction", "home-diabetes",
                      "home-phone-addiction", "sleep"）

        Returns:
            int: 健康分（0-10）
        """
        # 标准化场景名称
        scenario = scenario.lower().replace("-", "_")

        if scenario in ["diabetes", "home_diabetes"]:
            return Scorer.calculate_diabetes_health_score(agent_data)
        elif scenario in ["weight_loss", "weight"]:
            return Scorer.calculate_weight_loss_health_score(agent_data)
        elif scenario in ["phone_addiction", "home_phone_addiction"]:
            return Scorer.calculate_phone_addiction_health_score(agent_data)
        elif scenario == "sleep":
            return Scorer.calculate_sleep_health_score(agent_data)
        else:
            # 默认使用糖尿病标准
            return Scorer.calculate_diabetes_health_score(agent_data)

    @staticmethod
    def get_health_grade(score):
        """
        根据健康分获取等级

        Args:
            score: 健康分（0-10）

        Returns:
            tuple: (等级, 描述)
        """
        if score >= 9:
            return "优秀 (Excellent)", "夜间行为高度符合健康推荐，整体趋势在'目标范围'内"
        elif score >= 7:
            return "良好 (Good)", "多数行为良好，整体趋势接近'目标范围'，但在1-2个维度有改进空间"
        elif score >= 5:
            return "一般 (Fair)", "部分行为偏离推荐，需要主动调整"
        else:
            return "需改进 (Needs Improvement)", "多项行为显著不健康，亟需针对性干预"

    # ==================== 满意度评分常量 ====================

    # 干预等级权重（等级越高，对满意度负面影响越大）
    INTERVENTION_LEVEL_WEIGHTS = {
        0: 0.0,    # 观察 - 无感知影响
        1: -0.3,   # 劝说 - 轻微负面
        2: -0.6,   # 移除物品 - 中等负面
        3: -1.0,   # 锁定空间 - 强烈负面
    }

    # 干预合理性修正（合理干预减少负面影响）
    INTERVENTION_REASONABILITY = {
        "reasonable": 0.5,      # 合理干预（阻止了违规行为）
        "preventive": 0.3,      # 预防性干预（有潜在风险）
        "unnecessary": -0.5,    # 不必要干预（无违规倾向）
    }

    # 自律阶段修正
    DISCIPLINE_PHASE_MODIFIERS = {
        "adjustment": {"base": 0, "intervention_sensitivity": 0.8},     # 磨合期(1-7天): 对干预容忍度较高
        "formation": {"base": +0.5, "intervention_sensitivity": 1.0},  # 习惯养成期(8-21天): 逐渐形成习惯
        "fatigue": {"base": -0.5, "intervention_sensitivity": 1.3},    # 倦怠期(22+天): 容易厌倦，对干预更敏感
    }

    @staticmethod
    def get_discipline_phase(day):
        """
        根据天数获取自律阶段

        Args:
            day: 当前天数

        Returns:
            str: 阶段名称 (adjustment/formation/fatigue)
        """
        phases = Scorer._discipline_phase_modifiers()
        adj_max = phases.get("adjustment", {}).get("max_day", 7)
        form_max = phases.get("formation", {}).get("max_day", 21)
        if adj_max is None:
            adj_max = 7
        if day <= adj_max:
            return "adjustment"
        if form_max is None or day <= form_max:
            return "formation"
        return "fatigue"

    @staticmethod
    def calc_intervention_frequency_modifier(intervention_count, max_penalty=-2.0):
        """
        计算干预频率修正

        公式: -0.5 * min(intervention_count, 4)

        Args:
            intervention_count: 当日干预次数
            max_penalty: 最大惩罚值

        Returns:
            float: 频率修正值 (-2.0 ~ 0)
        """
        per = get_path(
            "simulation.satisfaction.frequency_penalty.per_intervention",
            default=-0.5,
        )
        max_p = get_path(
            "simulation.satisfaction.frequency_penalty.max_penalty",
            default=max_penalty,
        )
        penalty = per * intervention_count
        return max(max_p, penalty)

    @staticmethod
    def calc_intervention_intensity_modifier(actions, phase_sensitivity=1.0):
        """
        计算干预强度修正

        公式: Σ(level_weight) * phase_sensitivity

        Args:
            actions: 干预动作列表
            phase_sensitivity: 阶段敏感度系数

        Returns:
            float: 强度修正值
        """
        if not actions:
            return 0.0

        weights = Scorer._intervention_level_weights()
        total_weight = 0.0
        for action in actions:
            level = action.get("level", 0)
            weight = weights.get(level, 0)
            total_weight += weight

        return total_weight * phase_sensitivity

    @staticmethod
    def calc_intervention_reasonability_modifier(actions):
        """
        计算干预合理性修正

        合理的干预（成功阻止违规）会减少负面影响
        不必要的干预会增加负面影响

        Args:
            actions: 干预动作列表，每个action应包含 'reasonability' 字段

        Returns:
            float: 合理性修正值
        """
        if not actions:
            return 0.0

        reasonability_map = Scorer._intervention_reasonability()
        total_modifier = 0.0
        for action in actions:
            reasonability = action.get("reasonability", "preventive")
            modifier = reasonability_map.get(reasonability, 0)
            total_modifier += modifier

        return total_modifier

    @staticmethod
    def calc_habit_streak_modifier(habit_streak, intervention_intensity):
        """
        计算习惯养成修正（加强版 - 基于会议讨论2026-01-22）

        核心机制：好了还严管 → 更强的不满
        - 连续自律多天后如果仍被强干预，会产生强烈不满
        - 形成肌肉记忆后还被严管，会觉得"天天跟防贼一样"

        公式:
        - 连续自律>=5天: +0.5 - 0.4 * 当日最高干预强度
        - 连续自律>=10天: +1.0 - 0.5 * 当日最高干预强度（好了还管开始不满）
        - 连续自律>=14天: +1.5 - 0.7 * 当日最高干预强度（强烈不满）
        - 连续自律>=21天: +2.0 - 1.0 * 当日最高干预强度（已形成习惯，严管=不信任）

        Args:
            habit_streak: 连续自律天数
            intervention_intensity: 当日最高干预等级

        Returns:
            float: 习惯修正值（可能为负值，表示不满）
        """
        defaults = {
            5: {"base": 0.5, "intensity_weight": 0.4},
            10: {"base": 1.0, "intensity_weight": 0.5},
            14: {"base": 1.5, "intensity_weight": 0.7},
            21: {"base": 2.0, "intensity_weight": 1.0},
        }
        cfg = get_path("simulation.habit.streak_modifier_thresholds", default=None)
        thresholds = dict(defaults)
        if isinstance(cfg, dict):
            for key, value in cfg.items():
                if isinstance(value, dict):
                    thresholds[int(key)] = {
                        **thresholds.get(int(key), {}),
                        **value,
                    }

        if habit_streak < min(thresholds.keys(), default=5):
            return 0.0

        # 取不超过 habit_streak 的最高阈值档
        chosen = None
        for threshold in sorted(thresholds.keys()):
            if habit_streak >= threshold:
                chosen = thresholds[threshold]
        if not chosen:
            return 0.0
        return chosen.get("base", 0.0) - chosen.get("intensity_weight", 0.0) * intervention_intensity

    @staticmethod
    def calc_autonomy_modifier(actions):
        """
        计算自主性修正

        提供替代选项的干预会提升满意度
        公式: +0.5 * (提供替代选项次数 / 总干预次数)

        Args:
            actions: 干预动作列表，每个action应包含 'offered_alternative' 字段

        Returns:
            float: 自主性修正值 (0 ~ +0.5)
        """
        if not actions:
            return 0.0

        cap = get_path(
            "simulation.satisfaction.autonomy_modifier_cap",
            default=0.5,
        )
        alternative_count = sum(1 for a in actions if a.get("offered_alternative", False))
        return cap * (alternative_count / len(actions))

    @staticmethod
    def calc_overintervention_penalty(habit_streak, health_score, intervention_count, max_level):
        """
        计算过度干预惩罚（好了还严管 → 不高兴）

        核心规则（基于会议讨论2026-01-22）：
        - 健康分好（>=7）+ 连续自律（>=7天）+ 还被严管（Level>=2）= 不高兴
        - 惩罚随健康分和自律天数增加而加重

        Args:
            habit_streak: 连续自律天数
            health_score: 当日健康分 (0-10)
            intervention_count: 干预次数
            max_level: 最高干预等级

        Returns:
            float: 惩罚值（负数）
        """
        oi = get_path("simulation.satisfaction.overintervention", default=None) or {}
        min_streak = oi.get("min_habit_streak", 7)
        min_health = oi.get("min_health_score", 7)
        min_level = oi.get("min_level", 2)
        base_penalty = oi.get("base_penalty", -0.5)
        health_extra = oi.get("health_extra_per_point", -0.2)
        streak_extra = oi.get("streak_extra_per_day", -0.1)
        streak_cap = oi.get("streak_extra_cap_days", 14)
        level3_extra = oi.get("level3_extra", -0.5)
        high_count_threshold = oi.get("high_count_threshold", 3)
        high_count_health = oi.get("high_count_health", 6)
        high_count_extra = oi.get("high_count_extra", -0.2)

        if habit_streak < min_streak or health_score < min_health:
            return 0.0

        # 基础惩罚：好了还管
        penalty = 0.0

        # Level 2+的干预在表现好时会产生不满
        if max_level >= min_level:
            penalty += base_penalty
            penalty += (health_score - min_health) * health_extra
            penalty += min(habit_streak - min_streak, streak_cap) * streak_extra
            if max_level >= 3:
                penalty += level3_extra

        # 干预次数多也会增加惩罚
        if intervention_count >= high_count_threshold and health_score >= high_count_health:
            penalty += (intervention_count - (high_count_threshold - 1)) * high_count_extra

        return penalty

    @staticmethod
    def calculate_satisfaction_score(
        manager_actions,
        day,
        habit_streak=0,
        compliance_rate=0.5,
        health_score=5,
        discipline_level="medium",
        cumulative_health=None,
    ):
        """
        基于公式计算满意度分数（取代 LLM 生成）

        合并"满意度"与原"心情分"后，统一由本函数输出，整合：
          - 对干预过程的评价（频率 / 强度 / 合理性 / 自主性 / 过度干预）
          - 对当下健康状态的即时情绪反应（平台期严管 $\\Pi_t$ / 健康分低而无人管的焦虑 $N_t$）
        所有"负面惩罚项"按情绪敏感度 $\\sigma_m$ 放大，正面反馈保持自律等级无关。

        公式（$\\sigma_m \\in \\{0.7, 1.0, 1.5\\}$，HIGH/MEDIUM/LOW）：
            Sat = clip[1,10]( β₀ + P + F + I + Π + N + R + H + U + C + O )
            F / I / Π / N / O 及 R 的负向部分  *= σ_m
            H / C / U / R 的正向部分            不受 σ_m 影响

        Args:
            manager_actions: Manager 当日的干预动作列表
            day: 当前天数
            habit_streak: 连续自律天数
            compliance_rate: 遵从率 (0.0-1.0)
            health_score: 当日健康分（0-10）；若 >10 视为 0-100 区间，会被映射到 0-10
            discipline_level: 自律程度（high/medium/low），用于取 σ_m
            cumulative_health: 健康分累计状态 dict（含 in_plateau 字段，可选）

        Returns:
            tuple: (满意度分数 1-10, 评分明细 dict)
        """
        BASE_SCORE = get_path("simulation.satisfaction.base_score", default=6.0)

        # 健康分归一化到 [0,10]（调用方可能传入 0-100 区间的累计健康分）
        if health_score is None:
            health_score = 5.0
        if health_score > 10:
            health_score = health_score / 10.0

        # 情绪敏感度 σ_m
        try:
            disc_level = SelfDisciplineLevel(str(discipline_level).lower())
        except (ValueError, AttributeError):
            disc_level = SelfDisciplineLevel.MEDIUM
        _mood_sens_defaults = {"high": 0.7, "medium": 1.0, "low": 1.5}
        mood_sensitivity = get_path(
            f"simulation.health.discipline_params.{disc_level.value}.mood_sensitivity",
            default=_mood_sens_defaults.get(disc_level.value, 1.0),
        )

        # 阶段信息
        phase = Scorer.get_discipline_phase(day)
        phase_info = Scorer._discipline_phase_modifiers()[phase]
        phase_sensitivity = phase_info["intervention_sensitivity"]

        # 干预基础量
        intervention_count = len(manager_actions) if manager_actions else 0
        max_intervention_level = 0
        if manager_actions:
            max_intervention_level = max(a.get("level", 0) for a in manager_actions)

        # 1. 阶段基础修正（不受 σ_m 影响）
        phase_base_modifier = phase_info["base"]

        # 2. 干预频率修正：负面惩罚，受 σ_m 放大
        freq_cfg = get_path("simulation.satisfaction.frequency_penalty", default=None) or {}
        freq_per = freq_cfg.get("per_intervention", -0.5)
        freq_floor = freq_cfg.get("floor", -3.0)
        frequency_modifier = max(freq_floor, freq_per * intervention_count * mood_sensitivity)

        # 3. 干预强度修正：负面惩罚，受 σ_m 与阶段敏感度共同放大
        intensity_modifier = Scorer.calc_intervention_intensity_modifier(
            manager_actions, phase_sensitivity * mood_sensitivity
        )

        # 4. 平台期严管惩罚 Π_t（仅当 in_plateau 且被 ≥L2 干预时触发）
        plateau_cfg = get_path("simulation.satisfaction.plateau_penalty", default=None) or {}
        plateau_min_level = plateau_cfg.get("min_level", 2)
        plateau_amount = plateau_cfg.get("amount", -1.5)
        in_plateau = bool((cumulative_health or {}).get("in_plateau", False))
        if in_plateau and max_intervention_level >= plateau_min_level:
            plateau_penalty = plateau_amount * mood_sensitivity
        else:
            plateau_penalty = 0.0

        # 5. 忽视惩罚 N_t：健康分低但无人管 / 干预不足
        neglect_cfg = get_path("simulation.satisfaction.neglect_penalty", default=None) or {}
        neglect_health_low = neglect_cfg.get("health_lt", 5.0)        # 对应 0-10 区间
        neglect_when_no = neglect_cfg.get("when_no_intervention", -1.0)
        neglect_health_danger = neglect_cfg.get("health_danger_lt", 4.0)
        neglect_when_weak = neglect_cfg.get("when_weak_intervention", -0.5)
        if health_score < neglect_health_low and intervention_count == 0:
            neglect_penalty = neglect_when_no * mood_sensitivity
        elif health_score < neglect_health_danger and max_intervention_level < 2:
            neglect_penalty = neglect_when_weak * mood_sensitivity
        else:
            neglect_penalty = 0.0

        # 6. 干预合理性修正：合理奖励、不必要惩罚（仅负向部分受 σ_m 放大）
        reasonability_map = Scorer._intervention_reasonability()
        reasonability_modifier = 0.0
        for action in (manager_actions or []):
            rsb = action.get("reasonability", "preventive")
            if rsb == "unnecessary":
                reasonability_modifier += (
                    reasonability_map.get("unnecessary", -0.5) * mood_sensitivity
                )
            elif rsb == "reasonable":
                reasonability_modifier += reasonability_map.get("reasonable", 0.5)
            else:
                reasonability_modifier += reasonability_map.get("preventive", 0.0)

        # 7. 习惯养成修正（正面反馈，不受 σ_m 影响）
        habit_modifier = Scorer.calc_habit_streak_modifier(habit_streak, max_intervention_level)

        # 8. 自主性修正（正面反馈，不受 σ_m 影响）
        autonomy_modifier = Scorer.calc_autonomy_modifier(manager_actions)

        # 9. 遵从率修正（正面反馈，不受 σ_m 影响）
        compliance_modifier = (compliance_rate - 0.5) * 1.0

        # 10. 过度干预惩罚 O_t：负面惩罚，受 σ_m 放大
        overintervention_base = Scorer.calc_overintervention_penalty(
            habit_streak, health_score, intervention_count, max_intervention_level
        )
        # calc_overintervention_penalty 自身已产出可正可负的值；为统一 σ_m 放大规则，
        # 这里只在 O_t < 0 时乘 σ_m（正向时视作已退化为 0）。
        overintervention_penalty = overintervention_base * mood_sensitivity

        # 汇总
        total_score = (
            BASE_SCORE
            + phase_base_modifier
            + frequency_modifier
            + intensity_modifier
            + plateau_penalty
            + neglect_penalty
            + reasonability_modifier
            + habit_modifier
            + autonomy_modifier
            + compliance_modifier
            + overintervention_penalty
        )

        final_score = max(1.0, min(10.0, total_score))

        breakdown = {
            "base_score": BASE_SCORE,
            "discipline_level": disc_level.value,
            "mood_sensitivity": mood_sensitivity,
            "phase": phase,
            "phase_base_modifier": phase_base_modifier,
            "frequency_modifier": frequency_modifier,
            "intensity_modifier": intensity_modifier,
            "plateau_penalty": plateau_penalty,
            "neglect_penalty": neglect_penalty,
            "reasonability_modifier": reasonability_modifier,
            "habit_modifier": habit_modifier,
            "autonomy_modifier": autonomy_modifier,
            "compliance_modifier": compliance_modifier,
            "overintervention_penalty": overintervention_penalty,
            "in_plateau": in_plateau,
            "max_intervention_level": max_intervention_level,
            "total_before_clamp": total_score,
            "final_score": final_score,
        }

        return final_score, breakdown

    @staticmethod
    def get_satisfaction_description(score):
        """
        根据满意度分数返回简短描述

        Args:
            score: 满意度分数 (1-10)

        Returns:
            tuple: (评级, 描述)
        """
        if score >= 8.5:
            return "非常满意", "对管理方式很认可，感觉被尊重和理解"
        elif score >= 7.0:
            return "满意", "总体接受管理方式，偶有小不满"
        elif score >= 5.5:
            return "一般", "对管理方式有一定意见，但可以接受"
        elif score >= 4.0:
            return "不太满意", "觉得管理过于严格或不够人性化"
        else:
            return "不满意", "对管理方式有较大抵触情绪"

    @staticmethod
    def generate_satisfaction_summary(score, breakdown, day):
        """
        生成满意度评估的文字总结（用于日志和报告）

        Args:
            score: 满意度分数
            breakdown: 评分明细
            day: 当前天数

        Returns:
            str: 文字总结
        """
        rating, desc = Scorer.get_satisfaction_description(score)
        phase = breakdown["phase"]
        phase_names = {
            "adjustment": "磨合期",
            "formation": "习惯养成期",
            "fatigue": "倦怠期"
        }

        summary = f"第{day}天满意度评估: {score:.1f}/10 ({rating})\n"
        summary += f"当前阶段: {phase_names.get(phase, phase)}\n"
        summary += f"状态描述: {desc}\n"
        summary += f"主要影响因素:\n"

        # 列出影响最大的因素
        modifiers = [
            ("干预频率", breakdown["frequency_modifier"]),
            ("干预强度", breakdown["intensity_modifier"]),
            ("干预合理性", breakdown["reasonability_modifier"]),
            ("习惯养成", breakdown["habit_modifier"]),
            ("自主选择", breakdown["autonomy_modifier"]),
            ("遵从效果", breakdown["compliance_modifier"]),
        ]

        # 按绝对值排序，显示影响最大的因素
        sorted_modifiers = sorted(modifiers, key=lambda x: abs(x[1]), reverse=True)
        for name, value in sorted_modifiers[:3]:
            if value != 0:
                direction = "+" if value > 0 else ""
                summary += f"  - {name}: {direction}{value:.2f}\n"

        return summary

    # ==================== 综合评估系统 ====================
    # 将健康分和满意度整合，形成完整的评估体系

    # 综合评估权重配置
    COMPOSITE_WEIGHTS = {
        "health": 0.5,           # 健康分权重
        "satisfaction": 0.3,     # 满意度权重
        "effectiveness": 0.2,    # 干预效果权重
    }

    # 干预效果评级阈值
    EFFECTIVENESS_THRESHOLDS = {
        "excellent": 2.0,    # 健康分提升 >= 2
        "good": 1.0,         # 健康分提升 >= 1
        "neutral": 0.0,      # 健康分无变化
        "poor": -1.0,        # 健康分下降 <= -1
    }

    @staticmethod
    def calculate_health_trend(health_history, window=7):
        """
        计算健康分变化趋势

        Args:
            health_history: 历史健康分列表 [day1, day2, ...]
            window: 计算窗口大小（天）

        Returns:
            float: 趋势值（正数=改善，负数=恶化）
        """
        if not health_history or len(health_history) < 2:
            return 0.0

        # 取最近window天的数据
        recent = health_history[-window:] if len(health_history) >= window else health_history

        if len(recent) < 2:
            return 0.0

        # 计算线性趋势（简单差值）
        trend = recent[-1] - recent[0]

        # 也可以用加权平均考虑近期数据更重要
        # weights = [i + 1 for i in range(len(recent))]
        # weighted_avg = sum(v * w for v, w in zip(recent, weights)) / sum(weights)
        # trend = weighted_avg - recent[0]

        return trend

    @staticmethod
    def calculate_intervention_effectiveness(
        health_before, health_after, compliance_rate, intervention_count
    ):
        """
        计算干预效果分数

        公式：
        效果分 = 健康分变化 * 0.4 + 遵从率 * 3 + 干预效率修正

        干预效率 = 健康改善 / 干预次数（干预越少改善越多越好）

        Args:
            health_before: 干预前健康分
            health_after: 干预后健康分
            compliance_rate: 遵从率 (0.0-1.0)
            intervention_count: 干预次数

        Returns:
            tuple: (效果分0-10, 效果评级, 明细dict)
        """
        # 1. 健康分变化（-10 ~ +10 映射到 0 ~ 4）
        health_change = health_after - health_before
        health_change_score = (health_change + 5) * 0.4  # 映射到 0-4 范围

        # 2. 遵从率贡献（0-3分）
        compliance_score = compliance_rate * 3

        # 3. 干预效率（健康改善/干预次数）
        if intervention_count > 0:
            efficiency = health_change / intervention_count
            # 效率修正：-1 ~ +3 映射到 0-3
            efficiency_score = max(0, min(3, (efficiency + 1) * 0.75))
        else:
            # 无干预时，如果健康分保持或改善，给高分
            efficiency_score = 2.0 if health_change >= 0 else 0.5

        total_score = health_change_score + compliance_score + efficiency_score
        total_score = max(0, min(10, total_score))

        # 评级（阈值来自 mechanism config）
        thresholds = Scorer._effectiveness_thresholds()
        if health_change >= thresholds.get("excellent", 2.0):
            rating = "excellent"
            rating_cn = "优秀"
        elif health_change >= thresholds.get("good", 1.0):
            rating = "good"
            rating_cn = "良好"
        elif health_change >= thresholds.get("neutral", 0.0):
            rating = "neutral"
            rating_cn = "稳定"
        elif health_change >= thresholds.get("poor", -1.0):
            rating = "poor"
            rating_cn = "需改进"
        else:
            rating = "very_poor"
            rating_cn = "效果差"

        breakdown = {
            "health_change": health_change,
            "health_change_score": health_change_score,
            "compliance_rate": compliance_rate,
            "compliance_score": compliance_score,
            "intervention_count": intervention_count,
            "efficiency_score": efficiency_score,
            "total_score": total_score,
            "rating": rating,
            "rating_cn": rating_cn,
        }

        return total_score, rating, breakdown

    @staticmethod
    def calculate_composite_score(
        health_score,
        satisfaction_score,
        effectiveness_score,
        weights=None
    ):
        """
        计算综合评分

        公式：
        综合分 = 健康分 * w1 + 满意度 * w2 + 效果分 * w3

        默认权重：健康50% + 满意度30% + 效果20%

        Args:
            health_score: 健康分 (0-10)
            satisfaction_score: 满意度分 (1-10)
            effectiveness_score: 干预效果分 (0-10)
            weights: 自定义权重 dict，默认使用 COMPOSITE_WEIGHTS

        Returns:
            tuple: (综合分0-10, 评级, 明细dict)
        """
        if weights is None:
            weights = Scorer._composite_weights()

        w_health = weights.get("health", 0.5)
        w_satisfaction = weights.get("satisfaction", 0.3)
        w_effectiveness = weights.get("effectiveness", 0.2)

        # 归一化权重
        total_weight = w_health + w_satisfaction + w_effectiveness
        w_health /= total_weight
        w_satisfaction /= total_weight
        w_effectiveness /= total_weight

        composite = (
            health_score * w_health
            + satisfaction_score * w_satisfaction
            + effectiveness_score * w_effectiveness
        )

        # 评级（阈值来自 mechanism config）
        rating_th = Scorer._rating_thresholds()
        if composite >= rating_th.get("A", 8.0):
            rating = "A"
            rating_desc = "优秀 - 健康改善显著且用户接受度高"
        elif composite >= rating_th.get("B", 6.5):
            rating = "B"
            rating_desc = "良好 - 整体效果较好，有改进空间"
        elif composite >= rating_th.get("C", 5.0):
            rating = "C"
            rating_desc = "一般 - 需要调整干预策略"
        elif composite >= rating_th.get("D", 3.5):
            rating = "D"
            rating_desc = "较差 - 干预效果不佳或用户抵触"
        else:
            rating = "F"
            rating_desc = "失败 - 需要重新评估干预方案"

        breakdown = {
            "health_score": health_score,
            "health_weight": w_health,
            "health_contribution": health_score * w_health,
            "satisfaction_score": satisfaction_score,
            "satisfaction_weight": w_satisfaction,
            "satisfaction_contribution": satisfaction_score * w_satisfaction,
            "effectiveness_score": effectiveness_score,
            "effectiveness_weight": w_effectiveness,
            "effectiveness_contribution": effectiveness_score * w_effectiveness,
            "composite_score": composite,
            "rating": rating,
            "rating_desc": rating_desc,
        }

        return composite, rating, breakdown

    @staticmethod
    def evaluate_day(
        agent_data,
        manager_actions,
        day,
        habit_streak,
        compliance_rate,
        health_history,
        scenario="diabetes"
    ):
        """
        综合评估一天的健康管理效果

        整合健康分、满意度、干预效果为统一评估

        Args:
            agent_data: Agent当日行为数据
            manager_actions: Manager当日干预动作
            day: 当前天数
            habit_streak: 连续自律天数
            compliance_rate: 遵从率
            health_history: 历史健康分列表
            scenario: 场景类型

        Returns:
            dict: 完整的评估结果
        """
        # 1. 计算健康分
        health_score = Scorer.calculate_health_score(agent_data, scenario)

        # 2. 计算满意度（传入健康分用于过度干预惩罚计算）
        satisfaction_score, satisfaction_breakdown = Scorer.calculate_satisfaction_score(
            manager_actions, day, habit_streak, compliance_rate, health_score
        )

        # 3. 计算干预效果
        health_before = health_history[-1] if health_history else 5.0
        intervention_count = len(manager_actions) if manager_actions else 0
        effectiveness_score, effectiveness_rating, effectiveness_breakdown = \
            Scorer.calculate_intervention_effectiveness(
                health_before, health_score, compliance_rate, intervention_count
            )

        # 4. 计算综合分
        composite_score, composite_rating, composite_breakdown = \
            Scorer.calculate_composite_score(
                health_score, satisfaction_score, effectiveness_score
            )

        # 5. 计算健康趋势
        updated_history = (health_history or []) + [health_score]
        health_trend = Scorer.calculate_health_trend(updated_history)

        # 6. 生成建议
        recommendations = Scorer._generate_recommendations(
            health_score, satisfaction_score, effectiveness_rating,
            satisfaction_breakdown, day
        )

        return {
            "day": day,
            "scenario": scenario,
            "health": {
                "score": health_score,
                "grade": Scorer.get_health_grade(health_score)[0],
                "trend": health_trend,
            },
            "satisfaction": {
                "score": satisfaction_score,
                "phase": satisfaction_breakdown["phase"],
                "breakdown": satisfaction_breakdown,
            },
            "effectiveness": {
                "score": effectiveness_score,
                "rating": effectiveness_rating,
                "breakdown": effectiveness_breakdown,
            },
            "composite": {
                "score": composite_score,
                "rating": composite_rating,
                "breakdown": composite_breakdown,
            },
            "recommendations": recommendations,
        }

    @staticmethod
    def _generate_recommendations(
        health_score, satisfaction_score, effectiveness_rating,
        satisfaction_breakdown, day
    ):
        """
        基于评估结果生成改进建议

        Args:
            health_score: 健康分
            satisfaction_score: 满意度
            effectiveness_rating: 效果评级
            satisfaction_breakdown: 满意度明细
            day: 当前天数

        Returns:
            list: 建议列表
        """
        recommendations = []

        # 健康分相关建议
        if health_score < 5:
            recommendations.append({
                "type": "health",
                "priority": "high",
                "message": "健康行为需要显著改善，建议加强干预力度"
            })
        elif health_score < 7:
            recommendations.append({
                "type": "health",
                "priority": "medium",
                "message": "健康行为有改进空间，保持当前干预策略"
            })

        # 满意度相关建议
        if satisfaction_score < 4:
            recommendations.append({
                "type": "satisfaction",
                "priority": "high",
                "message": "用户满意度低，建议降低干预强度或增加沟通"
            })
            # 检查具体原因
            if satisfaction_breakdown["intensity_modifier"] < -1:
                recommendations.append({
                    "type": "satisfaction",
                    "priority": "medium",
                    "message": "干预强度过高，考虑使用更温和的方式"
                })
            if satisfaction_breakdown["frequency_modifier"] < -1:
                recommendations.append({
                    "type": "satisfaction",
                    "priority": "medium",
                    "message": "干预频率过高，考虑减少干预次数"
                })

        # 阶段相关建议
        phase = satisfaction_breakdown["phase"]
        if phase == "fatigue" and satisfaction_score < 6:
            recommendations.append({
                "type": "phase",
                "priority": "medium",
                "message": "处于倦怠期，建议增加正向激励和情感支持"
            })
        elif phase == "adjustment" and health_score < 5:
            recommendations.append({
                "type": "phase",
                "priority": "medium",
                "message": "磨合期健康分较低，可适当加强干预但注意用户反应"
            })

        # 效果相关建议
        if effectiveness_rating in ["poor", "very_poor"]:
            recommendations.append({
                "type": "effectiveness",
                "priority": "high",
                "message": "干预效果不佳，需要重新评估干预策略"
            })

        # 平衡建议
        if health_score >= 7 and satisfaction_score < 5:
            recommendations.append({
                "type": "balance",
                "priority": "medium",
                "message": "健康改善但满意度低，建议减少干预力度以提高可持续性"
            })
        elif health_score < 5 and satisfaction_score >= 7:
            recommendations.append({
                "type": "balance",
                "priority": "medium",
                "message": "满意度高但健康改善不足，可能需要适当增加干预"
            })

        return recommendations

    @staticmethod
    def _get_phase_name(phase):
        """获取阶段的中文名称"""
        phase_names = {
            "adjustment": "磨合期",
            "formation": "习惯养成期",
            "fatigue": "倦怠期"
        }
        return phase_names.get(phase, phase)

    @staticmethod
    def generate_daily_report(evaluation_result):
        """
        生成每日评估报告

        Args:
            evaluation_result: evaluate_day() 的返回结果

        Returns:
            str: 格式化的报告文本
        """
        day = evaluation_result["day"]
        health = evaluation_result["health"]
        satisfaction = evaluation_result["satisfaction"]
        effectiveness = evaluation_result["effectiveness"]
        composite = evaluation_result["composite"]
        recommendations = evaluation_result["recommendations"]

        report = f"""
================================================================================
                           第 {day} 天 健康管理评估报告
================================================================================

【综合评分】{composite['score']:.1f}/10 ({composite['rating']})
{composite['breakdown']['rating_desc']}

--------------------------------------------------------------------------------
                                  分项评分
--------------------------------------------------------------------------------

1. 健康行为分: {health['score']}/10 ({health['grade']})
   趋势: {'↑ 改善' if health['trend'] > 0 else '↓ 恶化' if health['trend'] < 0 else '→ 稳定'} ({health['trend']:+.1f})

2. 用户满意度: {satisfaction['score']:.1f}/10
   当前阶段: {Scorer._get_phase_name(satisfaction['phase'])}
   主要影响:
"""
        # 添加满意度影响因素
        breakdown = satisfaction["breakdown"]
        factors = [
            ("干预频率", breakdown["frequency_modifier"]),
            ("干预强度", breakdown["intensity_modifier"]),
            ("干预合理性", breakdown["reasonability_modifier"]),
            ("过度干预惩罚", breakdown.get("overintervention_penalty", 0)),  # 新增
            ("习惯养成", breakdown.get("habit_modifier", 0)),
        ]
        for name, value in factors:
            if value != 0:
                report += f"     - {name}: {value:+.2f}\n"

        report += f"""
3. 干预效果: {effectiveness['score']:.1f}/10 ({effectiveness['breakdown']['rating_cn']})
   健康变化: {effectiveness['breakdown']['health_change']:+.1f}
   遵从率: {effectiveness['breakdown']['compliance_rate']*100:.0f}%

--------------------------------------------------------------------------------
                                  改进建议
--------------------------------------------------------------------------------
"""
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                priority_icon = "🔴" if rec["priority"] == "high" else "🟡" if rec["priority"] == "medium" else "🟢"
                report += f"{i}. {priority_icon} [{rec['type']}] {rec['message']}\n"
        else:
            report += "当前状态良好，继续保持！\n"

        report += """
================================================================================
"""
        return report

    # ==================== 累积健康分系统新增方法 ====================

    # 注：原 calculate_mood_score_with_discipline / get_mood_description 已并入
    # calculate_satisfaction_score，不再单独输出心情分。所有主观评分由
    # calculate_satisfaction_score 统一给出。
