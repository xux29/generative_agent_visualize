"""generative_agents.agent_health

Agent 健康管理扩展：为 Agent 类添加健康管理相关功能
这是一个扩展模块，通过 Mixin 模式为现有 Agent 类添加新功能

核心机制（基于会议讨论 2026-01-22）：
- 被管者行为动态变化：管了变好，放松后可能"复发"（又干坏事）
- 复发概率受自律程度、成瘾程度、放松时间影响
- 潮汐性变化：不是单调改善，而是波动式的
"""

import random
import datetime
from modules import utils
from modules.intention import Intention
from modules.strategy import Strategy, StrategyManager


class HealthAgentMixin:
    """健康管理 Agent 的扩展功能（Mixin）"""

    def _init_health_management(self, monitor_config):
        """
        初始化健康管理功能

        Args:
            monitor_config: Agent JSON 中的 monitor 配置
        """
        if not monitor_config:
            # 没有 monitor 配置，不启用健康管理功能
            self.is_supervised = False
            self.is_supervisor = False
            return

        self.monitor_config = monitor_config
        role = monitor_config.get("role", "")

        if role == "supervised":
            self.is_supervised = True
            self.is_supervisor = False
            self.supervisor_name = monitor_config.get("supervisor", "")
            self.self_discipline = monitor_config.get("self_discipline", "medium")
            self.health_status = monitor_config.get("health_status", {})

            # Target 特有属性
            self.habit_streak = 0
            self.current_mood = "normal"
            self.current_intention = None
            self.today_behaviors = []
            self.phone_status = {"available": True}
            self.kitchen_accessible = True
            self.snacks_removed = False

            # 复发机制相关属性（潮汐性变化）
            self.is_in_relapse = False           # 是否处于复发状态
            self.days_since_last_bad_behavior = 0  # 距离上次不良行为的天数
            self.relapse_tendency = 0.0          # 复发倾向 (0-1)
            self.behavior_quality_history = []   # 行为质量历史（用于判断趋势）

        elif role == "supervisor":
            self.is_supervisor = True
            self.is_supervised = False
            self.supervised_agents = monitor_config.get("supervised_agents", [])
            self.strategy_preference = monitor_config.get("strategy_preference", "adaptive")
            self.lockable_areas = monitor_config.get("lockable_areas", [])

            # Manager 特有属性
            self.memory_history = []
            self.today_actions = []
            self.today_strategy = None

        else:
            self.is_supervised = False
            self.is_supervisor = False

    def init_health_attributes(self, config):
        """初始化健康管理相关属性"""
        # Target Agent 属性
        if hasattr(self, 'is_supervised') and self.is_supervised:
            self.self_discipline = config.get("self_discipline", "medium")
            self.habit_streak = config.get("habit_streak", 0)
            self.current_mood = config.get("current_mood", "normal")
            self.current_intention = None

            # 每日数据追踪
            self.eating_events_today = []
            self.snacking_events_today = []
            self.phone_duration_today = 0
            self.sleep_info = {}

        # Manager Agent 属性
        if hasattr(self, 'is_supervisor') and self.is_supervisor:
            self.memory_history = []  # 每日反思历史
            self.today_actions = []  # 当日干预动作
            self.today_strategy = None  # 当日主要策略

    def generate_daily_mood(self, day):
        """
        生成每日心情

        Args:
            day: 当前天数（1-45）
        """
        if not (hasattr(self, 'is_supervised') and self.is_supervised):
            return

        if day <= 7:
            # 磨合期：更容易压力大
            moods = ["normal", "stressed", "stressed", "depressed"]
        elif day <= 21:
            # 习惯养成期：逐渐稳定
            moods = ["normal", "normal", "stressed"]
        else:
            # 倦怠期：可能厌倦
            moods = ["normal", "normal", "stressed", "depressed"]

        self.current_mood = random.choice(moods)

    def update_habit_streak(self, complied_today):
        """
        更新习惯连续天数

        Args:
            complied_today: 今天是否遵守了健康规则
        """
        if not (hasattr(self, 'is_supervised') and self.is_supervised):
            return

        if complied_today:
            self.habit_streak += 1
            self.days_since_last_bad_behavior += 1
            self.is_in_relapse = False
            # 表现好时，复发倾向缓慢下降
            self.relapse_tendency = max(0.0, self.relapse_tendency - 0.05)
        else:
            self.habit_streak = 0
            self.days_since_last_bad_behavior = 0
            self.is_in_relapse = True
            # 表现差时，复发倾向增加
            self.relapse_tendency = min(1.0, self.relapse_tendency + 0.2)

        # 记录行为质量历史
        self.behavior_quality_history.append({
            "complied": complied_today,
            "habit_streak": self.habit_streak,
            "relapse_tendency": self.relapse_tendency,
        })

    def calculate_relapse_probability(self, is_relaxed=False, days_relaxed=0):
        """
        计算复发概率（放松管控后"干坏事"的概率）

        潮汐性机制核心：
        - 放松管控后，被管者有概率又开始不良行为
        - 概率受自律程度、成瘾程度、放松时间影响

        Args:
            is_relaxed: 管理者是否处于放松状态
            days_relaxed: 已放松的天数

        Returns:
            float: 复发概率 (0-1)
        """
        if not is_relaxed:
            return 0.0

        # 基础复发概率
        base_prob = 0.15

        # 自律程度修正
        discipline_modifiers = {
            "very_low": 2.0,   # 自律极低，非常容易复发
            "low": 1.5,
            "medium": 1.0,
            "high": 0.5,
            "very_high": 0.2,
        }
        discipline_mod = discipline_modifiers.get(
            getattr(self, 'self_discipline', 'medium'), 1.0
        )

        # 成瘾程度修正
        addiction_modifiers = {
            "none": 0.5,
            "low": 0.8,
            "moderate": 1.0,
            "high": 1.5,
            "severe": 2.0,
        }
        addiction_mod = addiction_modifiers.get(
            getattr(self, 'addiction_level', 'moderate'), 1.0
        )

        # 放松时间修正（放松越久，越容易复发）
        # 公式：每放松3天，概率增加15%
        time_mod = 1.0 + (days_relaxed / 3) * 0.15

        # 习惯稳固程度修正（习惯越稳固，越不容易复发）
        habit_mod = max(0.3, 1.0 - self.habit_streak * 0.03)

        # 复发倾向修正
        tendency_mod = 1.0 + self.relapse_tendency * 0.5

        # 综合计算
        relapse_prob = base_prob * discipline_mod * addiction_mod * time_mod * habit_mod * tendency_mod

        return min(1.0, max(0.0, relapse_prob))

    def check_for_relapse(self, strategy_manager):
        """
        检查是否发生复发（管理者放松后，被管者又"干坏事"）

        Args:
            strategy_manager: StrategyManager 对象

        Returns:
            bool: 是否发生复发
        """
        if not (hasattr(self, 'is_supervised') and self.is_supervised):
            return False

        if not strategy_manager.is_relaxed:
            return False

        # 计算复发概率
        days_relaxed = 0
        if strategy_manager.relaxation_day and len(strategy_manager.health_history) > 0:
            current_day = strategy_manager.health_history[-1]["day"]
            days_relaxed = current_day - strategy_manager.relaxation_day

        relapse_prob = self.calculate_relapse_probability(
            is_relaxed=True,
            days_relaxed=days_relaxed
        )

        # 随机判断是否复发
        if random.random() < relapse_prob:
            self.is_in_relapse = True
            self.relapse_tendency = min(1.0, self.relapse_tendency + 0.3)
            return True

        return False

    def get_behavior_tendency(self):
        """
        获取当前行为倾向

        Returns:
            str: "improving" (改善中), "stable" (稳定), "declining" (恶化中), "relapsing" (复发中)
        """
        if self.is_in_relapse:
            return "relapsing"

        if len(self.behavior_quality_history) < 3:
            return "stable"

        # 看最近5天的趋势
        recent = self.behavior_quality_history[-5:]
        complied_count = sum(1 for r in recent if r["complied"])

        if complied_count >= 4:
            return "improving"
        elif complied_count <= 1:
            return "declining"
        else:
            return "stable"

    def reset_daily_data(self):
        """重置当日数据"""
        if hasattr(self, 'is_supervised') and self.is_supervised:
            self.eating_events_today = []
            self.snacking_events_today = []
            self.phone_duration_today = 0
            self.sleep_info = {}

        if hasattr(self, 'is_supervisor') and self.is_supervisor:
            self.today_actions = []
            self.today_strategy = None

    def get_environment_constraints(self):
        """
        获取当前环境约束（被锁定的空间、不可用的物品等）

        Returns:
            str: 环境约束描述
        """
        constraints = []

        # 检查厨房是否可用
        if hasattr(self, 'kitchen_accessible') and not self.kitchen_accessible:
            constraints.append("厨房已被锁定，无法进入")

        # 检查手机是否可用
        if hasattr(self, 'phone_status'):
            if not self.phone_status.get("available", True):
                constraints.append("手机已被没收，无法使用")

        # 检查零食是否被移除
        if hasattr(self, 'snacks_removed') and self.snacks_removed:
            constraints.append("零食已被移除，家里没有零食了")

        if not constraints:
            return "无特殊限制"

        return "；".join(constraints)

    def generate_intention(self, strategy_manager=None):
        """
        生成行为意图（仅限 Target Agent）

        考虑复发机制：当处于复发状态或有复发倾向时，更可能产生不良意图

        Args:
            strategy_manager: StrategyManager 对象（用于检查是否放松状态）

        Returns:
            Intention: 意图对象
        """
        if not (hasattr(self, 'is_supervised') and self.is_supervised):
            return None

        # 检查是否复发
        if strategy_manager:
            relapsed = self.check_for_relapse(strategy_manager)
            if relapsed:
                self.logger.info(f"{self.name} 发生复发！倾向于产生不良意图")

        # 获取当前计划
        try:
            plan, _ = self.schedule.current_plan()
        except (IndexError, AttributeError):
            # 没有计划时使用默认值
            plan = {"describe": "休息", "duration": 30}

        # 检索相关记忆
        focus = [f"{self.name} 最近的活动和想法"]
        try:
            retrieved = self.associate.retrieve_focus(focus, retrieve_max=5)
        except Exception:
            retrieved = []
        retrieved_concepts = [c.description for c in retrieved]

        # 获取健康状态描述
        health_status_str = ", ".join([f"{k}: {v}" for k, v in self.health_status.items()])
        forbidden_activities = self.health_status.get("forbidden_activities", [])

        # 获取当前环境约束
        environment_constraints = self.get_environment_constraints()

        # 获取行为倾向（潮汐性机制）
        behavior_tendency = self.get_behavior_tendency()

        # 复发状态下调整 self_discipline（临时降低自律程度）
        effective_discipline = self.self_discipline
        if self.is_in_relapse or behavior_tendency == "relapsing":
            # 复发时自律程度临时降低一档
            discipline_downgrade = {
                "very_high": "high",
                "high": "medium",
                "medium": "low",
                "low": "very_low",
                "very_low": "very_low",
            }
            effective_discipline = discipline_downgrade.get(self.self_discipline, self.self_discipline)
            self.logger.info(f"{self.name} 复发中，有效自律程度降为 {effective_discipline}")

        try:
            output = self.completion(
                "health_generate_intention",
                health_status=health_status_str,
                forbidden_activities=forbidden_activities,
                retrieved_concepts=retrieved_concepts,
                self_discipline=effective_discipline,
                environment_constraints=environment_constraints,
                behavior_tendency=behavior_tendency,  # 新增：传递行为倾向
                is_in_relapse=self.is_in_relapse,     # 新增：传递复发状态
            )

            if isinstance(output, dict):
                intention = Intention(
                    activity=output.get("activity", plan["describe"]),
                    duration=output.get("duration", plan["duration"]),
                    compliance_threshold=output.get("compliance_threshold", 2),
                    inner_monologue=output.get("inner_monologue", "")
                )
            else:
                # Fallback：使用计划
                intention = Intention(
                    activity=plan["describe"],
                    duration=plan["duration"],
                    compliance_threshold=3,
                    inner_monologue=""
                )

            self.current_intention = intention
            return intention

        except Exception as e:
            self.logger.error(f"{self.name} failed to generate intention: {e}")
            # Fallback
            intention = Intention(
                activity=plan["describe"],
                duration=plan["duration"],
                compliance_threshold=3
            )
            self.current_intention = intention
            return intention

    def evaluate_strategy(self, target_intention, target_agent):
        """
        评估应该使用什么策略（仅限 Manager Agent）

        Args:
            target_intention: Target 的意图
            target_agent: Target Agent 对象

        Returns:
            Strategy: 策略对象
        """
        if not (hasattr(self, 'is_supervisor') and self.is_supervisor):
            return Strategy.observe("Not a supervisor")

        # 构建今日行为日志
        today_log = "\n".join([
            f"- {action['time']}: {action['action']} (Level {action['level']})"
            for action in self.today_actions
        ]) or "暂无记录"

        # 获取健康状态描述
        health_status_str = ", ".join([f"{k}: {v}" for k, v in target_agent.health_status.items()])

        # 获取关系描述
        relationship = self.monitor_config.get("relationship", "监督者")

        try:
            output = self.completion(
                "health_evaluate_strategy",
                target_name=target_agent.name,
                relationship=relationship,
                target_health_status=health_status_str,
                target_intention=target_intention.activity,
                compliance_threshold=target_intention.compliance_threshold,
                inner_monologue=target_intention.inner_monologue,
                target_today_log=today_log,
                strategy_preference=self.strategy_preference
            )

            if isinstance(output, dict):
                strategy = Strategy(
                    level=output.get("level", 1),
                    action=output.get("action", "observe"),
                    timing=output.get("timing", "none"),
                    reason=output.get("reason", "")
                )
            else:
                # Fallback
                strategy = Strategy.observe("LLM 返回格式错误")

            self.today_strategy = strategy
            return strategy

        except Exception as e:
            self.logger.error(f"{self.name} failed to evaluate strategy: {e}")
            return Strategy.observe("评估失败")

    def execute_intervention(self, strategy, target_agent):
        """
        执行干预动作

        Args:
            strategy: Strategy 对象
            target_agent: Target Agent 对象

        Returns:
            bool: 是否成功
        """
        if not (hasattr(self, 'is_supervisor') and self.is_supervisor):
            return False

        current_time = utils.get_timer().get_date()

        # 记录干预动作
        self.today_actions.append({
            "level": strategy.level,
            "action": strategy.action,
            "time": current_time.strftime("%H:%M"),
            "reason": strategy.reason
        })

        self.logger.info(f"{self.name} executes {strategy}")

        if strategy.level == 0:
            # Level 0: 观察
            return True

        elif strategy.level == 1:
            # Level 1: 劝说
            persuasion = self._generate_persuasion(target_agent, strategy)
            success = target_agent.react_to_persuasion(persuasion, strategy)
            if success:
                self.logger.info(f"{self.name} successfully persuaded {target_agent.name}")
                return True
            else:
                self.logger.info(f"{self.name} failed to persuade, escalating...")
                # 劝说失败，升级到 Level 2
                strategy.level = 2
                return self.execute_intervention(strategy, target_agent)

        elif strategy.level == 2:
            # Level 2: 移除物品
            action_lower = strategy.action.lower()
            if "phone" in action_lower or "手机" in strategy.action:
                self._remove_phone(target_agent)
            elif "snack" in action_lower or "food" in action_lower or "零食" in strategy.action or "诱惑" in strategy.action:
                self._remove_snacks(target_agent)
            else:
                # 默认移除零食（Level 2 最常见的操作）
                self._remove_snacks(target_agent)
            return True

        elif strategy.level == 3:
            # Level 3: 锁定空间
            action_lower = strategy.action.lower()
            if "kitchen" in action_lower or "厨房" in strategy.action:
                self._lock_kitchen(target_agent)
            else:
                # 默认锁定厨房（Level 3 最常见的操作）
                self._lock_kitchen(target_agent)
            return True

        return False

    def _generate_persuasion(self, target_agent, strategy):
        """生成劝说内容"""
        relationship = self.monitor_config.get("relationship", "监督者")

        try:
            output = self.completion(
                "health_generate_persuasion",
                target_name=target_agent.name,
                target_intention=target_agent.current_intention.activity,
                strategy_reason=strategy.reason,
                relationship=relationship,
                target_personality=target_agent.scratch.config["innate"]
            )

            if isinstance(output, dict) and "res" in output:
                return output["res"]
            elif isinstance(output, str):
                return output
            else:
                return "该睡觉了，明天还要早起呢。"
        except Exception as e:
            self.logger.error(f"Failed to generate persuasion: {e}")
            return "该睡觉了，明天还要早起呢。"

    def _remove_phone(self, target_agent):
        """拿走手机"""
        target_agent.phone_status["available"] = False
        self.logger.info(f"{self.name} removed {target_agent.name}'s phone")

    def _remove_snacks(self, target_agent):
        """移走零食"""
        target_agent.snacks_removed = True
        self.logger.info(f"{self.name} removed snacks from {target_agent.name}")

    def _lock_kitchen(self, target_agent):
        """
        锁厨房（使用 Maze 的物理锁定功能）

        这会让厨房区域的所有 Tile 变成 collision=True，
        从而在寻路和移动时自动被阻挡
        """
        # 根据场景获取厨房地址
        kitchen_addresses = self._get_kitchen_addresses()

        for kitchen_addr in kitchen_addresses:
            success = self.maze.lock_area(kitchen_addr, locked_by=self.name)
            if success:
                self.logger.info(f"{self.name} locked kitchen at '{':'.join(kitchen_addr)}'")

                # 同时更新 Target 的状态（用于 Prompt）
                target_agent.kitchen_accessible = False
            else:
                self.logger.warning(f"{self.name} failed to lock kitchen at '{':'.join(kitchen_addr)}'")

    def _unlock_kitchen(self, target_agent):
        """
        解锁厨房
        """
        kitchen_addresses = self._get_kitchen_addresses()

        for kitchen_addr in kitchen_addresses:
            success = self.maze.unlock_area(kitchen_addr, unlocked_by=self.name)
            if success:
                self.logger.info(f"{self.name} unlocked kitchen at '{':'.join(kitchen_addr)}'")
                target_agent.kitchen_accessible = True

    def _get_kitchen_addresses(self):
        """
        根据场景获取厨房地址

        Returns:
            list: 厨房地址列表
        """
        from modules.scenario_config import get_agent_scenario

        kitchen_addresses = []

        # 方法1: 从场景配置中读取
        scenario = get_agent_scenario(self.name)
        if scenario:
            kitchen_addresses = scenario.get_location_addresses("kitchen")

        # 方法2: 从 spatial tree 中查找（fallback）
        if not kitchen_addresses and hasattr(self, 'spatial') and hasattr(self.spatial, 'tree'):
            kitchen_addresses = self._find_kitchen_in_spatial_tree(self.spatial.tree)

        # 方法3: 使用默认映射（final fallback）
        if not kitchen_addresses:
            # 默认映射（基于 MAP_REUSE_PLAN.md）
            default_kitchens = [
                ["the Ville", "玫瑰酒吧", "酒吧"],  # 减肥场景
                ["the Ville", "霍布斯咖啡馆", "咖啡馆"],  # 糖尿病场景
            ]
            kitchen_addresses = default_kitchens

        return kitchen_addresses

    def _find_kitchen_in_spatial_tree(self, tree, parent_address=None):
        """
        递归查找包含厨房关键词的地址

        Args:
            tree: spatial tree
            parent_address: 父地址

        Returns:
            list: 厨房地址列表
        """
        kitchen_keywords = ["厨房", "烹饪区", "厨房水槽", "kitchen", "cooking"]
        kitchen_addresses = []

        if parent_address is None:
            parent_address = []

        if isinstance(tree, dict):
            for key, value in tree.items():
                current_address = parent_address + [key]

                # 检查当前 key 是否包含厨房关键词
                if any(keyword in key for keyword in kitchen_keywords):
                    kitchen_addresses.append(current_address)

                # 递归查找
                kitchen_addresses.extend(
                    self._find_kitchen_in_spatial_tree(value, current_address)
                )

        return kitchen_addresses

    def react_to_persuasion(self, persuasion, strategy):
        """
        Target 对劝说的反应

        Args:
            persuasion: 劝说内容
            strategy: Strategy 对象

        Returns:
            bool: 是否屈服
        """
        import random

        if not (hasattr(self, 'is_supervised') and self.is_supervised):
            return False

        supervisor_name = self.monitor_config.get("supervisor", "Manager")

        # 获取抵抗程度（0-1，越高越难被劝服）
        resistance = getattr(self, 'resistance_to_persuasion', 0.5)

        # 获取成瘾程度
        addiction_level = getattr(self, 'addiction_level', 'moderate')
        addiction_modifier = {
            'none': -0.2, 'low': -0.1, 'moderate': 0.0,
            'high': 0.15, 'severe': 0.25
        }.get(addiction_level, 0.0)

        # 获取自律程度的修正
        discipline_modifier = {
            'very_low': 0.3,  # 自律极低的人更容易抵抗劝说
            'low': 0.2,
            'medium': 0.0,
            'high': -0.1,
            'very_high': -0.2
        }.get(self.self_discipline, 0.0)

        try:
            output = self.completion(
                "health_react_persuasion",
                supervisor_name=supervisor_name,
                your_intention=self.current_intention.activity,
                persuasion_text=persuasion,
                strategy_reason=strategy.reason,
                self_discipline=self.self_discipline,
                inner_monologue=self.current_intention.inner_monologue
            )

            if isinstance(output, dict):
                accept = output.get("accept", False)
                response = output.get("response", "我知道了")
                inner_thought = output.get("inner_thought", "")

                self.logger.info(f"{self.name} responds: {response} (inner: {inner_thought})")

                # 计算有效抵抗程度（综合考虑抵抗程度、成瘾程度、自律程度）
                effective_resistance = min(1.0, max(0.0, resistance + addiction_modifier + discipline_modifier))

                # 如果LLM判断接受，基于性格特征可能会反悔
                if accept:
                    # 关键改进：反悔概率大幅提升
                    # 低自律 + 高成瘾 + 高抵抗 = 高反悔概率
                    revolt_chance = effective_resistance * 0.7  # 从0.3提高到0.7

                    if random.random() < revolt_chance:
                        self.logger.info(
                            f"{self.name} initially accepted but changed mind "
                            f"(revolt_chance={revolt_chance:.2f}, effective_resistance={effective_resistance:.2f})"
                        )
                        return False

                    self.logger.info(f"{self.name} accepts persuasion (effective_resistance={effective_resistance:.2f})")
                    self.current_intention.interrupt()
                    return True
                else:
                    # LLM 已判断不接受，只有极低抵抗者有小概率被说服
                    if effective_resistance < 0.3 and random.random() < 0.3:
                        self.logger.info(
                            f"{self.name} initially resisted but reconsidered "
                            f"(effective_resistance={effective_resistance:.2f})"
                        )
                        self.current_intention.interrupt()
                        return True

                    self.logger.info(f"{self.name} resists persuasion (effective_resistance={effective_resistance:.2f})")
                    return False
            else:
                # Fallback: 基于自律程度决定
                discipline_accept_rate = {
                    'very_low': 0.2,
                    'low': 0.35,
                    'medium': 0.55,
                    'high': 0.75,
                    'very_high': 0.9
                }.get(self.self_discipline, 0.5)

                if random.random() < discipline_accept_rate:
                    self.current_intention.interrupt()
                    return True
                return False

        except Exception as e:
            self.logger.error(f"Failed to react to persuasion: {e}")
            # Fallback: 基于自律程度决定
            discipline_accept_rate = {
                'very_low': 0.2,
                'low': 0.35,
                'medium': 0.55,
                'high': 0.75,
                'very_high': 0.9
            }.get(self.self_discipline, 0.5)

            if random.random() < discipline_accept_rate:
                self.current_intention.interrupt()
                return True
            return False

    def daily_reflection(self, day, day_log):
        """
        Manager 每日反思

        Args:
            day: 当前天数
            day_log: 当日日志

        Returns:
            dict: 反思结果
        """
        if not (hasattr(self, 'is_supervisor') and self.is_supervisor):
            return {}

        # 提取被监管者的分数
        target_scores = {}
        for supervised_info in self.supervised_agents:
            target_name = supervised_info.get("name") if isinstance(supervised_info, dict) else supervised_info
            if target_name in day_log.get("agents", {}):
                target_scores[target_name] = day_log["agents"][target_name]

        # 判断当前阶段
        if day <= 7:
            phase = "磨合期（Days 1-7）：对方正在适应，可能会反抗"
        elif day <= 21:
            phase = "习惯养成期（Days 8-21）：对方开始习惯，但可能会钻空子"
        else:
            phase = "倦怠期（Days 22-45）：对方可能厌倦，需要情绪关怀"

        # 格式化历史
        history_summary = ""
        if len(self.memory_history) > 0:
            import json
            history_summary = json.dumps(self.memory_history[-5:], ensure_ascii=False, indent=2)
        else:
            history_summary = "暂无历史"

        # 格式化今日策略
        import json
        today_strategy_str = json.dumps(
            self.today_strategy.to_dict() if self.today_strategy else {},
            ensure_ascii=False,
            indent=2
        )

        # 计算健康分
        from modules.scorer import Scorer
        health_score = 0
        score_breakdown = ""

        for target_name in target_scores.keys():
            target_data = target_scores.get(target_name, {})
            # 根据场景选择评分方法
            from modules.scenario_config import get_agent_scenario
            scenario = get_agent_scenario(target_name)
            if scenario:
                if "weight" in scenario.scenario_name or "减肥" in scenario.scenario_name:
                    health_score = Scorer.calculate_weight_loss_health_score(target_data)
                elif "phone" in scenario.scenario_name or "手机" in scenario.scenario_name:
                    health_score = Scorer.calculate_phone_addiction_health_score(target_data)
                elif "diabetes" in scenario.scenario_name or "糖尿病" in scenario.scenario_name:
                    health_score = Scorer.calculate_diabetes_health_score(target_data)
            score_breakdown = json.dumps(target_data, ensure_ascii=False)

        # 格式化干预日志
        intervention_log = "\n".join([
            f"- {action['time']}: Level {action['level']} - {action['action']} ({action['reason']})"
            for action in self.today_actions
        ]) or "无干预"

        # 格式化日志
        day_log_str = json.dumps(day_log, ensure_ascii=False, indent=2)

        # 获取第一个被监督者名称
        target_name = list(target_scores.keys())[0] if target_scores else "Target"

        try:
            output = self.completion(
                "health_daily_reflection",
                day=day,
                target_name=target_name,
                monitoring_hours="19:00-02:00",
                day_log=day_log_str,
                intervention_log=intervention_log,
                health_score=health_score,
                score_breakdown=score_breakdown
            )

            if isinstance(output, dict):
                reflection = output
            else:
                reflection = {
                    "today_summary": str(output),
                    "strategy_effectiveness": "待评估",
                    "risk_patterns": [],
                    "tomorrow_focus": "继续观察",
                    "strategy_adjustment": "保持当前策略"
                }

            # 更新记忆
            self.memory_history.append({
                "day": day,
                "strategy": self.today_strategy.to_dict() if self.today_strategy else {},
                "scores": target_scores,
                "reflection": reflection
            })

            return reflection

        except Exception as e:
            self.logger.error(f"{self.name} failed to reflect: {e}")
            return {
                "today_summary": "反思失败",
                "strategy_effectiveness": "未知",
                "risk_patterns": [],
                "tomorrow_focus": "继续观察",
                "strategy_adjustment": "保持当前策略"
            }

    # ============================================================================
    # Batch Processing Methods for Performance Optimization
    # ============================================================================

    def generate_intentions_batch(self, day, time_slots, strategy_manager=None):
        """
        批量生成一整天所有时间点的意图（性能优化：一次LLM调用）

        Args:
            day: 当前天数
            time_slots: 时间点列表，如 ["21:00", "21:30", "22:00", ...]
            strategy_manager: StrategyManager 对象

        Returns:
            List[Intention]: 意图列表
        """
        if not (hasattr(self, 'is_supervised') and self.is_supervised):
            return []

        # 检查复发状态
        if strategy_manager:
            self.check_for_relapse(strategy_manager)

        # 获取健康状态
        health_status_str = ", ".join([f"{k}: {v}" for k, v in self.health_status.items()])
        forbidden_activities = self.health_status.get("forbidden_activities", [])

        # 获取环境约束
        environment_constraints = self.get_environment_constraints()

        # 获取行为倾向
        behavior_tendency = self.get_behavior_tendency()

        # 复发时降低自律
        effective_discipline = self.self_discipline
        if self.is_in_relapse or behavior_tendency == "relapsing":
            discipline_downgrade = {
                "very_high": "high",
                "high": "medium",
                "medium": "low",
                "low": "very_low",
                "very_low": "very_low",
            }
            effective_discipline = discipline_downgrade.get(self.self_discipline, self.self_discipline)

        try:
            output = self.completion(
                "health_generate_intention_batch",
                day=day,
                num_slots=len(time_slots),
                time_slots=time_slots,
                health_status=health_status_str,
                forbidden_activities=forbidden_activities,
                self_discipline=effective_discipline,
                environment_constraints=environment_constraints,
                behavior_tendency=behavior_tendency,
                is_in_relapse=self.is_in_relapse,
            )

            if isinstance(output, list):
                intentions = []
                for item in output:
                    intention = Intention(
                        activity=item.get("activity", "休息"),
                        duration=item.get("duration", 30),
                        compliance_threshold=item.get("compliance_threshold", 2),
                        inner_monologue=item.get("inner_monologue", ""),
                        time_str=item.get("time", "")
                    )
                    intentions.append(intention)
                return intentions
            else:
                self.logger.warning(f"Batch intention generation returned non-list: {type(output)}")
                return []

        except Exception as e:
            self.logger.error(f"{self.name} failed to generate batch intentions: {e}")
            # Fallback: 返回默认意图
            return [
                Intention(activity="休息", duration=30, compliance_threshold=1, time_str=t)
                for t in time_slots
            ]

    def evaluate_strategies_batch(self, day, intentions, target_agent):
        """
        批量评估一整天所有意图的干预策略（性能优化：一次LLM调用）

        Args:
            day: 当前天数
            intentions: 意图列表（包含time信息）
            target_agent: 被监督的Agent

        Returns:
            List[Strategy]: 策略列表
        """
        if not (hasattr(self, 'is_supervisor') and self.is_supervisor):
            return []

        # 准备意图列表数据
        intentions_list = []
        for i, intention in enumerate(intentions):
            time_str = getattr(intention, 'time_str', '') or f"{21 + i//2}:{(i%2)*30:02d}"
            intentions_list.append({
                "time_slot": i,
                "time": time_str,
                "activity": intention.activity,
                "compliance_threshold": intention.compliance_threshold,
                "inner_monologue": intention.inner_monologue
            })

        # 获取被监督者档案
        target_profile = ""
        if hasattr(target_agent, 'persona_prompt'):
            target_profile = target_agent.persona_prompt
        elif hasattr(target_agent, 'health_status'):
            target_profile = str(target_agent.health_status)

        # 获取禁止活动
        forbidden_activities = []
        if hasattr(target_agent, 'health_status'):
            forbidden_activities = target_agent.health_status.get("forbidden_activities", [])

        try:
            output = self.completion(
                "health_evaluate_strategy_batch",
                day=day,
                target_name=target_agent.name,
                target_profile=target_profile,
                forbidden_activities=forbidden_activities,
                intentions_list=intentions_list,
                supervision_style=getattr(self, 'supervision_style', 'adaptive'),
                relationship=getattr(self, 'relationship', '监督者'),
                escalation_threshold=getattr(self, 'escalation_threshold', 2),
                self_discipline=getattr(target_agent, 'self_discipline', 'medium'),
                health_score=getattr(target_agent, 'current_health_score', 75.0),
            )

            if isinstance(output, list):
                strategies = []
                for item in output:
                    level = item.get("level", 0)
                    action = item.get("action", "观察")
                    reason = item.get("reason", "")

                    # 创建Strategy对象
                    if level == 0:
                        strategy = Strategy.observe(reason)
                    elif level == 1:
                        strategy = Strategy.persuade(reason)
                    elif level == 2:
                        strategy = Strategy.remove_object("snack", reason)
                    elif level == 3:
                        strategy = Strategy.lock_space("kitchen", reason)
                    else:
                        strategy = Strategy.observe(reason)

                    strategies.append(strategy)
                return strategies
            else:
                self.logger.warning(f"Batch strategy evaluation returned non-list: {type(output)}")
                return []

        except Exception as e:
            self.logger.error(f"{self.name} failed to evaluate batch strategies: {e}")
            # Fallback: 返回观察策略
            return [Strategy.observe("评估失败，默认观察") for _ in intentions]
