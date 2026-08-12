"""generative_agents.scorer

评分系统：基于医学标准计算健康分和满意度
参考文献：
- 美国糖尿病协会(ADA)《糖尿病护理标准—2025》
- 《中国糖尿病防治指南（2024版）》
- Electronic Screen Use and Sleep Duration
- 体重管理指导原则（2024年版）

核心机制（基于会议讨论 2026-01-22/23）：
================================================================================

【重要更新 2026-01-23：累积健康分系统】

1. 健康分模式变更：
   - 旧模式：每日绝对分(0-10)
   - 新模式：初始分 + 每日增减值（累积模式）

2. 三种初始健康分：
   - 高起点：90分（代表健康状况较好的人）
   - 中起点：75分（代表普通状况的人）
   - 低起点：60分（代表健康状况较差的人）

3. 警戒线：30分（健康崩溃阈值）
   - 低于30分视为健康严重受损

4. 自然恢复机制：
   - 无不良行为时健康自然恢复（+1~+3分/天，视自律程度）
   - 恢复有上限（不超过初始分）

5. 三种自律程度及其影响：
   - 高自律(high)：平台期长、下滑慢、自然恢复快(+3)、情绪稳定
   - 中自律(medium)：平台期中等、下滑适中、自然恢复中(+2)
   - 低自律(low)：平台期短、下滑快、自然恢复慢(+1)、情绪敏感

6. 潮汐性满意度变化：
   - 不好时不管 → 不高兴
   - 不好时管 → 高兴
   - 好了还严管 → 不高兴（"天天跟防贼一样"）
   - 放松后又变坏且不管 → 不高兴

7. 信任度机制（管理者学习曲线）：
   - 连续表现好建立信任
   - 过度干预破坏信任
   - 信任度影响放松决策和满意度
   - 管理者越来越早介入、越来越高效

================================================================================

评分公式汇总（基于上述文献）：
|影响维度|具体行为/条件|睡眠影响|减肥影响|糖尿病影响|
|---|---|---|---|---|
|**进餐食物种类**|高糖高脂| -1 | -5 | -4 |
| |低糖低脂| +1 | +3 | +2 |
| |高GI| 0 | -2 | -5 |
| |低GI| 0 | +2 | +5 |
|**进食量**|较多（超热量目标）| -2 | -5 | -4 |
| |适中（符合目标）| +1 | +3 | +3 |
| |较少（低于基础需求）| 0 | +1 | -1 |
|**结束玩手机时间**|22:00前| +5 | +2 | +2 |
| |22:00-24:00| +2 | +1 | +1 |
| |0:00-1:00| -3 | -1 | -1 |
| |1:00以后| -5 | -2 | -2 |
|**玩手机的种类**|办公| -2 | 0 | 0 |
| |游戏| -5 | 0 | 0 |
| |刷视频| -3 | 0 | 0 |
| |社交/聊天| -2 | 0 | 0 |
|**进餐到睡觉间隔时间**|通用公式| (t-180)*0.03 | (t-180)*0.02 | (t-180)*0.04 |
|**连续使用时长（单次）**|公式| (30-t)*0.15 | 0 | 0 |
|**夜间使用总时长**|公式| (120-t)*0.1 | 0 | (120-t)*0.05 (t>120) |
"""

import datetime
from copy import deepcopy
from enum import Enum
from typing import Any, Dict, Tuple, Optional, List

from modules.mechanism_config import get_path


def _deep_merge_dict(base: Dict, override: Optional[Dict]) -> Dict:
    """浅层嵌套合并：override 覆盖 base，保留未出现的键。"""
    if not isinstance(override, dict):
        return deepcopy(base)
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _resolve_linear_discipline_params(
    level: "SelfDisciplineLevel",
    hardcoded: Dict[str, Any],
) -> Dict[str, Any]:
    """从 mechanism config 合并自律参数；natural_recovery 始终用硬编码。"""
    cfg = get_path(
        f"simulation.health.discipline_params.{level.value}",
        default=None,
    )
    if not isinstance(cfg, dict):
        return dict(hardcoded)
    merged = dict(hardcoded)
    natural = hardcoded.get("natural_recovery")
    for key, value in cfg.items():
        if key == "natural_recovery":
            continue
        merged[key] = value
    if natural is not None:
        merged["natural_recovery"] = natural
    return merged


class SelfDisciplineLevel(Enum):
    """自律程度枚举"""
    HIGH = "high"       # 高自律
    MEDIUM = "medium"   # 中等自律
    LOW = "low"         # 低自律




class CumulativeHealthScorer:
    """累积健康分计算器（新系统：初始分 + 每日增减）

    核心设计理念（基于会议 2026-01-23）：
    1. 健康分从初始值开始（60/75/90），每天根据行为增减
    2. 警戒线30分，低于此值视为健康崩溃
    3. 无不良行为时自然恢复，恢复速度取决于自律程度
    4. 自然恢复有上限，不超过初始分
    5. 自律程度影响：平台期长度、下滑速度、恢复速度、情绪敏感度
    """

    # 警戒线
    WARNING_LINE = 30

    # 自律程度参数配置
    # 设计目标：产生"平台期+V形下跌+恢复"的健康曲线
    # - 平台期：健康分稳定在初始分（上限=初始分）
    # - V形下跌：每次未阻止的违规造成较大惩罚（10-15分/次）
    # - 恢复期：无违规时按recovery速度恢复到初始分
    # 典型模式：HIGH每5-7天一次浅V，MEDIUM每3-5天一次中V，LOW频繁深V
    DISCIPLINE_PARAMS = {
        SelfDisciplineLevel.HIGH: {
            "natural_recovery": 3,        # 每天自然恢复分数（适当降低）
            "plateau_duration": 14,       # 平台期持续天数（天）
            "decline_rate": 0.5,          # 下滑速度（分/天）
            "mood_sensitivity": 0.7,      # 情绪敏感度（越低越稳定）
            "violation_penalty": 10,      # 违规惩罚基础分（每次未阻止的违规）
            "compliance_bonus": 2,        # 遵从奖励基础分（限制在初始分以下）
            "description": "高自律：平台期长(14天)、恢复快(+3/天)、每次违规-10、2天恢复",
        },
        SelfDisciplineLevel.MEDIUM: {
            "natural_recovery": 2,
            "plateau_duration": 7,
            "decline_rate": 1.0,
            "mood_sensitivity": 1.0,
            "violation_penalty": 12,
            "compliance_bonus": 1.5,
            "description": "中自律：平台期中(7天)、恢复中(+2/天)、每次违规-12、4天恢复",
        },
        SelfDisciplineLevel.LOW: {
            "natural_recovery": 1.5,
            "plateau_duration": 3,
            "decline_rate": 2.0,
            "mood_sensitivity": 1.5,
            "violation_penalty": 15,
            "compliance_bonus": 1,
            "description": "低自律：平台期短(3天)、恢复慢(+1.5/天)、每次违规-15、7天恢复",
        },
    }

    def __init__(
        self,
        initial_score: int = 75,
        discipline_level: str = "medium",
        scenario: str = "diabetes"
    ):
        """初始化累积健康分计算器

        Args:
            initial_score: 初始健康分（60/75/90）
            discipline_level: 自律程度（high/medium/low）
            scenario: 场景类型（diabetes/weight-loss/phone-addiction）
        """
        self.initial_score = initial_score
        self.current_score = float(initial_score)
        self.scenario = scenario

        # 解析自律程度
        if isinstance(discipline_level, SelfDisciplineLevel):
            self.discipline_level = discipline_level
        else:
            self.discipline_level = SelfDisciplineLevel(discipline_level.lower())

        # 从 mechanism config 读取可外置参数（硬编码为 default）
        self.WARNING_LINE = get_path(
            "simulation.health.warning_line",
            default=CumulativeHealthScorer.WARNING_LINE,
        )
        self.params = _resolve_linear_discipline_params(
            self.discipline_level,
            self.DISCIPLINE_PARAMS[self.discipline_level],
        )

        # 追踪状态
        self.day_count = 0
        self.consecutive_good_days = 0
        self.consecutive_bad_days = 0
        self.plateau_days = 0  # 平台期计数
        self.in_plateau = False
        self.history: List[Dict] = []

        # 潮汐周期追踪
        self.last_trough_day = 0  # 上一次低谷的天数
        self.last_peak_day = 0    # 上一次高峰的天数
        self.trough_count = 0     # 低谷次数（复发次数）

    def calculate_daily_change(
        self,
        agent_data: Dict,
        had_violation: bool,
        intervention_count: int,
        intervention_success: bool,
        unblocked_violation_count: int = 0
    ) -> Tuple[float, Dict]:
        """计算每日健康分变化

        Args:
            agent_data: 当日行为数据
            had_violation: 是否有违规行为（偷吃、熬夜玩手机等）
            intervention_count: 干预次数
            intervention_success: 干预是否成功（阻止了违规）
            unblocked_violation_count: 未被阻止的违规次数（用于按比例计算惩罚）

        Returns:
            Tuple[float, Dict]: (健康分变化值, 详细分解)
        """
        self.day_count += 1
        change = 0.0
        breakdown = {
            "day": self.day_count,
            "initial_score": self.current_score,
            "components": {},
        }

        # 实际违规次数（至少1次如果had_violation为True）
        actual_violations = max(1, unblocked_violation_count) if had_violation else 0

        # 每日违规数量上限（防止单日健康崩溃）
        # 每天最多计1次违规的惩罚，深V-dip需要连续多天违规
        MAX_EFFECTIVE_VIOLATIONS = 1
        actual_violations = min(actual_violations, MAX_EFFECTIVE_VIOLATIONS)

        # 1. 检查是否有违规行为
        if had_violation:
            if intervention_success and unblocked_violation_count == 0:
                # 干预成功阻止了所有违规 - 小幅惩罚（有意图但被阻止）
                penalty = -self.params["violation_penalty"] * 0.3
                change += penalty
                breakdown["components"]["blocked_violation"] = penalty
                self.consecutive_bad_days = 0
            else:
                # 违规发生
                per_violation_penalty = self.params["violation_penalty"]

                # 如果已经在恢复期（低于初始分），违规影响大幅减弱
                # （模拟违规后的警觉性提高，"吃过亏"的保护效应）
                # 确保recovery_penalty < natural_recovery，使恢复趋势不被打断
                in_recovery = self.current_score < self.initial_score
                if in_recovery:
                    per_violation_penalty *= 0.15
                    breakdown["components"]["recovery_protection"] = True

                total_penalty = per_violation_penalty * actual_violations
                penalty = -total_penalty
                change += penalty
                breakdown["components"]["violation"] = penalty
                breakdown["components"]["violation_count"] = actual_violations

                if in_recovery:
                    # 恢复期的轻微违规不计入"连续不良天数"（不触发加速下滑）
                    # 违规日恢复补贴：无违规日已有自然恢复，这里只补贴部分（0.3倍）
                    recovery = min(
                        self.params["natural_recovery"] * 0.3,
                        self.initial_score - (self.current_score + change)
                    )
                    recovery = max(0, recovery)
                    if recovery > 0:
                        change += recovery
                        breakdown["components"]["recovery_during_violation"] = recovery
                else:
                    self.consecutive_bad_days += 1
                    self.consecutive_good_days = 0

                # 如果从平台期跌落（首次违规从高点开始）
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

            # 2. 自然恢复（如果当前分低于初始分）
            if self.current_score < self.initial_score:
                recovery = min(
                    self.params["natural_recovery"],
                    self.initial_score - self.current_score  # 不超过初始分
                )
                change += recovery
                breakdown["components"]["natural_recovery"] = recovery

            # 3. 遵从奖励（只在低于初始分时生效，不超过初始分）
            if intervention_count > 0 and intervention_success:
                if self.current_score < self.initial_score:
                    bonus = min(
                        self.params["compliance_bonus"],
                        self.initial_score - self.current_score - change  # 确保不超过初始分
                    )
                    bonus = max(0, bonus)  # 不为负
                    if bonus > 0:
                        change += bonus
                        breakdown["components"]["compliance_bonus"] = bonus

        # 4. 平台期检测（连续表现好达到阈值）
        if self.consecutive_good_days >= self.params["plateau_duration"]:
            if not self.in_plateau:
                self.in_plateau = True
                self.last_peak_day = self.day_count
                breakdown["components"]["entered_plateau"] = True
            self.plateau_days += 1

        # 5. 持续恶化时的加速下滑（连续多天不良）
        if self.consecutive_bad_days >= 3:
            # 越久不管越危险
            acceleration = -self.params["decline_rate"] * (self.consecutive_bad_days - 2)
            change += acceleration
            breakdown["components"]["decline_acceleration"] = acceleration

        # 6. 更新当前分数
        new_score = self.current_score + change

        # 确保分数在合理范围内：上限为初始分（不超过起点），下限为0
        new_score = max(0, min(self.initial_score, new_score))

        # 记录
        breakdown["change"] = change
        breakdown["new_score"] = new_score
        breakdown["below_warning"] = new_score < self.WARNING_LINE
        breakdown["consecutive_good_days"] = self.consecutive_good_days
        breakdown["consecutive_bad_days"] = self.consecutive_bad_days
        breakdown["in_plateau"] = self.in_plateau
        breakdown["plateau_days"] = self.plateau_days

        self.history.append(breakdown)
        self.current_score = new_score

        return change, breakdown

    def get_health_status(self) -> str:
        """获取当前健康状态描述"""
        if self.current_score >= 80:
            return "excellent"  # 优秀
        elif self.current_score >= 60:
            return "good"  # 良好
        elif self.current_score >= self.WARNING_LINE:
            return "fair"  # 一般
        else:
            return "critical"  # 危险

    def get_tide_phase(self) -> str:
        """获取当前潮汐周期阶段"""
        if self.in_plateau:
            return "plateau"  # 平台期（高点）
        elif self.consecutive_bad_days >= 3:
            return "declining"  # 下滑期
        elif self.consecutive_good_days >= 2:
            return "recovering"  # 恢复期
        else:
            return "fluctuating"  # 波动期

    def get_summary(self) -> Dict:
        """获取健康分摘要"""
        return {
            "initial_score": self.initial_score,
            "current_score": round(self.current_score, 1),
            "discipline_level": self.discipline_level.value,
            "day_count": self.day_count,
            "status": self.get_health_status(),
            "tide_phase": self.get_tide_phase(),
            "consecutive_good_days": self.consecutive_good_days,
            "consecutive_bad_days": self.consecutive_bad_days,
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
            "plateau_days": self.plateau_days,
            "in_plateau": self.in_plateau,
            "last_trough_day": self.last_trough_day,
            "last_peak_day": self.last_peak_day,
            "trough_count": self.trough_count,
            "history": self.history[-30:],  # 只保留最近30天
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CumulativeHealthScorer":
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
        scorer.plateau_days = data.get("plateau_days", 0)
        scorer.in_plateau = data.get("in_plateau", False)
        scorer.last_trough_day = data.get("last_trough_day", 0)
        scorer.last_peak_day = data.get("last_peak_day", 0)
        scorer.trough_count = data.get("trough_count", 0)
        scorer.history = data.get("history", [])
        return scorer


# ---------------------------------------------------------------------------
# 兼容导出：满意度/心情等计算已迁至 scorer_nonlinear.Scorer
# 新代码请直接：from modules.health_mechanisms.scoring.nonlinear import Scorer, NonlinearHealthScorer
# ---------------------------------------------------------------------------
from modules.health_mechanisms.scoring.nonlinear import Scorer, InitialHealthScore  # noqa: E402,F401
