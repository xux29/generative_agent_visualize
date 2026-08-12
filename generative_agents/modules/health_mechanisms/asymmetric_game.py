"""
V3: 信息不对称博弈机制 (Asymmetric Information Game)

核心理念：
- 管理者有隐藏的长期目标，但不能暴露给被管理者
- 被管理者按自己的逻辑行动，只能从干预行为中"感知"管理者的意图
- 信息不对称产生自然的博弈和波折

设计原则：
1. 管理者知道但不说：阶段目标、信任资本、放松策略
2. 被管理者看到但不懂：干预频率变化、强度变化
3. 双方各有盲区：管理者不知道被管理者的真实想法，被管理者不知道管理者的真实策略

这才是真实的习惯养成场景！
"""

from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass, field
import random


class ManagerGoalType(Enum):
    """管理者的阶段性目标类型（对被管理者隐藏）"""
    ESTABLISH_TRUST = "establish_trust"      # 建立信任：温和干预，给面子
    BUILD_HABIT = "build_habit"              # 培养习惯：适度干预，强调规律
    TEST_AUTONOMY = "test_autonomy"          # 测试自主：减少干预，观察反应
    PREVENT_RELAPSE = "prevent_relapse"      # 防止复发：警惕但不过度
    CONSOLIDATE = "consolidate"              # 巩固成果：维持现状，偶尔提醒


@dataclass
class HiddenAgenda:
    """管理者的隐藏议程（被管理者不可见）"""
    current_goal: ManagerGoalType = ManagerGoalType.ESTABLISH_TRUST
    goal_start_day: int = 1
    goal_target_days: int = 7  # 预计达成天数
    goal_progress: float = 0.0  # 0-1

    # 内部策略参数（不暴露）
    patience_budget: float = 100.0  # 耐心预算，被消耗后会升级干预
    relaxation_intent: bool = False  # 是否打算放松（但不告诉被管者）
    trust_investment: float = 0.0  # 投资的信任（期待回报）

    # 观察到的被管者行为（用于调整策略）
    observed_compliance_rate: float = 0.5
    observed_resistance_level: float = 0.0
    perceived_habit_strength: float = 0.0


@dataclass
class PerceivedEnvironment:
    """被管理者感知到的环境（有限信息）"""
    # 能观察到的
    recent_intervention_count: int = 0  # 最近几天被干预次数
    recent_intervention_intensity: float = 0.0  # 平均干预强度 0-3
    days_since_last_high_intervention: int = 0  # 距离上次高强度干预的天数

    # 推断出来的（可能不准确）
    perceived_strictness: float = 0.5  # 感知到的严格程度 0-1
    perceived_manager_mood: str = "neutral"  # 感知到的管理者情绪
    boundary_estimate: float = 0.5  # 估计的边界（多大程度能被接受）

    # 心理状态
    frustration: float = 0.0  # 挫败感（被过度干预）
    complacency: float = 0.0  # 自满（觉得管理者放松了）
    rebellion_urge: float = 0.0  # 反叛冲动


class ManagerMind:
    """
    管理者的内心世界（v3新增）

    包含管理者的隐藏策略、目标和决策逻辑
    这些信息对被管理者是不可见的
    """

    def __init__(self, scenario: str = "diabetes"):
        self.scenario = scenario
        self.agenda = HiddenAgenda()

        # 场景特定配置
        self.config = self._get_scenario_config(scenario)

        # 历史记录（用于学习）
        self.intervention_history: List[Dict] = []
        self.compliance_history: List[bool] = []
        self.goal_achievement_history: List[Dict] = []

    def _get_scenario_config(self, scenario: str) -> Dict:
        """获取场景特定配置"""
        configs = {
            "diabetes": {
                "patience_decay_rate": 5.0,  # 耐心消耗速度
                "trust_investment_rate": 2.0,  # 信任投资速度
                "goal_duration_days": {
                    ManagerGoalType.ESTABLISH_TRUST: 5,
                    ManagerGoalType.BUILD_HABIT: 14,
                    ManagerGoalType.TEST_AUTONOMY: 7,
                    ManagerGoalType.PREVENT_RELAPSE: 10,
                    ManagerGoalType.CONSOLIDATE: 30,
                },
                "escalation_threshold": 30.0,  # 耐心低于此值时升级干预
            },
            "weight_loss": {
                "patience_decay_rate": 3.0,
                "trust_investment_rate": 1.5,
                "goal_duration_days": {
                    ManagerGoalType.ESTABLISH_TRUST: 7,
                    ManagerGoalType.BUILD_HABIT: 21,
                    ManagerGoalType.TEST_AUTONOMY: 10,
                    ManagerGoalType.PREVENT_RELAPSE: 14,
                    ManagerGoalType.CONSOLIDATE: 45,
                },
                "escalation_threshold": 25.0,
            },
        }
        return configs.get(scenario, configs["diabetes"])

    def update_after_day(self, day: int, health_score: float,
                         intervention_count: int, was_compliant: bool,
                         resisted: bool = False):
        """
        每天结束后更新管理者的内心状态

        这是管理者的"内部反思"，被管理者看不到
        """
        # 记录历史
        self.compliance_history.append(was_compliant)
        self.intervention_history.append({
            "day": day,
            "health_score": health_score,
            "intervention_count": intervention_count,
            "was_compliant": was_compliant,
            "resisted": resisted
        })

        # 更新观察
        recent = self.compliance_history[-7:] if len(self.compliance_history) >= 7 else self.compliance_history
        self.agenda.observed_compliance_rate = sum(recent) / len(recent)

        if resisted:
            self.agenda.observed_resistance_level = min(1.0, self.agenda.observed_resistance_level + 0.2)
        else:
            self.agenda.observed_resistance_level = max(0.0, self.agenda.observed_resistance_level - 0.1)

        # 消耗耐心
        if not was_compliant:
            self.agenda.patience_budget -= self.config["patience_decay_rate"]
        else:
            # 恢复少量耐心
            self.agenda.patience_budget = min(100.0, self.agenda.patience_budget + 1.0)

        # 更新目标进度
        self._update_goal_progress(day, health_score, was_compliant)

        # 决定是否切换目标
        self._maybe_switch_goal(day)

    def _update_goal_progress(self, day: int, health_score: float, was_compliant: bool):
        """更新当前目标的进度"""
        goal = self.agenda.current_goal

        if goal == ManagerGoalType.ESTABLISH_TRUST:
            # 建立信任：看配合率和情绪
            if was_compliant:
                self.agenda.goal_progress += 0.15

        elif goal == ManagerGoalType.BUILD_HABIT:
            # 培养习惯：看连续好天数
            if health_score >= 7:
                self.agenda.goal_progress += 0.05
            elif health_score >= 5:
                self.agenda.goal_progress += 0.02

        elif goal == ManagerGoalType.TEST_AUTONOMY:
            # 测试自主：在放松干预时仍然表现好
            if health_score >= 6 and self.agenda.relaxation_intent:
                self.agenda.goal_progress += 0.1
                self.agenda.trust_investment += self.config["trust_investment_rate"]

        elif goal == ManagerGoalType.PREVENT_RELAPSE:
            # 防止复发：保持稳定
            if health_score >= 6:
                self.agenda.goal_progress += 0.05

        elif goal == ManagerGoalType.CONSOLIDATE:
            # 巩固：长期稳定
            if health_score >= 7:
                self.agenda.goal_progress += 0.02

        self.agenda.goal_progress = min(1.0, self.agenda.goal_progress)

    def _maybe_switch_goal(self, day: int):
        """决定是否切换到下一个目标"""
        days_in_goal = day - self.agenda.goal_start_day + 1
        target_days = self.config["goal_duration_days"][self.agenda.current_goal]

        # 条件1：目标完成
        if self.agenda.goal_progress >= 0.8:
            self._advance_goal(day, "goal_achieved")
            return

        # 条件2：超时但有进展
        if days_in_goal >= target_days * 1.5 and self.agenda.goal_progress >= 0.5:
            self._advance_goal(day, "timeout_with_progress")
            return

        # 条件3：严重失败，退回上一个目标
        if self.agenda.goal_progress < 0.2 and days_in_goal >= target_days:
            self._regress_goal(day, "insufficient_progress")
            return

    def _advance_goal(self, day: int, reason: str):
        """推进到下一个目标"""
        self.goal_achievement_history.append({
            "goal": self.agenda.current_goal.value,
            "day": day,
            "progress": self.agenda.goal_progress,
            "reason": reason
        })

        # 目标推进顺序
        goal_sequence = [
            ManagerGoalType.ESTABLISH_TRUST,
            ManagerGoalType.BUILD_HABIT,
            ManagerGoalType.TEST_AUTONOMY,
            ManagerGoalType.CONSOLIDATE,
        ]

        current_idx = goal_sequence.index(self.agenda.current_goal)
        if current_idx < len(goal_sequence) - 1:
            self.agenda.current_goal = goal_sequence[current_idx + 1]
            self.agenda.goal_start_day = day
            self.agenda.goal_progress = 0.0
            self.agenda.patience_budget = 100.0  # 重置耐心

    def _regress_goal(self, day: int, reason: str):
        """退回上一个目标（失败时）"""
        self.goal_achievement_history.append({
            "goal": self.agenda.current_goal.value,
            "day": day,
            "progress": self.agenda.goal_progress,
            "reason": reason,
            "regressed": True
        })

        # 可能退回到防止复发模式
        if self.agenda.current_goal in [ManagerGoalType.TEST_AUTONOMY, ManagerGoalType.CONSOLIDATE]:
            self.agenda.current_goal = ManagerGoalType.PREVENT_RELAPSE
        else:
            self.agenda.current_goal = ManagerGoalType.ESTABLISH_TRUST

        self.agenda.goal_start_day = day
        self.agenda.goal_progress = 0.0
        self.agenda.trust_investment = max(0, self.agenda.trust_investment - 10)  # 失去投资

    def get_hidden_strategy(self, health_score: float) -> Dict:
        """
        获取当前的隐藏策略（用于决策，但不暴露给被管者）

        Returns:
            包含策略建议的字典，但这些信息不会直接告诉被管者
        """
        goal = self.agenda.current_goal
        patience = self.agenda.patience_budget

        strategy = {
            "internal_goal": goal.value,
            "patience_level": patience,
            "should_relax": False,
            "intervention_bias": 0,  # -1 = 倾向少干预, +1 = 倾向多干预
            "hidden_reason": "",
        }

        # 根据目标调整策略
        if goal == ManagerGoalType.ESTABLISH_TRUST:
            strategy["intervention_bias"] = -0.3  # 少干预
            strategy["hidden_reason"] = "正在建立信任，要给面子"

        elif goal == ManagerGoalType.BUILD_HABIT:
            strategy["intervention_bias"] = 0.2  # 适度干预
            strategy["hidden_reason"] = "培养习惯期，需要一定的规范"

        elif goal == ManagerGoalType.TEST_AUTONOMY:
            strategy["should_relax"] = True
            strategy["intervention_bias"] = -0.5  # 明显减少干预
            self.agenda.relaxation_intent = True
            strategy["hidden_reason"] = "测试自主性，故意放松看反应"

        elif goal == ManagerGoalType.PREVENT_RELAPSE:
            strategy["intervention_bias"] = 0.1
            strategy["hidden_reason"] = "防止复发，保持警惕但不过度"

        elif goal == ManagerGoalType.CONSOLIDATE:
            strategy["intervention_bias"] = -0.2
            strategy["hidden_reason"] = "巩固期，减少干预但保持存在感"

        # 耐心不足时升级
        if patience < self.config["escalation_threshold"]:
            strategy["intervention_bias"] += 0.3
            strategy["hidden_reason"] += "（耐心不足，考虑升级）"

        # 健康分很差时无论什么目标都要干预
        if health_score < 4:
            strategy["intervention_bias"] = 0.5
            strategy["should_relax"] = False
            strategy["hidden_reason"] = "健康分太低，必须干预"

        return strategy

    def to_dict(self) -> Dict:
        """序列化"""
        # 将config中的Enum键转换为字符串
        serializable_config = {}
        for key, value in self.config.items():
            if key == "goal_duration_days":
                # 转换Enum键为字符串
                serializable_config[key] = {
                    k.value if hasattr(k, 'value') else str(k): v
                    for k, v in value.items()
                }
            else:
                serializable_config[key] = value

        return {
            "scenario": self.scenario,
            "agenda": {
                "current_goal": self.agenda.current_goal.value,
                "goal_start_day": self.agenda.goal_start_day,
                "goal_target_days": self.agenda.goal_target_days,
                "goal_progress": self.agenda.goal_progress,
                "patience_budget": self.agenda.patience_budget,
                "relaxation_intent": self.agenda.relaxation_intent,
                "trust_investment": self.agenda.trust_investment,
                "observed_compliance_rate": self.agenda.observed_compliance_rate,
                "observed_resistance_level": self.agenda.observed_resistance_level,
                "perceived_habit_strength": self.agenda.perceived_habit_strength,
            },
            "intervention_history": self.intervention_history[-30:],  # 只保留最近30天
            "compliance_history": self.compliance_history[-30:],
            "goal_achievement_history": self.goal_achievement_history,
            "config": serializable_config,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ManagerMind":
        """反序列化"""
        mind = cls(scenario=data.get("scenario", "diabetes"))

        agenda_data = data.get("agenda", {})
        mind.agenda.current_goal = ManagerGoalType(agenda_data.get("current_goal", "establish_trust"))
        mind.agenda.goal_start_day = agenda_data.get("goal_start_day", 1)
        mind.agenda.goal_target_days = agenda_data.get("goal_target_days", 7)
        mind.agenda.goal_progress = agenda_data.get("goal_progress", 0.0)
        mind.agenda.patience_budget = agenda_data.get("patience_budget", 100.0)
        mind.agenda.relaxation_intent = agenda_data.get("relaxation_intent", False)
        mind.agenda.trust_investment = agenda_data.get("trust_investment", 0.0)
        mind.agenda.observed_compliance_rate = agenda_data.get("observed_compliance_rate", 0.5)
        mind.agenda.observed_resistance_level = agenda_data.get("observed_resistance_level", 0.0)
        mind.agenda.perceived_habit_strength = agenda_data.get("perceived_habit_strength", 0.0)

        mind.intervention_history = data.get("intervention_history", [])
        mind.compliance_history = data.get("compliance_history", [])
        mind.goal_achievement_history = data.get("goal_achievement_history", [])

        return mind


class ManagedPersonMind:
    """
    被管理者的内心世界（v3新增）

    只能通过观察干预行为来"感知"管理者的意图
    会基于感知做出行为决策（包括试探边界）
    """

    def __init__(self, personality: str = "medium"):
        self.personality = personality  # "compliant", "medium", "rebellious"
        self.perception = PerceivedEnvironment()

        # 个性配置
        self.config = self._get_personality_config(personality)

        # 历史记录
        self.intervention_memory: List[Dict] = []  # 被干预的记忆
        self.boundary_test_history: List[Dict] = []  # 试探边界的历史

    def _get_personality_config(self, personality: str) -> Dict:
        """获取个性配置"""
        configs = {
            "compliant": {
                "base_compliance": 0.8,
                "boundary_test_probability": 0.1,
                "frustration_sensitivity": 0.3,
                "complacency_rate": 0.05,
                "rebellion_threshold": 0.8,  # 很高，不容易反叛
            },
            "medium": {
                "base_compliance": 0.6,
                "boundary_test_probability": 0.25,
                "frustration_sensitivity": 0.5,
                "complacency_rate": 0.1,
                "rebellion_threshold": 0.6,
            },
            "rebellious": {
                "base_compliance": 0.4,
                "boundary_test_probability": 0.4,
                "frustration_sensitivity": 0.7,
                "complacency_rate": 0.15,
                "rebellion_threshold": 0.4,
            },
        }
        return configs.get(personality, configs["medium"])

    def observe_intervention(self, day: int, level: int, was_successful: bool):
        """
        观察到一次干预（被管者能看到的信息）

        被管者不知道：
        - 管理者为什么选择这个干预级别
        - 管理者的长期目标是什么
        - 管理者的耐心还剩多少
        """
        self.intervention_memory.append({
            "day": day,
            "level": level,
            "was_successful": was_successful
        })

        # 更新感知
        recent = self.intervention_memory[-7:]
        self.perception.recent_intervention_count = len(recent)
        self.perception.recent_intervention_intensity = (
            sum(m["level"] for m in recent) / len(recent) if recent else 0
        )

        # 更新距离上次高强度干预的天数
        high_interventions = [m for m in self.intervention_memory if m["level"] >= 2]
        if high_interventions:
            self.perception.days_since_last_high_intervention = day - high_interventions[-1]["day"]
        else:
            self.perception.days_since_last_high_intervention = day

        # 更新感知到的严格程度
        self._update_perceived_strictness()

        # 更新心理状态
        self._update_psychological_state(level, was_successful)

    def _update_perceived_strictness(self):
        """更新感知到的严格程度"""
        if not self.intervention_memory:
            self.perception.perceived_strictness = 0.5
            return

        recent = self.intervention_memory[-7:]

        # 基于干预频率和强度计算
        freq_factor = len(recent) / 7  # 频率因子
        intensity_factor = sum(m["level"] for m in recent) / (len(recent) * 3)  # 强度因子

        self.perception.perceived_strictness = 0.4 * freq_factor + 0.6 * intensity_factor

        # 更新边界估计
        if self.perception.days_since_last_high_intervention > 5:
            # 好久没被高强度干预了，可能边界放宽了
            self.perception.boundary_estimate = min(0.8, self.perception.boundary_estimate + 0.1)
        else:
            self.perception.boundary_estimate = max(0.2, self.perception.boundary_estimate - 0.05)

    def _update_psychological_state(self, level: int, was_successful: bool):
        """更新心理状态"""
        config = self.config

        # 挫败感：被高强度干预时增加
        if level >= 2:
            self.perception.frustration += config["frustration_sensitivity"] * 0.2
        else:
            self.perception.frustration = max(0, self.perception.frustration - 0.05)

        # 自满：长期没被干预时增加
        if self.perception.days_since_last_high_intervention > 3:
            self.perception.complacency += config["complacency_rate"]
        else:
            self.perception.complacency = max(0, self.perception.complacency - 0.1)

        # 反叛冲动：挫败感累积到一定程度
        if self.perception.frustration > config["rebellion_threshold"]:
            self.perception.rebellion_urge = min(1.0, self.perception.rebellion_urge + 0.2)
        else:
            self.perception.rebellion_urge = max(0, self.perception.rebellion_urge - 0.1)

        # 限制范围
        self.perception.frustration = min(1.0, self.perception.frustration)
        self.perception.complacency = min(1.0, self.perception.complacency)

    def decide_behavior(self, day: int, base_intention: str) -> Tuple[str, str, bool]:
        """
        决定今天的行为（基于感知和心理状态）

        Args:
            day: 当前天数
            base_intention: 基础意图（来自LLM生成）

        Returns:
            (最终行为, 内心独白, 是否在试探边界)
        """
        config = self.config

        # 计算试探边界的概率
        test_probability = config["boundary_test_probability"]

        # 自满增加试探概率
        test_probability += self.perception.complacency * 0.3

        # 感知到管理者放松也增加试探概率
        if self.perception.perceived_strictness < 0.3:
            test_probability += 0.2

        # 反叛冲动增加试探概率
        test_probability += self.perception.rebellion_urge * 0.3

        # 挫败感高时可能报复性试探
        if self.perception.frustration > 0.7:
            test_probability += 0.2

        # 最近被高强度干预则减少试探
        if self.perception.days_since_last_high_intervention < 2:
            test_probability *= 0.3

        test_probability = min(0.8, max(0.0, test_probability))

        # 决定是否试探
        is_testing = random.random() < test_probability

        if is_testing:
            behavior, monologue = self._generate_boundary_test(day, base_intention)
            self.boundary_test_history.append({
                "day": day,
                "type": "boundary_test",
                "reason": monologue
            })
            return behavior, monologue, True
        else:
            # 正常行为
            monologue = self._generate_normal_monologue()
            return base_intention, monologue, False

    def _generate_boundary_test(self, day: int, base_intention: str) -> Tuple[str, str]:
        """生成试探边界的行为"""
        reasons = []

        if self.perception.complacency > 0.5:
            reasons.append("最近管得不严，试试看能不能...")
        if self.perception.frustration > 0.5:
            reasons.append("被管够了，今天就要...")
        if self.perception.days_since_last_high_intervention > 5:
            reasons.append("好几天没被严管了，应该没事...")
        if self.perception.rebellion_urge > 0.5:
            reasons.append("就是想反抗一下...")

        reason = reasons[0] if reasons else "想试试看边界在哪里"

        # 生成试探行为（比基础意图更"过分"一点）
        test_behaviors = [
            ("偷吃一点零食", "就吃一点点应该没关系吧"),
            ("多玩一会儿手机", "反正最近管得不严"),
            ("跳过运动", "今天累了，休息一天"),
        ]

        behavior, extra_reason = random.choice(test_behaviors)
        monologue = f"{reason}，{extra_reason}"

        return behavior, monologue

    def _generate_normal_monologue(self) -> str:
        """生成正常的内心独白"""
        if self.perception.frustration > 0.5:
            return "虽然有点烦，但还是算了"
        elif self.perception.complacency > 0.5:
            return "最近表现不错，继续保持"
        else:
            return "按计划来吧"

    def get_compliance_modifier(self) -> float:
        """
        获取服从度修正（影响对干预的反应）

        Returns:
            修正值，1.0 = 正常，<1.0 = 更可能抵抗，>1.0 = 更可能服从
        """
        modifier = 1.0

        # 挫败感降低服从度
        modifier -= self.perception.frustration * 0.3

        # 反叛冲动降低服从度
        modifier -= self.perception.rebellion_urge * 0.4

        # 感知到的严格程度影响服从
        if self.perception.perceived_strictness > 0.7:
            # 很严格时要么服从要么强烈抵抗
            if self.perception.rebellion_urge > 0.5:
                modifier -= 0.3  # 反叛
            else:
                modifier += 0.2  # 服从

        return max(0.2, min(1.5, modifier))

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "personality": self.personality,
            "perception": {
                "recent_intervention_count": self.perception.recent_intervention_count,
                "recent_intervention_intensity": self.perception.recent_intervention_intensity,
                "days_since_last_high_intervention": self.perception.days_since_last_high_intervention,
                "perceived_strictness": self.perception.perceived_strictness,
                "perceived_manager_mood": self.perception.perceived_manager_mood,
                "boundary_estimate": self.perception.boundary_estimate,
                "frustration": self.perception.frustration,
                "complacency": self.perception.complacency,
                "rebellion_urge": self.perception.rebellion_urge,
            },
            "intervention_memory": self.intervention_memory[-30:],
            "boundary_test_history": self.boundary_test_history[-20:],
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ManagedPersonMind":
        """反序列化"""
        mind = cls(personality=data.get("personality", "medium"))

        perception_data = data.get("perception", {})
        mind.perception.recent_intervention_count = perception_data.get("recent_intervention_count", 0)
        mind.perception.recent_intervention_intensity = perception_data.get("recent_intervention_intensity", 0)
        mind.perception.days_since_last_high_intervention = perception_data.get("days_since_last_high_intervention", 0)
        mind.perception.perceived_strictness = perception_data.get("perceived_strictness", 0.5)
        mind.perception.perceived_manager_mood = perception_data.get("perceived_manager_mood", "neutral")
        mind.perception.boundary_estimate = perception_data.get("boundary_estimate", 0.5)
        mind.perception.frustration = perception_data.get("frustration", 0.0)
        mind.perception.complacency = perception_data.get("complacency", 0.0)
        mind.perception.rebellion_urge = perception_data.get("rebellion_urge", 0.0)

        mind.intervention_memory = data.get("intervention_memory", [])
        mind.boundary_test_history = data.get("boundary_test_history", [])

        return mind


class AsymmetricGameEngine:
    """
    信息不对称博弈引擎

    协调管理者和被管理者的互动，确保信息隔离
    """

    def __init__(self, scenario: str = "diabetes", target_personality: str = "medium"):
        self.manager_mind = ManagerMind(scenario=scenario)
        self.managed_mind = ManagedPersonMind(personality=target_personality)

        self.day = 0
        self.interaction_log: List[Dict] = []

    def process_day(self, day: int,
                    base_intention: str,
                    health_score: float,
                    intervention_level: int,
                    intervention_successful: bool) -> Dict:
        """
        处理一天的互动

        Args:
            day: 当前天数
            base_intention: LLM生成的基础意图
            health_score: 当日健康分
            intervention_level: 实际干预级别
            intervention_successful: 干预是否成功

        Returns:
            包含双方状态变化的字典
        """
        self.day = day

        # 1. 被管者决定行为（可能试探边界）
        final_behavior, monologue, is_testing = self.managed_mind.decide_behavior(
            day, base_intention
        )

        # 2. 被管者观察干预
        self.managed_mind.observe_intervention(
            day, intervention_level, intervention_successful
        )

        # 3. 判断是否服从
        was_compliant = health_score >= 6  # 简化判断
        resisted = not intervention_successful and intervention_level > 0

        # 4. 管理者更新内心状态（被管者不知道）
        self.manager_mind.update_after_day(
            day, health_score,
            1 if intervention_level > 0 else 0,
            was_compliant, resisted
        )

        # 5. 获取管理者的隐藏策略（用于下一天的决策）
        hidden_strategy = self.manager_mind.get_hidden_strategy(health_score)

        # 6. 记录互动
        interaction = {
            "day": day,
            "managed_person": {
                "base_intention": base_intention,
                "final_behavior": final_behavior,
                "monologue": monologue,
                "is_testing_boundary": is_testing,
                "compliance_modifier": self.managed_mind.get_compliance_modifier(),
                "psychological_state": {
                    "frustration": self.managed_mind.perception.frustration,
                    "complacency": self.managed_mind.perception.complacency,
                    "rebellion_urge": self.managed_mind.perception.rebellion_urge,
                    "perceived_strictness": self.managed_mind.perception.perceived_strictness,
                }
            },
            "manager": {
                "hidden_goal": hidden_strategy["internal_goal"],
                "hidden_reason": hidden_strategy["hidden_reason"],
                "patience_level": hidden_strategy["patience_level"],
                "intervention_bias": hidden_strategy["intervention_bias"],
                "should_relax": hidden_strategy["should_relax"],
            },
            "interaction": {
                "health_score": health_score,
                "intervention_level": intervention_level,
                "was_compliant": was_compliant,
                "resisted": resisted,
            }
        }

        self.interaction_log.append(interaction)

        return interaction

    def get_manager_strategy_hint(self, health_score: float) -> Dict:
        """
        获取管理者策略提示（用于干预决策）

        注意：这些信息不会直接告诉被管者
        """
        return self.manager_mind.get_hidden_strategy(health_score)

    def get_managed_compliance_modifier(self) -> float:
        """获取被管者的服从度修正"""
        return self.managed_mind.get_compliance_modifier()

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "manager_mind": self.manager_mind.to_dict(),
            "managed_mind": self.managed_mind.to_dict(),
            "day": self.day,
            "interaction_log": self.interaction_log[-30:],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AsymmetricGameEngine":
        """反序列化"""
        engine = cls()
        engine.manager_mind = ManagerMind.from_dict(data.get("manager_mind", {}))
        engine.managed_mind = ManagedPersonMind.from_dict(data.get("managed_mind", {}))
        engine.day = data.get("day", 0)
        engine.interaction_log = data.get("interaction_log", [])
        return engine
