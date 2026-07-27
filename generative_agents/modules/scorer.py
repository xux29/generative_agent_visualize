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
from enum import Enum
from typing import Dict, Tuple, Optional, List


class SelfDisciplineLevel(Enum):
    """自律程度枚举"""
    HIGH = "high"       # 高自律
    MEDIUM = "medium"   # 中等自律
    LOW = "low"         # 低自律


class InitialHealthScore(Enum):
    """初始健康分枚举"""
    HIGH = 90    # 高起点
    MEDIUM = 75  # 中起点
    LOW = 60     # 低起点


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

        self.params = self.DISCIPLINE_PARAMS[self.discipline_level]

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
        coefficients = {
            "sleep": 0.03,
            "weight": 0.02,
            "diabetes": 0.04
        }
        coef = coefficients.get(scenario, 0.03)
        return (interval_minutes - 180) * coef

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
        return (30 - duration_minutes) * 0.15

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
        food_score = Scorer.FOOD_TYPE_SCORES.get(food_type, {}).get("diabetes", 0)
        base_score += food_score

        # 2. 进食量
        food_amount = agent_data.get("food_amount", "none")
        amount_score = Scorer.FOOD_AMOUNT_SCORES.get(food_amount, {}).get("diabetes", 0)
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
            time_score = Scorer.PHONE_END_TIME_SCORES.get(time_category, {}).get("diabetes", 0)
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
            snack_score = Scorer.FOOD_TYPE_SCORES.get(snacking_type, {}).get("diabetes", -2)
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
        food_score = Scorer.FOOD_TYPE_SCORES.get(food_type, {}).get("weight", 0)
        base_score += food_score

        # 2. 进食量
        food_amount = agent_data.get("food_amount", "none")
        amount_score = Scorer.FOOD_AMOUNT_SCORES.get(food_amount, {}).get("weight", 0)
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
            time_score = Scorer.PHONE_END_TIME_SCORES.get(time_category, {}).get("weight", 0)
            base_score += time_score

        # 偷吃行为额外惩罚
        snacking_count = agent_data.get("snacking_count", 0)
        if snacking_count > 0:
            snacking_type = agent_data.get("snacking_type", "processed")
            snack_score = Scorer.FOOD_TYPE_SCORES.get(snacking_type, {}).get("weight", -3)
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
            time_score = Scorer.PHONE_END_TIME_SCORES.get(time_category, {}).get("sleep", 0)
            base_score += time_score

        # 2. 玩手机种类
        phone_activity = agent_data.get("phone_activity", "none")
        activity_score = Scorer.PHONE_ACTIVITY_SCORES.get(phone_activity, {}).get("sleep", 0)
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
        food_score = Scorer.FOOD_TYPE_SCORES.get(food_type, {}).get("sleep", 0)
        base_score += food_score

        # 2. 进食量
        food_amount = agent_data.get("food_amount", "none")
        amount_score = Scorer.FOOD_AMOUNT_SCORES.get(food_amount, {}).get("sleep", 0)
        base_score += amount_score

        # 3. 玩手机结束时间
        phone_end_time = agent_data.get("phone_end_time")
        if phone_end_time:
            time_category = Scorer.get_phone_end_time_category(phone_end_time)
            time_score = Scorer.PHONE_END_TIME_SCORES.get(time_category, {}).get("sleep", 0)
            base_score += time_score

        # 4. 玩手机种类
        phone_activity = agent_data.get("phone_activity", "none")
        activity_score = Scorer.PHONE_ACTIVITY_SCORES.get(phone_activity, {}).get("sleep", 0)
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
        if day <= 7:
            return "adjustment"
        elif day <= 21:
            return "formation"
        else:
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
        penalty = -0.5 * intervention_count
        return max(max_penalty, penalty)

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

        total_weight = 0.0
        for action in actions:
            level = action.get("level", 0)
            weight = Scorer.INTERVENTION_LEVEL_WEIGHTS.get(level, 0)
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

        total_modifier = 0.0
        for action in actions:
            reasonability = action.get("reasonability", "preventive")
            modifier = Scorer.INTERVENTION_REASONABILITY.get(reasonability, 0)
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
        if habit_streak < 5:
            return 0.0
        elif habit_streak < 10:
            # 初步形成习惯，轻微正面修正
            return 0.5 - 0.4 * intervention_intensity
        elif habit_streak < 14:
            # 习惯逐渐稳固，过度干预开始产生不满
            return 1.0 - 0.5 * intervention_intensity
        elif habit_streak < 21:
            # 习惯较稳固，强干预会产生强烈不满
            return 1.5 - 0.7 * intervention_intensity
        else:
            # 已形成稳定习惯（21天+），任何强干预都会被视为不信任
            # Level 3干预会导致：2.0 - 1.0*3 = -1.0（显著负面）
            return 2.0 - 1.0 * intervention_intensity

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

        alternative_count = sum(1 for a in actions if a.get("offered_alternative", False))
        return 0.5 * (alternative_count / len(actions))

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
        if habit_streak < 7 or health_score < 7:
            return 0.0

        # 基础惩罚：好了还管
        penalty = 0.0

        # Level 2+的干预在表现好时会产生不满
        if max_level >= 2:
            # 基础惩罚
            penalty -= 0.5

            # 健康分越高，惩罚越重（你都这么好了还管）
            penalty -= (health_score - 7) * 0.2

            # 连续自律越久，惩罚越重（都自律这么久了还不信任）
            penalty -= min(habit_streak - 7, 14) * 0.1

            # Level 3（锁定）额外惩罚
            if max_level >= 3:
                penalty -= 0.5

        # 干预次数多也会增加惩罚
        if intervention_count >= 3 and health_score >= 6:
            penalty -= (intervention_count - 2) * 0.2

        return penalty

    @staticmethod
    def calculate_satisfaction_score(manager_actions, day, habit_streak=0, compliance_rate=0.5, health_score=5):
        """
        基于公式计算满意度分数（取代LLM生成）- 增强版

        公式（增强版 - 基于会议讨论2026-01-22）：
        满意度 = 基础分(6.0)
               + 阶段基础修正
               + 干预频率修正
               + 干预强度修正 * 阶段敏感度
               + 干预合理性修正
               + 习惯养成修正（加强版）
               + 自主性修正
               + 遵从率修正
               + 过度干预惩罚（新增：好了还严管的惩罚）

        Args:
            manager_actions: Manager 当日的干预动作列表
            day: 当前天数
            habit_streak: 连续自律天数
            compliance_rate: 遵从率 (0.0-1.0)
            health_score: 当日健康分 (0-10)，新增参数

        Returns:
            tuple: (满意度分数1-10, 评分明细dict)
        """
        BASE_SCORE = 6.0

        # 获取阶段信息
        phase = Scorer.get_discipline_phase(day)
        phase_info = Scorer.DISCIPLINE_PHASE_MODIFIERS[phase]

        # 1. 阶段基础修正
        phase_base_modifier = phase_info["base"]

        # 2. 干预频率修正
        intervention_count = len(manager_actions) if manager_actions else 0
        frequency_modifier = Scorer.calc_intervention_frequency_modifier(intervention_count)

        # 3. 干预强度修正（考虑阶段敏感度）
        phase_sensitivity = phase_info["intervention_sensitivity"]
        intensity_modifier = Scorer.calc_intervention_intensity_modifier(
            manager_actions, phase_sensitivity
        )

        # 4. 干预合理性修正
        reasonability_modifier = Scorer.calc_intervention_reasonability_modifier(manager_actions)

        # 5. 习惯养成修正（加强版）
        max_intervention_level = 0
        if manager_actions:
            max_intervention_level = max(a.get("level", 0) for a in manager_actions)
        habit_modifier = Scorer.calc_habit_streak_modifier(habit_streak, max_intervention_level)

        # 6. 自主性修正
        autonomy_modifier = Scorer.calc_autonomy_modifier(manager_actions)

        # 7. 遵从率修正：遵从率高意味着干预有效，长期会提升满意度
        # 公式: (compliance_rate - 0.5) * 1.0，范围 -0.5 ~ +0.5
        compliance_modifier = (compliance_rate - 0.5) * 1.0

        # 8. 【新增】过度干预惩罚：好了还严管 → 不高兴
        overintervention_penalty = Scorer.calc_overintervention_penalty(
            habit_streak, health_score, intervention_count, max_intervention_level
        )

        # 汇总计算
        total_score = (
            BASE_SCORE
            + phase_base_modifier
            + frequency_modifier
            + intensity_modifier
            + reasonability_modifier
            + habit_modifier
            + autonomy_modifier
            + compliance_modifier
            + overintervention_penalty  # 新增
        )

        # 限制在1-10范围内
        final_score = max(1.0, min(10.0, total_score))

        # 返回评分明细供调试和分析
        breakdown = {
            "base_score": BASE_SCORE,
            "phase": phase,
            "phase_base_modifier": phase_base_modifier,
            "frequency_modifier": frequency_modifier,
            "intensity_modifier": intensity_modifier,
            "reasonability_modifier": reasonability_modifier,
            "habit_modifier": habit_modifier,
            "autonomy_modifier": autonomy_modifier,
            "compliance_modifier": compliance_modifier,
            "overintervention_penalty": overintervention_penalty,  # 新增
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

        # 评级
        if health_change >= 2.0:
            rating = "excellent"
            rating_cn = "优秀"
        elif health_change >= 1.0:
            rating = "good"
            rating_cn = "良好"
        elif health_change >= 0:
            rating = "neutral"
            rating_cn = "稳定"
        elif health_change >= -1.0:
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
            weights = Scorer.COMPOSITE_WEIGHTS

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

        # 评级
        if composite >= 8.0:
            rating = "A"
            rating_desc = "优秀 - 健康改善显著且用户接受度高"
        elif composite >= 6.5:
            rating = "B"
            rating_desc = "良好 - 整体效果较好，有改进空间"
        elif composite >= 5.0:
            rating = "C"
            rating_desc = "一般 - 需要调整干预策略"
        elif composite >= 3.5:
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

    @staticmethod
    def calculate_mood_score_with_discipline(
        manager_actions: List[Dict],
        day: int,
        discipline_level: str,
        health_score: float,
        cumulative_health: Optional[Dict] = None,
        habit_streak: int = 0,
        compliance_rate: float = 0.5
    ) -> Tuple[float, Dict]:
        """
        计算心情分（考虑自律程度和干预合理性）

        核心设计理念（基于会议 2026-01-23）：
        1. 自律程度影响情绪敏感度
        2. 在平台期被管会产生"天天跟防贼一样"的不满
        3. 健康分低时不被管会焦虑
        4. 考虑干预的合理性（该管的时候管，不该管的时候不管）

        Args:
            manager_actions: 管理者当日干预动作列表
            day: 当前天数
            discipline_level: 自律程度 (high/medium/low)
            health_score: 当日健康分（累积模式下是当前累积分）
            cumulative_health: 累积健康分状态 (可选)
            habit_streak: 连续自律天数
            compliance_rate: 遵从率

        Returns:
            Tuple[float, Dict]: (心情分1-10, 详细分解)
        """
        BASE_SCORE = 6.0

        # 获取自律程度参数
        try:
            disc_level = SelfDisciplineLevel(discipline_level.lower())
        except ValueError:
            disc_level = SelfDisciplineLevel.MEDIUM
        params = CumulativeHealthScorer.DISCIPLINE_PARAMS[disc_level]
        mood_sensitivity = params["mood_sensitivity"]

        breakdown = {
            "base_score": BASE_SCORE,
            "discipline_level": discipline_level,
            "mood_sensitivity": mood_sensitivity,
        }

        # 1. 干预频率影响（自律程度越高越不喜欢被频繁干预）
        intervention_count = len(manager_actions) if manager_actions else 0
        frequency_penalty = -0.5 * intervention_count * mood_sensitivity
        frequency_penalty = max(-3.0, frequency_penalty)
        breakdown["frequency_modifier"] = frequency_penalty

        # 2. 干预强度影响
        intensity_penalty = 0.0
        max_level = 0
        if manager_actions:
            for action in manager_actions:
                level = action.get("level", 0)
                max_level = max(max_level, level)
                if level == 1:
                    intensity_penalty -= 0.3 * mood_sensitivity
                elif level == 2:
                    intensity_penalty -= 0.6 * mood_sensitivity
                elif level >= 3:
                    intensity_penalty -= 1.0 * mood_sensitivity
        breakdown["intensity_modifier"] = intensity_penalty
        breakdown["max_intervention_level"] = max_level

        # 3. 平台期被管的额外惩罚（"天天跟防贼一样"）
        plateau_penalty = 0.0
        in_plateau = False
        if cumulative_health:
            in_plateau = cumulative_health.get("in_plateau", False)
            if in_plateau and max_level >= 2:
                # 在平台期被强管会非常不满
                plateau_penalty = -1.5 * mood_sensitivity
                breakdown["plateau_strict_management"] = True
        breakdown["plateau_penalty"] = plateau_penalty

        # 4. 健康分低时不被管的焦虑
        neglect_penalty = 0.0
        if health_score < 50 and intervention_count == 0:
            # 健康分很低但没人管，会焦虑
            neglect_penalty = -1.0 * mood_sensitivity
            breakdown["neglected_when_low"] = True
        elif health_score < 40 and max_level < 2:
            # 健康分危险但干预力度不够
            neglect_penalty = -0.5 * mood_sensitivity
        breakdown["neglect_penalty"] = neglect_penalty

        # 5. 干预合理性奖励
        reasonability_bonus = 0.0
        for action in (manager_actions or []):
            reasonability = action.get("reasonability", "preventive")
            if reasonability == "reasonable":
                reasonability_bonus += 0.5
            elif reasonability == "unnecessary":
                reasonability_bonus -= 0.5 * mood_sensitivity
        breakdown["reasonability_modifier"] = reasonability_bonus

        # 6. 习惯养成的正面影响
        habit_bonus = 0.0
        if habit_streak >= 14:
            habit_bonus = 1.5
        elif habit_streak >= 7:
            habit_bonus = 1.0
        elif habit_streak >= 3:
            habit_bonus = 0.5
        breakdown["habit_bonus"] = habit_bonus

        # 7. 遵从率影响
        compliance_modifier = (compliance_rate - 0.5) * 1.0
        breakdown["compliance_modifier"] = compliance_modifier

        # 8. 自然恢复期的好心情（健康在恢复）
        recovery_bonus = 0.0
        if cumulative_health:
            consecutive_good = cumulative_health.get("consecutive_good_days", 0)
            if consecutive_good >= 3 and health_score > cumulative_health.get("initial_score", 75) * 0.8:
                recovery_bonus = 0.5
                breakdown["recovery_feeling_good"] = True
        breakdown["recovery_bonus"] = recovery_bonus

        # 汇总计算
        total_score = (
            BASE_SCORE
            + frequency_penalty
            + intensity_penalty
            + plateau_penalty
            + neglect_penalty
            + reasonability_bonus
            + habit_bonus
            + compliance_modifier
            + recovery_bonus
        )

        # 限制在1-10范围内
        final_score = max(1.0, min(10.0, total_score))
        breakdown["total_before_clamp"] = total_score
        breakdown["final_score"] = final_score

        return final_score, breakdown

    @staticmethod
    def get_mood_description(score: float, discipline_level: str) -> Tuple[str, str]:
        """
        根据心情分和自律程度返回描述

        Args:
            score: 心情分 (1-10)
            discipline_level: 自律程度

        Returns:
            Tuple[str, str]: (评级, 描述)
        """
        if score >= 8.5:
            return "非常满意", "感觉被尊重和信任，管理方式恰到好处"
        elif score >= 7.0:
            return "满意", "总体认可管理方式，偶有小意见"
        elif score >= 5.5:
            return "一般", "对管理有一定意见，但可以接受"
        elif score >= 4.0:
            if discipline_level == "high":
                return "不太满意", "感觉被过度管控，希望有更多自主权"
            else:
                return "不太满意", "觉得管理要么太严要么太松"
        else:
            if discipline_level == "high":
                return "不满意", "强烈感觉不被信任，像被当贼一样防着"
            else:
                return "不满意", "对管理方式有较大抵触情绪"
