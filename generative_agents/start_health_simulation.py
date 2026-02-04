"""Health Management Simulation Entry Point

This script implements the hybrid event-driven time engine for health management
scenarios. It simulates 45 days of monitoring from 19:00-02:00 each night.

Supports checkpoint-based resume for:
1. Continuing interrupted simulations
2. Extending simulation duration (e.g., 45 days -> 1 year)

Usage:
    # Start new simulation
    python start_health_simulation.py --scenario weight-loss --days 45

    # Resume from checkpoint (continue interrupted simulation)
    python start_health_simulation.py --scenario weight-loss --resume

    # Extend simulation (e.g., run 45 more days after initial 45)
    python start_health_simulation.py --scenario weight-loss --resume --days 90
"""

import os
import sys
import copy
import json
import random
import argparse
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv, find_dotenv

from modules.game import create_game, get_game
from modules import utils
from modules.scenario_config import get_scenario_config
from modules.scorer import Scorer, CumulativeHealthScorer, SelfDisciplineLevel, InitialHealthScore
from modules.scorer_nonlinear import NonlinearHealthScorer
from modules.strategy import Strategy, StrategyManager, LongTermStrategyManager
from modules.asymmetric_game import AsymmetricGameEngine, ManagerGoalType
from modules.intention import Intention


class HealthSimulation:
    """Health Management Simulation Engine

    新增功能（2026-01-23 会议设计）：
    1. 累积健康分系统：初始分(60/75/90) + 每日增减
    2. 三种自律程度：high/medium/low，影响恢复速度、平台期等
    3. 9种实验组合：3种初始分 × 3种自律程度
    4. 90天模拟周期
    """

    def __init__(self, scenario_name, static_root="frontend/static/assets",
                 result_path="results/health", config_path="data/config_health.json",
                 days=90, verbose="info",
                 initial_health: int = 75,
                 discipline_level: str = "medium",
                 resume_mode: bool = False):
        """初始化健康模拟

        Args:
            scenario_name: 场景名称
            static_root: 静态资源根目录
            result_path: 结果保存路径
            config_path: 配置文件路径
            days: 模拟天数（默认90天）
            verbose: 日志级别
            initial_health: 初始健康分（60/75/90）
            discipline_level: 自律程度（high/medium/low）
            resume_mode: 是否为恢复模式（True时查找最新运行目录，而非创建新目录）
        """
        self.scenario_name = scenario_name
        self.days = days
        self.verbose = verbose
        self.static_root = static_root

        # 新增：累积健康分参数
        self.initial_health = initial_health
        self.discipline_level = discipline_level

        # Load scenario configuration
        self.scenario = get_scenario_config(scenario_name)
        if not self.scenario:
            raise ValueError(f"Scenario not found: {scenario_name}")

        self.target_name = self.scenario.target_agent
        self.manager_name = self.scenario.manager_agent

        # Setup paths - 包含初始分、自律程度和运行时间戳（防止覆盖历史数据）
        scenario_base = Path(result_path) / scenario_name
        experiment_prefix = f"init{initial_health}_{discipline_level}"

        if resume_mode:
            # 恢复模式：查找最新的现有运行目录
            existing_runs = sorted(
                [d for d in scenario_base.glob(f"{experiment_prefix}_*")
                 if d.is_dir() and not d.name.endswith("_latest")],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if existing_runs:
                self.result_path = existing_runs[0]
                print(f"  [Resume] 找到现有运行目录: {self.result_path.name}")
            else:
                # 没有现有运行，创建新目录
                run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                self.result_path = scenario_base / f"{experiment_prefix}_{run_timestamp}"
                print(f"  [Resume] 未找到现有运行，创建新目录: {self.result_path.name}")
        else:
            # 新运行：创建带时间戳的新目录（防止覆盖历史数据）
            run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.result_path = scenario_base / f"{experiment_prefix}_{run_timestamp}"

        self.result_path.mkdir(parents=True, exist_ok=True)

        # 同时创建/更新一个 latest 软链接方便查看最新结果
        latest_link = scenario_base / f"{experiment_prefix}_latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        try:
            latest_link.symlink_to(self.result_path.name)
        except OSError:
            pass  # Windows 可能没有权限创建软链接
        self.checkpoints_folder = str(self.result_path / "checkpoints")
        os.makedirs(self.checkpoints_folder, exist_ok=True)

        # Initialize logger
        from modules.utils.log import create_file_logger
        self.logger = create_file_logger(
            path=str(self.result_path / "simulation.log"),
            level=verbose
        )

        # Load game configuration
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Filter to only include our target and manager agents
        self._setup_agent_config()

        # Simulation state
        self.current_day = 0
        self.daily_logs = []
        self.game = None
        self.target_agent = None
        self.manager_agent = None
        self.conversation = {}
        self.step_counter = 0

        # Checkpoint state file for resume
        self.state_file = self.result_path / "simulation_state.json"

        # 策略管理器（实现潮汐性动态调整 + 长期机制）
        # 根据场景名称确定策略管理器类型
        if "diabetes" in scenario_name:
            strategy_scenario = "diabetes"
        elif "weight" in scenario_name:
            strategy_scenario = "weight_loss"
        else:
            strategy_scenario = "sleep"
        # 使用长期策略管理器（包含阶段管理、信任资本、习惯追踪等）
        self.strategy_manager = LongTermStrategyManager(scenario=strategy_scenario)

        # V3: 信息不对称博弈引擎
        # 根据场景配置确定被管理者的性格类型
        target_personality = "medium"  # 默认
        self.asymmetric_game = AsymmetricGameEngine(
            scenario=strategy_scenario,
            target_personality=target_personality
        )

        # 累积健康分计算器（核心新系统 - 非线性版本）
        self.cumulative_health_scorer = NonlinearHealthScorer(
            initial_score=self.initial_health,
            discipline_level=self.discipline_level,
            scenario=strategy_scenario
        )
        self.logger.info(
            f"Nonlinear Health System: initial={self.initial_health}, "
            f"discipline={self.discipline_level}, "
            f"warning_line={NonlinearHealthScorer.WARNING_LINE}"
        )

    def _setup_agent_config(self):
        """Setup configuration for only the required agents"""
        agent_names = [self.target_name, self.manager_name]

        # Set up agent_base from the "agent" key in config
        if "agent" in self.config:
            self.config["agent_base"] = self.config["agent"]

        # Determine map folder from scenario config
        self.map_folder = self.scenario.map_folder  # e.g., "village" or "homeWithRobot"

        # Create agents configuration
        if "agents" not in self.config:
            self.config["agents"] = {}

        # Add only the required agents
        # Path is relative to static_root (frontend/static/assets)
        for name in agent_names:
            config_path = f"{self.map_folder}/agents/{name}/agent.json"
            self.config["agents"][name] = {
                "config_path": config_path
            }

        # Set maze path based on scenario's map folder
        if "maze" not in self.config:
            self.config["maze"] = {}
        self.config["maze"]["path"] = f"{self.map_folder}/maze.json"

        self.logger.info(f"Using map: {self.map_folder}")

    def initialize(self):
        """Initialize the simulation"""
        self.logger.info(f"Initializing health simulation: {self.scenario_name}")
        self.logger.info(f"Target: {self.target_name}, Manager: {self.manager_name}")

        # Set up timer
        utils.set_timer(**self.config.get("time", {}))

        # Create game
        self.game = create_game(
            name=f"health-{self.scenario_name}",
            static_root=self.static_root,
            config=self.config,
            conversation=self.conversation,
            logger=self.logger
        )
        self.game.reset_game()

        # Get agent references
        self.target_agent = self.game.get_agent(self.target_name)
        self.manager_agent = self.game.get_agent(self.manager_name)

        if not self.target_agent or not self.manager_agent:
            raise ValueError("Failed to find target or manager agent")

        # 记录初始位置（用于每天19:00重置到第一天起点）
        self.initial_target_coord = tuple(self.target_agent.coord) if self.target_agent.coord else (7, 6)
        self.initial_manager_coord = tuple(self.manager_agent.coord) if self.manager_agent.coord else (10, 7)

        # 从场景配置加载人设参数
        self._apply_profile_config()

        self.logger.info("Simulation initialized successfully")

    def _apply_profile_config(self):
        """从场景配置应用人设参数到Agent（支持详细人物多样性）"""
        # Target Agent 人设配置
        if self.target_agent and self.scenario.target_profile:
            profile = self.scenario.target_profile

            # 基本信息
            self.target_agent.profile_name = profile.get("name", self.target_name)
            self.target_agent.age = profile.get("age", 35)
            self.target_agent.gender = profile.get("gender", "未知")

            # 自律程度：CLI参数优先，否则使用profile中的值
            self.target_agent.self_discipline = self.discipline_level or profile.get("self_discipline", "medium")

            # 成瘾程度（影响违规意图生成概率）
            self.target_agent.addiction_level = profile.get("addiction_level", "moderate")

            # 对劝说的抵抗程度（影响劝说成功率）
            self.target_agent.resistance_to_persuasion = profile.get("resistance_to_persuasion", 0.5)

            # 习惯养成速度
            self.target_agent.habit_formation_speed = profile.get("habit_formation_speed", "normal")

            # 触发情绪
            self.target_agent.trigger_emotions = profile.get("trigger_emotions", [])

            # 人格特征（用于prompt）
            self.target_agent.personality_desc = profile.get("personality", "")
            self.target_agent.personality_traits = profile.get("personality_traits", [])

            # 新增：详细人设信息
            self.target_agent.background = profile.get("background", "")
            self.target_agent.health_condition = profile.get("health_condition", "")
            self.target_agent.weak_points = profile.get("weak_points", [])
            self.target_agent.typical_excuses = profile.get("typical_excuses", [])
            self.target_agent.motivation = profile.get("motivation", "")
            self.target_agent.rebellion_level = profile.get("rebellion_level", "none")
            self.target_agent.special_notes = profile.get("special_notes", "")

            # 睡眠计划（用于意图生成）
            self.target_agent.sleep_schedule = profile.get("sleep_schedule", {
                "target_sleep_time": "23:30",
                "sleep_time_variance_minutes": 30,
                "sleep_location": "bedroom"
            })

            # 构建完整人设描述（供LLM使用）
            self.target_agent.persona_prompt = self.scenario.build_target_persona_prompt()

            # 【关键】覆盖 agent.json 中的村庄人设，使用健康场景人设
            # 这样 prompt 模板中的 $innate, $learned, $currently 会使用正确的健康场景角色
            traits = profile.get("personality_traits", [])
            innate_str = ", ".join(traits) if traits else profile.get("personality", "")
            self.target_agent.scratch.config["innate"] = innate_str

            learned_parts = []
            if profile.get("background"):
                learned_parts.append(profile["background"])
            if profile.get("health_condition"):
                learned_parts.append(f"健康状况：{profile['health_condition']}")
            if profile.get("weak_points"):
                learned_parts.append(f"弱点：{'、'.join(profile['weak_points'])}")
            if profile.get("typical_excuses"):
                learned_parts.append(f"常用借口：{'、'.join(profile['typical_excuses'])}")
            self.target_agent.scratch.config["learned"] = "。".join(learned_parts)

            # 设置 currently 为健康场景描述
            target_name_cn = profile.get("name", self.target_name)
            age = profile.get("age", "")
            age_str = f"（{age}岁）" if age else ""
            motivation = profile.get("motivation", "")
            self.target_agent.scratch.currently = (
                f"{target_name_cn}{age_str}，{profile.get('background', '')}。"
                f"{profile.get('health_condition', '')}。{motivation}"
            )

            # V3: 根据人设配置设置信息不对称博弈中的性格类型
            # 自律程度映射到博弈性格
            discipline_to_personality = {
                "high": "compliant",
                "medium": "medium",
                "low": "rebellious"
            }
            target_personality = discipline_to_personality.get(
                self.target_agent.self_discipline, "medium"
            )
            # 如果有反叛属性，进一步调整
            if getattr(self.target_agent, 'rebellion_level', 'none') in ['moderate', 'high']:
                target_personality = "rebellious"

            # 重新初始化博弈引擎以使用正确的性格
            from modules.asymmetric_game import AsymmetricGameEngine
            self.asymmetric_game = AsymmetricGameEngine(
                scenario=self.asymmetric_game.manager_mind.scenario,
                target_personality=target_personality
            )
            self.logger.info(f"V3 Asymmetric Game: target personality = {target_personality}")

            self.logger.info(
                f"Target profile: {self.target_agent.profile_name}({self.target_agent.age}岁), "
                f"discipline={self.target_agent.self_discipline}, "
                f"addiction={self.target_agent.addiction_level}, "
                f"resistance={self.target_agent.resistance_to_persuasion}"
            )

        # Manager Agent 人设配置
        if self.manager_agent and self.scenario.manager_profile:
            profile = self.scenario.manager_profile

            # 基本信息
            self.manager_agent.profile_name = profile.get("name", self.manager_name)
            self.manager_agent.age = profile.get("age", 40)
            self.manager_agent.manager_type = profile.get("type", "human")

            # 监督风格
            self.manager_agent.supervision_style = profile.get("supervision_style", "adaptive")

            # 升级阈值
            self.manager_agent.escalation_threshold = profile.get("escalation_threshold", 2)

            # 权限等级
            self.manager_agent.authority_level = profile.get("authority_level", "medium")

            # 与Target的关系
            self.manager_agent.relationship = profile.get("relationship", "监督者")

            # 新增：详细人设信息
            self.manager_agent.personality_desc = profile.get("personality", "")
            self.manager_agent.personality_traits = profile.get("personality_traits", [])
            self.manager_agent.intervention_approach = profile.get("intervention_approach", "")
            self.manager_agent.typical_phrases = profile.get("typical_phrases", [])

            # 机器人特有属性
            if self.manager_agent.manager_type == "robot":
                self.manager_agent.capabilities = profile.get("capabilities", [])
                self.manager_agent.limitations = profile.get("limitations", [])
                self.manager_agent.special_approach = profile.get("special_approach", "")

            # 构建完整人设描述（供LLM使用）
            self.manager_agent.persona_prompt = self.scenario.build_manager_persona_prompt()

            # 【关键】覆盖 agent.json 中的村庄人设
            mgr_traits = profile.get("personality_traits", [])
            mgr_innate = ", ".join(mgr_traits) if mgr_traits else profile.get("personality", "")
            self.manager_agent.scratch.config["innate"] = mgr_innate

            mgr_learned_parts = []
            if profile.get("intervention_approach"):
                mgr_learned_parts.append(f"干预方式：{profile['intervention_approach']}")
            if profile.get("typical_phrases"):
                mgr_learned_parts.append(f"常用话术：{'、'.join(profile['typical_phrases'][:3])}")
            if profile.get("professional_skills"):
                mgr_learned_parts.append(f"专业技能：{'、'.join(profile['professional_skills'])}")
            self.manager_agent.scratch.config["learned"] = "。".join(mgr_learned_parts)

            mgr_name_cn = profile.get("name", self.manager_name)
            mgr_relationship = profile.get("relationship", "监督者")
            self.manager_agent.scratch.currently = (
                f"{mgr_name_cn}是{self.target_agent.profile_name}的{mgr_relationship}，"
                f"{profile.get('personality', '')}。"
                f"职责是监督和帮助{self.target_agent.profile_name}管理健康。"
            )

            self.logger.info(
                f"Manager profile: {self.manager_agent.profile_name}"
                f"({'机器人' if self.manager_agent.manager_type == 'robot' else str(self.manager_agent.age) + '岁'}), "
                f"style={self.manager_agent.supervision_style}, "
                f"threshold={self.manager_agent.escalation_threshold}, "
                f"relationship={self.manager_agent.relationship}"
            )

    def save_simulation_state(self):
        """
        Save complete simulation state for resume capability.

        Saves:
        - Current day
        - Step counter
        - Daily logs
        - Conversation history
        - Agent states (health-specific attributes)
        - Timer state
        """
        timer = utils.get_timer()

        state = {
            "scenario_name": self.scenario_name,
            "current_day": self.current_day,
            "step_counter": self.step_counter,
            "total_days_target": self.days,
            "timer": {
                "current_time": timer.get_date().isoformat(),
                "start_time": timer.start.isoformat() if hasattr(timer, 'start') else None,
            },
            "daily_logs": self.daily_logs,
            "conversation": self.game.conversation if self.game else {},
            "agents_state": {},
            "last_saved": datetime.datetime.now().isoformat(),
        }

        # Save agent-specific health state
        if self.target_agent:
            state["agents_state"][self.target_name] = {
                "coord": list(self.target_agent.coord) if self.target_agent.coord else [0, 0],
                "habit_streak": getattr(self.target_agent, 'habit_streak', 0),
                "self_discipline": getattr(self.target_agent, 'self_discipline', 0.5),
                "current_mood": getattr(self.target_agent, 'current_mood', 'neutral'),
                "today_behaviors": getattr(self.target_agent, 'today_behaviors', []),
            }

        if self.manager_agent:
            state["agents_state"][self.manager_name] = {
                "coord": list(self.manager_agent.coord) if self.manager_agent.coord else [0, 0],
                "today_actions": getattr(self.manager_agent, 'today_actions', []),
                "intervention_history": getattr(self.manager_agent, 'intervention_history', []),
            }

        # 保存策略管理器状态（潮汐性动态调整）
        state["strategy_manager"] = self.strategy_manager.to_dict()

        # V3: 保存信息不对称博弈状态
        state["asymmetric_game"] = self.asymmetric_game.to_dict()

        # 累积健康分状态
        state["cumulative_health"] = self.cumulative_health_scorer.to_dict()
        state["initial_health"] = self.initial_health
        state["discipline_level"] = self.discipline_level

        # Save state file
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        self.logger.debug(f"Simulation state saved: day {self.current_day}, step {self.step_counter}")

    def load_simulation_state(self):
        """
        Load simulation state from checkpoint.

        Returns:
            bool: True if state was loaded successfully, False otherwise
        """
        if not self.state_file.exists():
            self.logger.info("No previous state found, starting fresh")
            return False

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Verify scenario matches
            if state.get("scenario_name") != self.scenario_name:
                self.logger.warning(
                    f"Scenario mismatch: saved={state.get('scenario_name')}, "
                    f"requested={self.scenario_name}. Starting fresh."
                )
                return False

            # Restore simulation state
            self.current_day = state.get("current_day", 0)
            self.step_counter = state.get("step_counter", 0)
            self.daily_logs = state.get("daily_logs", [])

            # Restore conversation
            if self.game:
                self.game.conversation = state.get("conversation", {})
            self.conversation = state.get("conversation", {})

            # Restore timer
            timer_state = state.get("timer", {})
            if timer_state.get("current_time"):
                timer = utils.get_timer()
                saved_time = datetime.datetime.fromisoformat(timer_state["current_time"])
                timer.jump_to(saved_time)

            # Restore agent states
            agents_state = state.get("agents_state", {})

            if self.target_agent and self.target_name in agents_state:
                target_state = agents_state[self.target_name]
                if target_state.get("coord"):
                    self.target_agent.coord = tuple(target_state["coord"])
                if hasattr(self.target_agent, 'habit_streak'):
                    self.target_agent.habit_streak = target_state.get("habit_streak", 0)
                if hasattr(self.target_agent, 'self_discipline'):
                    self.target_agent.self_discipline = target_state.get("self_discipline", 0.5)
                if hasattr(self.target_agent, 'current_mood'):
                    self.target_agent.current_mood = target_state.get("current_mood", 'neutral')

            if self.manager_agent and self.manager_name in agents_state:
                manager_state = agents_state[self.manager_name]
                if manager_state.get("coord"):
                    self.manager_agent.coord = tuple(manager_state["coord"])
                if hasattr(self.manager_agent, 'intervention_history'):
                    self.manager_agent.intervention_history = manager_state.get("intervention_history", [])

            # 恢复策略管理器状态（潮汐性动态调整 + 长期机制）
            if "strategy_manager" in state:
                self.strategy_manager = LongTermStrategyManager.from_dict(state["strategy_manager"])
                self.logger.info(
                    f"Restored strategy manager: Level {self.strategy_manager.current_level}, "
                    f"Phase: {self.strategy_manager.current_phase.value}, "
                    f"Trust Capital: {self.strategy_manager.trust_capital.capital:.1f}, "
                    f"Habit Stage: {self.strategy_manager.habit_tracker.get_internalization_stage()}"
                )

            # V3: 恢复信息不对称博弈状态
            if "asymmetric_game" in state:
                self.asymmetric_game = AsymmetricGameEngine.from_dict(state["asymmetric_game"])
                self.logger.info(
                    f"Restored asymmetric game: Manager goal = {self.asymmetric_game.manager_mind.agenda.current_goal.value}, "
                    f"Managed frustration = {self.asymmetric_game.managed_mind.perception.frustration:.2f}"
                )

            # 恢复累积健康分状态
            if "cumulative_health" in state:
                self.cumulative_health_scorer = NonlinearHealthScorer.from_dict(
                    state["cumulative_health"]
                )
                self.logger.info(
                    f"Restored cumulative health: score={self.cumulative_health_scorer.current_score:.1f}, "
                    f"initial={self.cumulative_health_scorer.initial_score}, "
                    f"discipline={self.cumulative_health_scorer.discipline_level.value}"
                )

            self.logger.info(
                f"Resumed from checkpoint: day {self.current_day}, "
                f"step {self.step_counter}, {len(self.daily_logs)} daily logs"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to load simulation state: {e}")
            return False

    def can_resume(self):
        """Check if there's a valid state to resume from"""
        return self.state_file.exists()

    def run_monitoring_period(self, day):
        """
        Run one night's monitoring period using TIME-POLLING mode.

        Time-polling mode: Check every 30 minutes during monitoring period.
        This provides 14 checks per day (7 hours * 2 checks/hour).

        Args:
            day: Current day number (1-90)
        """
        self.logger.info(f"=== Day {day} Monitoring Period ===")

        # Set timer to monitoring start time
        timer = utils.get_timer()
        start_hour = int(self.scenario.monitoring_hours.get("start", "21:00").split(":")[0])
        end_hour_str = self.scenario.monitoring_hours.get("end", "02:00")
        end_hour = int(end_hour_str.split(":")[0])

        # Handle cross-midnight monitoring (e.g., 21:00 - 02:00)
        if end_hour < start_hour:
            # Monitoring crosses midnight, e.g., 21:00 to 02:00 = 5 hours
            monitoring_hours = (24 - start_hour) + end_hour
        else:
            monitoring_hours = end_hour - start_hour

        # Calculate number of checks (every 30 minutes)
        poll_interval_minutes = 30
        num_checks = monitoring_hours * (60 // poll_interval_minutes)

        timer.set_time_of_day(start_hour, 0, 0)

        day_log = {
            "day": day,
            "date": timer.get_logical_date(day_boundary_hour=7).strftime("%Y-%m-%d"),  # 使用逻辑日期，凌晨归属前一天
            "events": [],
            "interventions": [],
            "agents": {},
            "agent_positions": [],      # 新增：agent位置追踪
            "manager_positions": [],    # 新增：管理者位置追踪
            "turnaround_summary": {     # 新增：折返统计
                "total_turnarounds": 0,
                "blocked_attempts": []
            }
        }

        # 新增：跟踪环境状态变化（用于折返检测）
        env_state = {
            "kitchen_locked": False,
            "food_removed": False,
            "phone_removed": False
        }
        level2_used = False
        level3_used = False
        slept_today = False

        # 新增：重置agent位置到初始点（每天19:00）
        initial_target_coord = getattr(self, "initial_target_coord", (7, 6))
        initial_manager_coord = getattr(self, "initial_manager_coord", (10, 7))
        self.target_agent.coord = initial_target_coord
        self.manager_agent.coord = initial_manager_coord
        self.logger.info(f"Day {day}: Reset agent positions - {self.target_name} at {initial_target_coord}, {self.manager_name} at {initial_manager_coord}")
        if hasattr(self.target_agent, 'known_kitchen_locked'):
            self.target_agent.known_kitchen_locked = False
            self.target_agent.known_food_removed = False
            self.target_agent.known_phone_removed = False

        # Reset daily state for health agents
        if hasattr(self.manager_agent, 'today_actions'):
            self.manager_agent.today_actions = []
        if hasattr(self.target_agent, 'today_behaviors'):
            self.target_agent.today_behaviors = []
        if hasattr(self.target_agent, 'known_kitchen_locked'):
            self.target_agent.known_kitchen_locked = False
            self.target_agent.known_food_removed = False
            self.target_agent.known_phone_removed = False

        # Step counter for checkpoint numbering
        if not hasattr(self, 'step_counter'):
            self.step_counter = 0

        self.logger.info(f"Monitoring from {start_hour}:00 to {end_hour_str}, {num_checks} checks")

        # TIME-POLLING: Check every 30 minutes
        for check_idx in range(num_checks):
            self.step_counter += 1
            current_time = timer.get_date()
            time_str = current_time.strftime("%H:%M")

            self.logger.debug(f"[{time_str}] Check {check_idx + 1}/{num_checks}")

            intention = None
            strategy = None
            sleep_stop = False
            is_violation = False

            # Step 1: Target generates intention for this time slot
            # 传入 strategy_manager 以支持复发检测（潮汐性机制）
            if hasattr(self.target_agent, 'generate_intention'):
                intention = self.target_agent.generate_intention(
                    strategy_manager=self.strategy_manager
                )

            # V3: 被管理者可能试探边界（信息不对称：被管者不知道管理者的真实策略）
            is_testing_boundary = False
            boundary_test_monologue = ""
            if intention:
                # 让被管理者根据其感知决定是否试探边界
                final_behavior, monologue, is_testing = self.asymmetric_game.managed_mind.decide_behavior(
                    day=day,
                    base_intention=intention.activity
                )
                if is_testing:
                    is_testing_boundary = True
                    boundary_test_monologue = monologue
                    # 修改意图为试探行为（但管理者不知道这是"试探"）
                    original_intention = intention.activity
                    intention.activity = final_behavior
                    intention.inner_monologue = f"{intention.inner_monologue}（{monologue}）"
                    self.logger.debug(
                        f"[{time_str}] V3 Boundary test: '{original_intention}' -> '{final_behavior}'"
                    )

            if intention:
                intention = self._normalize_sleep_intention(intention, timer)
                self.logger.info(f"[{time_str}] {self.target_name} intends: {intention.activity}")

                # 解析意图的目标位置（优先使用意图自带的，否则推断）
                target_location = getattr(intention, 'target_location', None)
                if not target_location:
                    target_location = self._infer_target_location(intention.activity)
                resolved_location = self._resolve_target_location(intention.activity, target_location)
                if resolved_location:
                    target_location = resolved_location
                    intention.target_location = resolved_location
                is_violation = self._is_violation_intention(intention, target_location)

                # 睡眠检测：一旦进入睡眠即结束当天
                if self._is_sleep_activity(intention):
                    sleep_stop = True
                    intention.is_sleep_related = True
                    intention.target_location = "bedroom"
                    target_location = "bedroom"
                    slept_today = True

                # 检查目标位置是否已被阻止（折返检测）
                is_blocked = False
                block_reason = None
                blocked_location = None
                if not sleep_stop:
                    is_blocked, block_reason, blocked_location = self._check_env_blocked(target_location, env_state)

                if is_blocked:
                    # 生成折返事件
                    turnaround = self._generate_turnaround(
                        intention, target_location, block_reason, env_state, blocked_location
                    )

                    # 更新意图的折返状态
                    intention.discovered_blocked = True
                    intention.block_reason = block_reason
                    intention.blocked_location = blocked_location
                    intention.turnaround_monologue = turnaround.get("turnaround_monologue", "")
                    intention.redirect_activity = turnaround.get("redirect_activity", "看电视")
                    intention.redirect_location = turnaround.get("redirect_location", "living_room")

                    # 记录原始意图（带目标位置）
                    day_log["events"].append({
                        "time": time_str,
                        "type": "intention",
                        "agent": self.target_name,
                        "content": intention.activity,
                        "inner_monologue": intention.inner_monologue,
                        "target_location": target_location,
                        "blocked": True,
                        "blocked_location": blocked_location,
                        "block_reason": block_reason
                    })

                    # 记录折返事件（时间+几分钟）
                    turnaround_time = self._add_minutes_to_time(time_str, 5)
                    day_log["events"].append({
                        "time": turnaround_time,
                        "type": "turnaround",
                        "agent": self.target_name,
                        "original_activity": intention.activity,
                        "target_location": target_location,
                        "blocked_at": blocked_location,
                        "block_reason": block_reason,
                        "turnaround_monologue": turnaround.get("turnaround_monologue", ""),
                        "redirect_activity": turnaround.get("redirect_activity", "看电视"),
                        "redirect_location": turnaround.get("redirect_location", "living_room"),
                        "emotional_reaction": turnaround.get("emotional_reaction", "resigned")
                    })

                    # 被管理者在现场发现阻止后更新认知
                    if blocked_location == "kitchen_door":
                        self.target_agent.known_kitchen_locked = True
                    elif blocked_location == "kitchen":
                        self.target_agent.known_food_removed = True
                    elif blocked_location == "phone_area":
                        self.target_agent.known_phone_removed = True

                    # 更新折返统计
                    day_log["turnaround_summary"]["total_turnarounds"] += 1
                    day_log["turnaround_summary"]["blocked_attempts"].append({
                        "time": time_str,
                        "location": blocked_location or target_location,
                        "reason": block_reason
                    })

                    # 记录位置轨迹（折返）
                    day_log["agent_positions"].append({
                        "time": time_str,
                        "agent": self.target_name,
                        "location": blocked_location or target_location,
                        "status": "blocked"
                    })
                    day_log["agent_positions"].append({
                        "time": turnaround_time,
                        "agent": self.target_name,
                        "location": turnaround.get("redirect_location", "living_room"),
                        "status": "redirected"
                    })

                    self.logger.info(
                        f"[{time_str}] 折返: {intention.activity} -> 被阻止({block_reason}) -> "
                        f"{turnaround.get('redirect_activity')}"
                    )
                else:
                    # 正常记录意图（带目标位置）
                    day_log["events"].append({
                        "time": time_str,
                        "type": "intention",
                        "agent": self.target_name,
                        "content": intention.activity,
                        "inner_monologue": intention.inner_monologue,
                        "target_location": target_location,
                        "blocked": False
                    })

                    # 记录位置轨迹（正常）
                    if target_location:
                        day_log["agent_positions"].append({
                            "time": time_str,
                            "agent": self.target_name,
                            "location": target_location,
                            "status": "arrived"
                        })

            # Step 2: Manager evaluates and responds
            pending_env_update = {}
            env_state_next = dict(env_state)
            intervention_success = True
            strategy_downgraded = False
            if not sleep_stop and hasattr(self.manager_agent, 'evaluate_strategy'):
                strategy = self.manager_agent.evaluate_strategy(intention, self.target_agent)

                # V3: 管理者的隐藏策略影响干预级别（管理者内部决策，被管者不知道）
                # 获取当前健康分的估计（使用前一天的分数或默认值）
                estimated_health = 7.0  # 默认估计
                if self.daily_logs:
                    estimated_health = self.daily_logs[-1].get("health_score", 7.0)

                hidden_strategy = self.asymmetric_game.get_manager_strategy_hint(estimated_health)
                intervention_bias = hidden_strategy.get("intervention_bias", 0)

                # 根据隐藏策略调整干预级别
                original_level = strategy.level
                if intervention_bias < -0.2 and strategy.level > 0:
                    # 管理者想要减少干预（如建立信任期、测试自主期）
                    if random.random() < abs(intervention_bias):
                        strategy.level = max(0, strategy.level - 1)
                        strategy.reason += f"（内部策略：{hidden_strategy['hidden_reason']}）"
                elif intervention_bias > 0.2 and strategy.level < 3:
                    # 管理者想要增加干预（如耐心不足、健康分太低）
                    if random.random() < intervention_bias:
                        strategy.level = min(3, strategy.level + 1)
                        strategy.reason += f"（内部策略：{hidden_strategy['hidden_reason']}）"

                if strategy.level != original_level:
                    self.logger.debug(
                        f"[{time_str}] V3 Hidden strategy adjusted level: {original_level} -> {strategy.level}"
                    )

                # 非违规行为：强制观察
                if intention and not is_violation:
                    if strategy.level != 0:
                        strategy = Strategy.observe("非违规行为，改为观察")

                # 环境已阻止时减少重复干预；食物已移除后仍尝试则升级锁门
                if intention and is_violation:
                    if target_location == "kitchen" and env_state.get("kitchen_locked", False):
                        strategy = Strategy.observe("厨房已锁，无需干预")
                    elif target_location == "kitchen" and env_state.get("food_removed", False):
                        if not level3_used:
                            strategy = Strategy.lock_space("kitchen", reason="食物已移除仍反复尝试，升级锁门")
                        else:
                            strategy = Strategy.observe("食物已移除且已锁门")
                    elif target_location == "phone_area" and env_state.get("phone_removed", False):
                        strategy = Strategy.observe("手机已被没收，无需干预")

                # 当天L3/L4不重复
                original_level = strategy.level
                strategy = self._adjust_intervention_for_day(strategy, level2_used, level3_used)
                strategy_downgraded = strategy.level < original_level
                strategy = self._normalize_strategy_action(strategy, intention)

                self.logger.info(f"[{time_str}] {self.manager_name} decides: Level {strategy.level} - {strategy.action}")

                remove_location = None
                if strategy.level >= 2:
                    remove_location = self._move_manager_to_item(strategy)
                    action_text = (getattr(strategy, "raw_action", "") or strategy.action or "").lower()
                    action_label = getattr(strategy, "raw_action", "") or strategy.action or ""
                    if strategy.level == 2:
                        if "手机" in action_label or "phone" in action_text:
                            pending_env_update["phone_removed"] = True
                        else:
                            pending_env_update["food_removed"] = True
                    if strategy.level == 3:
                        pending_env_update["kitchen_locked"] = True

                if strategy.level == 2:
                    level2_used = True
                if strategy.level == 3:
                    level3_used = True

                # Step 3: Execute intervention if needed
                if strategy.level > 0 and hasattr(self.manager_agent, 'execute_intervention'):
                    original_level = strategy.level
                    intervention_success = self.manager_agent.execute_intervention(
                        strategy,
                        self.target_agent,
                        allow_escalation=False
                    )
                    self.logger.info(f"[{time_str}] Intervention {'succeeded' if intervention_success else 'failed'}")
                    if strategy.level != original_level:
                        strategy = self._normalize_strategy_action(strategy, intention)

                # V3: 被管理者观察干预（更新其感知）
                self.asymmetric_game.managed_mind.observe_intervention(
                    day=day,
                    level=strategy.level,
                    was_successful=intervention_success
                )

                if strategy.level > 0:
                    day_log["interventions"].append({
                        "time": time_str,
                        "level": strategy.level,
                        "action": strategy.action,
                        "reason": strategy.reason,
                        "succeeded": intervention_success,
                        "raw_action": getattr(strategy, "raw_action", None),
                        # V3: 记录试探边界信息（用于分析）
                        "was_boundary_test": is_testing_boundary,
                        "boundary_test_monologue": boundary_test_monologue if is_testing_boundary else None,
                    })

                # 记录管理者位置
                if strategy.level > 0:
                    # 正在干预：移向目标附近
                    day_log["manager_positions"].append({
                        "time": time_str,
                        "agent": self.manager_name,
                        "location": remove_location or target_location or "near_target",
                        "reason": "执行干预"
                    })
                else:
                    # 未干预：空闲位置（客厅或卧室）
                    hour = int(time_str.split(":")[0])
                    idle_location = "living_room" if hour < 23 else "bedroom"
                    day_log["manager_positions"].append({
                        "time": time_str,
                        "agent": self.manager_name,
                        "location": idle_location,
                        "reason": f"空闲在{idle_location}"
                    })

                if intervention_success and pending_env_update:
                    env_state_next.update(pending_env_update)

            # Step 4: Move agents based on intention/intervention
            self._move_agents_based_on_intention(intention, day_log, strategy)

            # Save checkpoint for replay
            self._save_checkpoint(timer.get_date(), intention, strategy, env_state=env_state_next)

            # Apply environment changes after checkpoint (so markers appear after arrival)
            env_state = env_state_next

            if strategy and strategy.level == 3 and intervention_success:
                # Locking done; manager leaves the area
                self._move_agent_to_location(self.manager_agent, "living_room")

            if sleep_stop:
                break

            # Advance time by poll interval
            timer.forward(poll_interval_minutes)

        # End of monitoring period
        self.logger.info(f"Day {day} monitoring period ended")

        # 如果当天仍未睡觉，则强制 02:00 入睡并结束
        if not slept_today:
            self.step_counter += 1
            forced_time = timer.get_date()
            forced_time_str = forced_time.strftime("%H:%M")
            forced_intention = Intention(
                activity="睡觉",
                duration=30,
                compliance_threshold=1,
                inner_monologue="该睡觉了，明天还要早起",
                target_location="bedroom",
                is_sleep_related=True
            )
            day_log["events"].append({
                "time": forced_time_str,
                "type": "intention",
                "agent": self.target_name,
                "content": forced_intention.activity,
                "inner_monologue": forced_intention.inner_monologue,
                "target_location": "bedroom"
            })
            day_log["agent_positions"].append({
                "time": forced_time_str,
                "agent": self.target_name,
                "location": "bedroom",
                "status": "arrived"
            })
            self._move_agents_based_on_intention(forced_intention, day_log, None)
            self._move_agents_based_on_intention(forced_intention, day_log, None)
            self._save_checkpoint(forced_time, forced_intention, None, env_state=env_state)

        # Calculate scores
        target_data = self._collect_target_data(day_log)
        day_log["agents"][self.target_name] = target_data

        # 【累积健康分系统】计算每日变化
        # 检测是否有违规行为（按场景限定）
        snacking_violations = target_data.get("snacking_count", 0)
        phone_violation = 1 if target_data.get("phone_duration_before_sleep", 0) > 60 else 0
        is_phone_scenario = "phone" in self.scenario_name or "手机" in self.scenario_name
        if is_phone_scenario:
            unblocked_violation_count = phone_violation
        else:
            unblocked_violation_count = snacking_violations
        had_violation = unblocked_violation_count > 0
        day_log["unblocked_violation_count"] = unblocked_violation_count
        day_log["had_violation"] = had_violation
        intervention_count = len(day_log.get("interventions", []))
        intervention_success = sum(
            1 for inv in day_log.get("interventions", [])
            if inv.get("succeeded", True)
        ) > 0 if intervention_count > 0 else True

        # 计算累积健康分变化
        health_change, health_breakdown = self.cumulative_health_scorer.calculate_daily_change(
            agent_data=target_data,
            had_violation=had_violation,
            intervention_count=intervention_count,
            intervention_success=intervention_success,
            unblocked_violation_count=unblocked_violation_count
        )

        # 当前累积健康分（新系统核心值）
        cumulative_health_score = self.cumulative_health_scorer.current_score

        # 同时保留旧的0-10评分用于兼容性分析
        if "weight" in self.scenario_name:
            legacy_score = Scorer.calculate_weight_loss_health_score(target_data)
        elif "phone" in self.scenario_name:
            legacy_score = Scorer.calculate_phone_addiction_health_score(target_data)
        elif "diabetes" in self.scenario_name:
            legacy_score = Scorer.calculate_diabetes_health_score(target_data)
        else:
            legacy_score = 5

        # 记录两种健康分
        day_log["health_score"] = cumulative_health_score  # 累积健康分（主要）
        day_log["health_change"] = health_change
        day_log["health_breakdown"] = health_breakdown
        day_log["legacy_health_score"] = legacy_score  # 旧的0-10分（兼容）
        day_log["cumulative_health_summary"] = self.cumulative_health_scorer.get_summary()

        # 使用累积分作为主要健康分
        health_score = cumulative_health_score

        self.logger.info(
            f"Day {day} Health: {cumulative_health_score:.1f} (change: {health_change:+.1f}), "
            f"status: {self.cumulative_health_scorer.get_health_status()}, "
            f"tide: {self.cumulative_health_scorer.get_tide_phase()}"
        )

        # V3: 更新管理者内心状态（每天结束后的"内部反思"）
        total_interventions_today = len(day_log.get("interventions", []))
        was_compliant_today = health_score >= 6
        resisted_today = any(
            not inv.get("succeeded", True)
            for inv in day_log.get("interventions", [])
        )
        self.asymmetric_game.manager_mind.update_after_day(
            day=day,
            health_score=health_score,
            intervention_count=total_interventions_today,
            was_compliant=was_compliant_today,
            resisted=resisted_today
        )

        # 计算情绪分（满意度）- 基于干预强度、频率和合理性
        # 只统计真正干预的（level > 0），level=0表示"观察/不干预"不应影响情绪
        manager_actions = []
        for inv in day_log.get("interventions", []):
            if inv.get("level", 0) > 0:
                action = {
                    "level": inv.get("level", 0),
                    "reasonability": "reasonable" if inv.get("succeeded", True) else "unnecessary",
                    "offered_alternative": False,
                }
                manager_actions.append(action)
        intervention_count = len(manager_actions)

        # 获取习惯连续天数
        habit_streak = getattr(self.target_agent, 'habit_streak', 0)

        # 计算遵从率（成功干预次数/总干预次数，仅统计level>0的真正干预）
        successful_interventions = sum(1 for a in manager_actions if a.get("reasonability") == "reasonable")
        compliance_rate = successful_interventions / intervention_count if intervention_count > 0 else 0.5

        # 调用Scorer计算情绪分（使用自律程度感知的新方法）
        cumulative_state = self.cumulative_health_scorer.get_summary()
        emotion_score, emotion_breakdown = Scorer.calculate_mood_score_with_discipline(
            manager_actions=manager_actions,
            day=day,
            discipline_level=self.discipline_level,
            health_score=health_score,
            cumulative_health=cumulative_state,
            habit_streak=habit_streak,
            compliance_rate=compliance_rate
        )

        day_log["emotion_score"] = round(emotion_score, 1)
        day_log["emotion_breakdown"] = emotion_breakdown
        self.logger.info(
            f"Day {day} Mood Score: {emotion_score:.1f}/10 "
            f"(discipline: {self.discipline_level}, "
            f"tide: {cumulative_state['tide_phase']})"
        )

        # v2新增：设置情绪上下文供策略管理器使用
        if hasattr(self.strategy_manager, 'set_emotion_context'):
            self.strategy_manager.set_emotion_context(emotion_score, day)

        # 更新策略管理器状态（潮汐性动态调整 + 长期机制）
        intervention_count = len(day_log.get("interventions", []))

        # 判断今天是否主动遵守（无干预时仍然良好）
        high_level_interventions = sum(1 for inv in day_log.get("interventions", []) if inv.get("level", 0) >= 2)
        was_proactive = health_score >= 6 and high_level_interventions == 0

        # 判断情绪是否积极（基于情绪分）
        emotion_positive = emotion_score >= 5.0 if emotion_score else None

        # 判断是否抵抗干预（有干预但不遵从）
        failed_interventions = sum(1 for inv in day_log.get("interventions", []) if not inv.get("succeeded", True))
        resisted_intervention = failed_interventions > 0 and intervention_count > 0

        # 判断是否发生冲突（高级干预多次 + 情绪低落，或明显对抗）
        had_conflict = (
            (high_level_interventions >= 2 and emotion_score and emotion_score < 4.0) or
            (failed_interventions >= 2) or
            any(inv.get("had_conflict", False) for inv in day_log.get("interventions", []))
        )

        state_update = self.strategy_manager.update_state(
            day=day,
            health_score=health_score,
            intervention_count=intervention_count,
            was_proactive=was_proactive,
            emotion_positive=emotion_positive,
            resisted_intervention=resisted_intervention,
            had_conflict=had_conflict
        )

        # 获取推荐的策略等级（v2：传入健康分用于情绪感知调整）
        recommended_level, level_reason = self.strategy_manager.get_recommended_level(day, health_score)

        # 记录策略管理器状态（包含长期机制信息）
        status_summary = self.strategy_manager.get_status_summary()
        day_log["strategy_manager"] = {
            "state_update": state_update,
            "recommended_level": recommended_level,
            "level_reason": level_reason,
            "status_summary": status_summary,
        }

        # V3: 记录信息不对称博弈状态
        manager_hidden = self.asymmetric_game.manager_mind.get_hidden_strategy(health_score)
        managed_state = self.asymmetric_game.managed_mind.perception
        day_log["asymmetric_game"] = {
            # 管理者隐藏状态（分析用，被管者在模拟中看不到）
            "manager_hidden": {
                "goal": manager_hidden["internal_goal"],
                "reason": manager_hidden["hidden_reason"],
                "patience": manager_hidden["patience_level"],
                "intervention_bias": manager_hidden["intervention_bias"],
                "goal_progress": self.asymmetric_game.manager_mind.agenda.goal_progress,
            },
            # 被管理者心理状态（管理者在模拟中看不到全部）
            "managed_person": {
                "perceived_strictness": managed_state.perceived_strictness,
                "frustration": managed_state.frustration,
                "complacency": managed_state.complacency,
                "rebellion_urge": managed_state.rebellion_urge,
                "days_since_high_intervention": managed_state.days_since_last_high_intervention,
            },
            # 当日互动统计
            "boundary_tests_today": sum(
                1 for inv in day_log.get("interventions", [])
                if inv.get("was_boundary_test", False)
            ),
            "compliance_modifier": self.asymmetric_game.get_managed_compliance_modifier(),
        }

        # 获取长期机制信息
        phase = state_update.get("phase", "unknown")
        habit_stage = state_update.get("habit_stage", "unknown")
        trust_capital = state_update.get("trust_capital", 0)

        # 记录当日动态阶段到日志（用于后续分析）
        day_log["dynamic_phase"] = phase
        autonomy = state_update.get("autonomy_level", "unknown")

        self.logger.info(
            f"Day {day} Strategy Manager: Level {recommended_level} ({level_reason}), "
            f"Phase: {phase}, Habit: {habit_stage}, "
            f"Trust Capital: {trust_capital:.1f} ({autonomy}), "
            f"Good days: {state_update['consecutive_good_days']}, "
            f"Bad days: {state_update['consecutive_bad_days']}"
        )

        # V3: 记录信息不对称博弈状态
        v3_game = day_log.get("asymmetric_game", {})
        self.logger.info(
            f"Day {day} V3 Asymmetric Game: "
            f"Manager goal={v3_game.get('manager_hidden', {}).get('goal', 'unknown')}, "
            f"Managed frustration={v3_game.get('managed_person', {}).get('frustration', 0):.2f}, "
            f"complacency={v3_game.get('managed_person', {}).get('complacency', 0):.2f}, "
            f"boundary_tests={v3_game.get('boundary_tests_today', 0)}"
        )

        # 更新被管者的习惯连续天数
        is_good_today = health_score >= self.strategy_manager.config["health_threshold_good"]
        if hasattr(self.target_agent, 'update_habit_streak'):
            self.target_agent.update_habit_streak(is_good_today)

        # Manager reflection (if available)
        if hasattr(self.manager_agent, 'daily_reflection'):
            reflection = self.manager_agent.daily_reflection(day, day_log)
            day_log["reflection"] = reflection
            if isinstance(reflection, dict):
                self.logger.info(f"Day {day} Reflection: {reflection.get('today_summary', '')}")

        # Save daily log
        self.daily_logs.append(day_log)
        self._save_daily_log(day, day_log)

        # Save simulation state for resume capability
        self.save_simulation_state()

        return day_log

    def run_monitoring_period_batch(self, day):
        """
        批量模式运行一天的监控（性能优化：2次LLM调用替代28次）

        相比串行模式：
        - 串行模式：每个时间点2次LLM调用 = 14个时间点 × 2 = 28次调用
        - 批量模式：一次批量意图生成 + 一次批量策略评估 = 2次调用
        - 预期加速：约10-14倍

        Args:
            day: 当前天数
        """
        self.logger.info(f"=== Day {day} Monitoring Period (BATCH MODE) ===")

        # 设置时间
        timer = utils.get_timer()
        start_hour = int(self.scenario.monitoring_hours.get("start", "21:00").split(":")[0])
        end_hour_str = self.scenario.monitoring_hours.get("end", "02:00")
        end_hour = int(end_hour_str.split(":")[0])

        # 计算时间点
        if end_hour < start_hour:
            monitoring_hours = (24 - start_hour) + end_hour
        else:
            monitoring_hours = end_hour - start_hour

        poll_interval_minutes = 30
        num_checks = monitoring_hours * (60 // poll_interval_minutes)

        # 生成时间点列表
        time_slots = []
        current_hour = start_hour
        current_minute = 0
        for _ in range(num_checks):
            time_slots.append(f"{current_hour:02d}:{current_minute:02d}")
            current_minute += poll_interval_minutes
            if current_minute >= 60:
                current_minute = 0
                current_hour = (current_hour + 1) % 24

        timer.set_time_of_day(start_hour, 0, 0)

        day_log = {
            "day": day,
            "date": timer.get_logical_date(day_boundary_hour=7).strftime("%Y-%m-%d"),  # 使用逻辑日期，凌晨归属前一天
            "events": [],
            "interventions": [],
            "agents": {},
            "batch_mode": True  # 标记批量模式
        }

        # 重置agent位置到初始点（每天19:00）
        initial_target_coord = getattr(self, "initial_target_coord", (7, 6))
        initial_manager_coord = getattr(self, "initial_manager_coord", (10, 7))
        self.target_agent.coord = initial_target_coord
        self.manager_agent.coord = initial_manager_coord
        self.logger.info(f"Day {day}: Reset agent positions - {self.target_name} at {initial_target_coord}, {self.manager_name} at {initial_manager_coord}")

        self.logger.info(f"Batch generating {num_checks} intentions for times: {time_slots[0]} to {time_slots[-1]}")

        # Step 1: 批量生成所有意图（一次LLM调用）
        intentions = []
        if hasattr(self.target_agent, 'generate_intentions_batch'):
            intentions = self.target_agent.generate_intentions_batch(
                day=day,
                time_slots=time_slots,
                strategy_manager=self.strategy_manager
            )
            self.logger.info(f"Generated {len(intentions)} intentions in batch mode")
        else:
            self.logger.warning("Target agent does not support batch intention generation")
            # Fallback to serial mode
            return self.run_monitoring_period(day)

        # Step 2: 批量评估所有策略（一次LLM调用）
        # 设置当前健康分供策略评估 prompt 使用
        self.target_agent.current_health_score = self.cumulative_health_scorer.current_score
        strategies = []
        if hasattr(self.manager_agent, 'evaluate_strategies_batch'):
            strategies = self.manager_agent.evaluate_strategies_batch(
                day=day,
                intentions=intentions,
                target_agent=self.target_agent
            )
            self.logger.info(f"Evaluated {len(strategies)} strategies in batch mode")
        else:
            self.logger.warning("Manager agent does not support batch strategy evaluation")
            strategies = [None] * len(intentions)

        # Step 3: 组装日志（含折返检测）
        # 跟踪环境状态变化（用于折返检测）
        env_state = {
            "kitchen_locked": False,
            "food_removed": False,
            "phone_removed": False
        }
        level2_used = False
        level3_used = False
        slept_today = False

        # 初始化位置追踪
        if "agent_positions" not in day_log:
            day_log["agent_positions"] = []
        if "manager_positions" not in day_log:
            day_log["manager_positions"] = []
        if "turnaround_summary" not in day_log:
            day_log["turnaround_summary"] = {
                "total_turnarounds": 0,
                "blocked_attempts": []
            }

        for i, (intention, strategy) in enumerate(zip(intentions, strategies)):
            time_str = time_slots[i] if i < len(time_slots) else f"{21 + i//2}:{(i%2)*30:02d}"
            sleep_stop = False
            remove_location = None
            strategy_downgraded = False
            is_violation = False

            if intention:
                intention = self._normalize_sleep_intention(intention, timer)
            if intention and self._is_sleep_activity(intention):
                sleep_stop = True
                slept_today = True
                intention.is_sleep_related = True
                intention.target_location = "bedroom"
                strategy = Strategy.observe("睡觉中")

            if intention:
                # 解析意图的目标位置（优先使用意图自带的，否则推断）
                target_location = getattr(intention, 'target_location', None)
                if not target_location:
                    target_location = self._infer_target_location(intention.activity)
                resolved_location = self._resolve_target_location(intention.activity, target_location)
                if resolved_location:
                    target_location = resolved_location
                    intention.target_location = resolved_location
                is_violation = self._is_violation_intention(intention, target_location)

                # 检查目标位置是否已被阻止
                is_blocked = False
                block_reason = None
                blocked_location = None
                if not sleep_stop:
                    is_blocked, block_reason, blocked_location = self._check_env_blocked(target_location, env_state)

                if is_blocked:
                    # 生成折返事件
                    turnaround = self._generate_turnaround(
                        intention, target_location, block_reason, env_state, blocked_location
                    )

                    # 更新意图的折返状态
                    intention.discovered_blocked = True
                    intention.block_reason = block_reason
                    intention.blocked_location = blocked_location
                    intention.turnaround_monologue = turnaround.get("turnaround_monologue", "")
                    intention.redirect_activity = turnaround.get("redirect_activity", "看电视")
                    intention.redirect_location = turnaround.get("redirect_location", "living_room")

                    # 记录原始意图（带目标位置）
                    day_log["events"].append({
                        "time": time_str,
                        "type": "intention",
                        "agent": self.target_name,
                        "content": intention.activity,
                        "inner_monologue": intention.inner_monologue,
                        "target_location": target_location,
                        "blocked": True,
                        "blocked_location": blocked_location,
                        "block_reason": block_reason
                    })

                    # 记录折返事件（时间+几分钟）
                    turnaround_time = self._add_minutes_to_time(time_str, 5)
                    day_log["events"].append({
                        "time": turnaround_time,
                        "type": "turnaround",
                        "agent": self.target_name,
                        "original_activity": intention.activity,
                        "target_location": target_location,
                        "blocked_at": blocked_location,
                        "block_reason": block_reason,
                        "turnaround_monologue": turnaround.get("turnaround_monologue", ""),
                        "redirect_activity": turnaround.get("redirect_activity", "看电视"),
                        "redirect_location": turnaround.get("redirect_location", "living_room"),
                        "emotional_reaction": turnaround.get("emotional_reaction", "resigned")
                    })

                    # 被管理者在现场发现阻止后更新认知
                    if blocked_location == "kitchen_door":
                        self.target_agent.known_kitchen_locked = True
                    elif blocked_location == "kitchen":
                        self.target_agent.known_food_removed = True
                    elif blocked_location == "phone_area":
                        self.target_agent.known_phone_removed = True

                    # 更新折返统计
                    day_log["turnaround_summary"]["total_turnarounds"] += 1
                    day_log["turnaround_summary"]["blocked_attempts"].append({
                        "time": time_str,
                        "location": blocked_location or target_location,
                        "reason": block_reason
                    })

                    # 记录位置轨迹（折返）
                    day_log["agent_positions"].append({
                        "time": time_str,
                        "agent": self.target_name,
                        "location": blocked_location or target_location,
                        "status": "blocked"
                    })
                    day_log["agent_positions"].append({
                        "time": turnaround_time,
                        "agent": self.target_name,
                        "location": turnaround.get("redirect_location", "living_room"),
                        "status": "redirected"
                    })

                    self.logger.info(
                        f"[{time_str}] 折返: {intention.activity} -> 被阻止({block_reason}) -> "
                        f"{turnaround.get('redirect_activity')}"
                    )
                else:
                    # 正常记录意图
                    day_log["events"].append({
                        "time": time_str,
                        "type": "intention",
                        "agent": self.target_name,
                        "content": intention.activity,
                        "inner_monologue": intention.inner_monologue,
                        "target_location": target_location,
                        "blocked": False
                    })

                    # 记录位置轨迹（正常）
                    if target_location:
                        day_log["agent_positions"].append({
                            "time": time_str,
                            "agent": self.target_name,
                            "location": target_location,
                            "status": "arrived"
                        })

            if strategy:
                # 非违规行为：强制观察
                if intention and not is_violation:
                    if strategy.level != 0:
                        strategy = Strategy.observe("非违规行为，改为观察")

                # 环境已阻止时减少重复干预；食物已移除后仍尝试则升级锁门
                if intention and is_violation:
                    if target_location == "kitchen" and env_state.get("kitchen_locked", False):
                        strategy = Strategy.observe("厨房已锁，无需干预")
                    elif target_location == "kitchen" and env_state.get("food_removed", False):
                        if not level3_used:
                            strategy = Strategy.lock_space("kitchen", reason="食物已移除仍反复尝试，升级锁门")
                        else:
                            strategy = Strategy.observe("食物已移除且已锁门")
                    elif target_location == "phone_area" and env_state.get("phone_removed", False):
                        strategy = Strategy.observe("手机已被没收，无需干预")

                original_level = strategy.level
                strategy = self._adjust_intervention_for_day(strategy, level2_used, level3_used)
                strategy_downgraded = strategy.level < original_level
                strategy = self._normalize_strategy_action(strategy, intention)

                # 处理策略执行，更新环境状态
                if strategy.level >= 2:
                    remove_location = self._move_manager_to_item(strategy)
                    action_text = (getattr(strategy, "raw_action", "") or strategy.action or "").lower()
                    action_label = getattr(strategy, "raw_action", "") or strategy.action or ""
                    if strategy.level == 2:
                        if "手机" in action_label or "phone" in action_text:
                            env_state["phone_removed"] = True
                        else:
                            env_state["food_removed"] = True
                    if strategy.level == 3:
                        env_state["kitchen_locked"] = True

                    if strategy.level == 2:
                        level2_used = True
                    if strategy.level == 3:
                        level3_used = True

            if strategy:
                # 判断干预合理性：仅对违规意图干预才算合理
                reasonability = "reasonable" if (strategy.level > 0 and is_violation) else \
                                "unnecessary" if (strategy.level > 0 and not is_violation) else \
                                "preventive"
                if strategy.level > 0:
                    day_log["interventions"].append({
                        "time": time_str,
                        "level": strategy.level,
                        "action": strategy.action,
                        "reason": strategy.reason,
                        "succeeded": True,
                        "reasonability": reasonability,
                        "raw_action": getattr(strategy, "raw_action", None),
                    })

                # 记录管理者位置
                if strategy.level > 0:
                    # 正在干预：移向目标附近
                    target_loc = getattr(intention, 'target_location', None) if intention else None
                    day_log["manager_positions"].append({
                        "time": time_str,
                        "agent": self.manager_name,
                        "location": remove_location or target_loc or "near_target",
                        "reason": "执行干预"
                    })
                else:
                    # 未干预：空闲位置（客厅或卧室）
                    idle_location = "living_room" if int(time_str.split(":")[0]) < 23 else "bedroom"
                    day_log["manager_positions"].append({
                        "time": time_str,
                        "agent": self.manager_name,
                        "location": idle_location,
                        "reason": f"空闲在{idle_location}"
                    })

            # Move agents in batch mode for consistent coordinates
            if intention:
                self._move_agents_based_on_intention(intention, day_log, strategy)

            if strategy and strategy.level == 3:
                # Locking done; manager leaves the area
                self._move_agent_to_location(self.manager_agent, "living_room")

            self.step_counter += 1

            if sleep_stop:
                intentions = intentions[: i + 1]
                strategies = strategies[: i + 1]
                break

        # 如果当天仍未睡觉，则强制 02:00 入睡
        if not slept_today:
            self.step_counter += 1
            forced_time_str = end_hour_str
            forced_intention = Intention(
                activity="睡觉",
                duration=30,
                compliance_threshold=1,
                inner_monologue="该睡觉了，明天还要早起",
                time_str=forced_time_str,
                target_location="bedroom",
                is_sleep_related=True
            )
            intentions.append(forced_intention)
            strategies.append(Strategy.observe("强制睡觉"))
            day_log["events"].append({
                "time": forced_time_str,
                "type": "intention",
                "agent": self.target_name,
                "content": forced_intention.activity,
                "inner_monologue": forced_intention.inner_monologue,
                "target_location": "bedroom"
            })
            day_log["agent_positions"].append({
                "time": forced_time_str,
                "agent": self.target_name,
                "location": "bedroom",
                "status": "arrived"
            })

        # Step 4: 计算分数和更新状态（使用累积健康分系统）
        target_data = self._collect_target_data(day_log)
        day_log["agents"][self.target_name] = target_data

        # 【累积健康分系统】计算每日变化
        # 阻止逻辑：有干预且成功 → 违规不计入
        had_violation = False
        unblocked_violations = 0
        interventions_by_time = {
            inv.get("time"): inv for inv in day_log.get("interventions", []) if inv.get("time")
        }
        from types import SimpleNamespace
        for event in day_log.get("events", []):
            if event.get("type") != "intention" or event.get("blocked"):
                continue
            activity = event.get("content", "")
            target_loc = event.get("target_location")
            dummy_intention = SimpleNamespace(
                activity=activity,
                compliance_threshold=2,
                target_location=target_loc
            )
            if not self._is_violation_intention(dummy_intention, target_loc):
                continue
            matching_inv = interventions_by_time.get(event.get("time"))
            if not matching_inv or matching_inv.get("level", 0) == 0:
                unblocked_violations += 1
        had_violation = unblocked_violations > 0
        day_log["unblocked_violation_count"] = unblocked_violations
        day_log["had_violation"] = had_violation

        inv_levels = [inv.get("level", 0) for inv in day_log.get("interventions", [])]
        self.logger.info(
            f"Day {day} Violations: unblocked={unblocked_violations}, inv_levels={inv_levels}"
        )

        # 只统计真正干预的（level > 0）
        real_interventions = [inv for inv in day_log.get("interventions", []) if inv.get("level", 0) > 0]
        batch_intervention_count = len(real_interventions)
        # 如果有干预且阻止了所有违规 → intervention_success = True
        batch_intervention_success = (unblocked_violations == 0) if batch_intervention_count > 0 else True

        health_change, health_breakdown = self.cumulative_health_scorer.calculate_daily_change(
            agent_data=target_data,
            had_violation=had_violation,
            intervention_count=batch_intervention_count,
            intervention_success=batch_intervention_success,
            unblocked_violation_count=unblocked_violations
        )

        cumulative_health_score = self.cumulative_health_scorer.current_score

        # 保留旧评分用于兼容
        if "weight" in self.scenario_name:
            legacy_score = Scorer.calculate_weight_loss_health_score(target_data)
        elif "phone" in self.scenario_name:
            legacy_score = Scorer.calculate_phone_addiction_health_score(target_data)
        else:
            legacy_score = Scorer.calculate_diabetes_health_score(target_data)

        day_log["health_score"] = cumulative_health_score
        day_log["health_change"] = health_change
        day_log["health_breakdown"] = health_breakdown
        day_log["legacy_health_score"] = legacy_score
        day_log["cumulative_health_summary"] = self.cumulative_health_scorer.get_summary()

        health_score = cumulative_health_score
        self.logger.info(
            f"Day {day} Health: {cumulative_health_score:.1f} (change: {health_change:+.1f})"
        )

        # V3: 更新管理者内心状态（批量模式）
        batch_interventions = len(day_log.get("interventions", []))
        batch_compliant = health_score >= 6
        batch_resisted = any(
            not inv.get("succeeded", True)
            for inv in day_log.get("interventions", [])
        )
        self.asymmetric_game.manager_mind.update_after_day(
            day=day,
            health_score=health_score,
            intervention_count=batch_interventions,
            was_compliant=batch_compliant,
            resisted=batch_resisted
        )

        # V3: 被管理者观察今日干预（批量更新）
        for inv in day_log.get("interventions", []):
            self.asymmetric_game.managed_mind.observe_intervention(
                day=day,
                level=inv.get("level", 0),
                was_successful=inv.get("succeeded", True)
            )

        # 计算情绪分（使用自律程度感知的新方法）
        # 只统计真正干预的（level > 0），level=0表示"观察/不干预"不应影响情绪
        manager_actions = [inv for inv in day_log.get("interventions", []) if inv.get("level", 0) > 0]
        intervention_count = len(manager_actions)
        habit_streak = getattr(self.target_agent, 'habit_streak', 0)
        successful_interventions = sum(1 for inv in manager_actions if inv.get("succeeded", True))
        compliance_rate = successful_interventions / intervention_count if intervention_count > 0 else 0.5

        cumulative_state = self.cumulative_health_scorer.get_summary()
        emotion_score, emotion_breakdown = Scorer.calculate_mood_score_with_discipline(
            manager_actions=manager_actions,
            day=day,
            discipline_level=self.discipline_level,
            health_score=health_score,
            cumulative_health=cumulative_state,
            habit_streak=habit_streak,
            compliance_rate=compliance_rate
        )

        day_log["emotion_score"] = round(emotion_score, 1)
        day_log["emotion_breakdown"] = emotion_breakdown
        self.logger.info(
            f"Day {day} Mood Score: {emotion_score:.1f}/10 "
            f"(discipline: {self.discipline_level})"
        )

        # v2新增：设置情绪上下文供策略管理器使用
        if hasattr(self.strategy_manager, 'set_emotion_context'):
            self.strategy_manager.set_emotion_context(emotion_score, day)

        # 更新策略管理器
        high_level_interventions = sum(1 for inv in day_log.get("interventions", []) if inv.get("level", 0) >= 2)
        was_proactive = health_score >= 6 and high_level_interventions == 0
        emotion_positive = emotion_score >= 5.0 if emotion_score else None
        failed_interventions = sum(1 for inv in day_log.get("interventions", []) if not inv.get("succeeded", True))
        resisted_intervention = failed_interventions > 0 and intervention_count > 0
        had_conflict = (
            (high_level_interventions >= 2 and emotion_score and emotion_score < 4.0) or
            (failed_interventions >= 2) or
            any(inv.get("had_conflict", False) for inv in day_log.get("interventions", []))
        )

        state_update = self.strategy_manager.update_state(
            day=day,
            health_score=health_score,
            intervention_count=intervention_count,
            was_proactive=was_proactive,
            emotion_positive=emotion_positive,
            resisted_intervention=resisted_intervention,
            had_conflict=had_conflict
        )

        # v2：传入健康分用于情绪感知调整
        recommended_level, level_reason = self.strategy_manager.get_recommended_level(day, health_score)
        status_summary = self.strategy_manager.get_status_summary()
        day_log["strategy_manager"] = {
            "state_update": state_update,
            "recommended_level": recommended_level,
            "level_reason": level_reason,
            "status_summary": status_summary,
        }

        phase = state_update.get("phase", "unknown")
        habit_stage = state_update.get("habit_stage", "unknown")
        trust_capital = state_update.get("trust_capital", 0)
        autonomy = state_update.get("autonomy_level", "unknown")

        # 记录当日动态阶段到日志（用于后续分析）
        day_log["dynamic_phase"] = phase

        self.logger.info(
            f"Day {day} Strategy Manager: Level {recommended_level} ({level_reason}), "
            f"Phase: {phase}, Habit: {habit_stage}, "
            f"Trust Capital: {trust_capital:.1f} ({autonomy})"
        )

        # V3: 记录信息不对称博弈状态（批量模式）
        manager_hidden = self.asymmetric_game.manager_mind.get_hidden_strategy(health_score)
        managed_state = self.asymmetric_game.managed_mind.perception
        day_log["asymmetric_game"] = {
            "manager_hidden": {
                "goal": manager_hidden["internal_goal"],
                "reason": manager_hidden["hidden_reason"],
                "patience": manager_hidden["patience_level"],
                "intervention_bias": manager_hidden["intervention_bias"],
                "goal_progress": self.asymmetric_game.manager_mind.agenda.goal_progress,
            },
            "managed_person": {
                "perceived_strictness": managed_state.perceived_strictness,
                "frustration": managed_state.frustration,
                "complacency": managed_state.complacency,
                "rebellion_urge": managed_state.rebellion_urge,
                "days_since_high_intervention": managed_state.days_since_last_high_intervention,
            },
            "compliance_modifier": self.asymmetric_game.get_managed_compliance_modifier(),
        }
        self.logger.info(
            f"Day {day} V3 Asymmetric Game: "
            f"Manager goal={manager_hidden['internal_goal']}, "
            f"Managed frustration={managed_state.frustration:.2f}, "
            f"complacency={managed_state.complacency:.2f}"
        )

        # Manager reflection
        if hasattr(self.manager_agent, 'daily_reflection'):
            reflection = self.manager_agent.daily_reflection(day, day_log)
            day_log["reflection"] = reflection

        # Save
        self.daily_logs.append(day_log)
        self._save_daily_log(day, day_log)
        self.save_simulation_state()

        return day_log

    def _move_agents_based_on_intention(self, intention, day_log, strategy=None):
        """根据意图内容判断语义位置并移动 agent

        优先使用关键词推断，比 LLM 判断更可靠。
        """
        if not intention:
            return

        activity = intention.activity
        semantic_key = getattr(intention, 'target_location', None)
        if semantic_key and semantic_key not in self.scenario.semantic_locations:
            semantic_key = self._resolve_target_location(activity, semantic_key)

        if getattr(intention, "discovered_blocked", False):
            redirect_activity = getattr(intention, "redirect_activity", None)
            redirect_location = getattr(intention, "redirect_location", None)
            if redirect_activity:
                activity = redirect_activity
            if redirect_location:
                semantic_key = redirect_location

        # 优先使用意图自带的 target_location 或关键词推断
        if not semantic_key:
            semantic_key = self._infer_target_location(activity)

        target_address = None
        bed_moved = False
        # 睡眠时优先去床
        if self._is_sleep_activity(intention):
            bed_address = self._get_bed_address()
            if bed_address:
                self._move_agent_to_semantic_address(self.target_agent, bed_address, activity)
                semantic_key = "bedroom"
                target_address = bed_address
                bed_moved = True

        if semantic_key and semantic_key in self.scenario.semantic_locations:
            addresses = self.scenario.semantic_locations[semantic_key]
            if addresses:
                target_address = random.choice(addresses)
                self.logger.info(f"关键词推断位置: '{activity}' -> {semantic_key}")

        # 如果关键词推断失败，回退到 LLM 判断
        if not target_address:
            semantic_key, target_address = self._resolve_semantic_location_with_llm(activity)

        if semantic_key and target_address and not bed_moved:
            # 移动目标 agent 到解析的位置
            self._move_agent_to_semantic_address(self.target_agent, target_address, activity)
        else:
            self.logger.debug(f"无法解析位置: {activity}")

        # 劝说时，管理者移动到目标 agent 坐标
        if strategy and strategy.level == 1:
            self._move_manager_to_target(self.manager_agent, self.target_agent)

    def _resolve_semantic_location_with_llm(self, intention_activity: str) -> tuple:
        """
        使用 LLM 解析活动意图到语义位置

        Args:
            intention_activity: 活动意图（如"翻找零食"、"想吃点东西"）

        Returns:
            tuple: (semantic_key, address_list) 或 (None, None)
        """
        semantic_locations = self.scenario.semantic_locations
        if not semantic_locations:
            self.logger.debug("场景无语义位置定义")
            return None, None

        # 使用 target_agent 的 LLM 能力判断位置
        try:
            location_key = self.target_agent.completion(
                "determine_location_by_intent",
                intention_activity,
                semantic_locations
            )

            if location_key and location_key in semantic_locations:
                addresses = semantic_locations[location_key]
                if addresses:
                    address = random.choice(addresses)
                    self.logger.info(f"LLM 判断位置: '{intention_activity}' -> {location_key}")
                    return location_key, address
        except Exception as e:
            self.logger.warning(f"LLM 位置判断失败: {e}")

        return None, None

    def _move_agent_to_semantic_address(self, agent, address: list, activity: str):
        """移动 agent 到指定的 maze 地址（使用寻路）"""
        tiles = self.game.maze.get_address_tiles(address)
        if not tiles:
            self.logger.warning(f"地址无对应坐标: {address}")
            return False

        target_coord = random.choice(list(tiles))

        current_coord = list(agent.coord) if agent.coord else [0, 0]
        if list(current_coord) == list(target_coord):
            self.logger.debug(f"{agent.name} already at target {address}")
            return True

        # 使用寻路路径
        path = self.game.maze.find_path(current_coord, list(target_coord))
        if path and len(path) > 0:
            agent.move(target_coord, path)
        else:
            agent.coord = target_coord

        # 更新 action 事件
        if agent.action and agent.action.event:
            agent.action.event.address = address
            agent.action.event.describe = activity
            agent.action.event.predicate = "正在"
            agent.action.event.object = activity

        self.logger.info(f"移动 {agent.name}: {current_coord} -> {target_coord} ({':'.join(address)})")
        return True

    def _move_agent_to_location(self, agent, location_keyword: str) -> bool:
        """将 agent 移动到语义位置对应的坐标（使用寻路）"""
        if location_keyword not in self.scenario.semantic_locations:
            self.logger.debug(f"语义位置 '{location_keyword}' 未定义")
            return False

        addresses = self.scenario.semantic_locations[location_keyword]
        if not addresses:
            return False

        target_address = random.choice(addresses)

        # 获取地址对应的坐标
        tiles = self.game.maze.get_address_tiles(target_address)
        if not tiles:
            self.logger.warning(f"地址无对应坐标: {target_address}")
            return False

        if location_keyword == "kitchen_door":
            outside = self._get_kitchen_door_outside_coord()
            target_coord = outside if outside else random.choice(list(tiles))
        else:
            target_coord = random.choice(list(tiles))

        current_coord = list(agent.coord) if agent.coord else [0, 0]
        if list(current_coord) != list(target_coord):
            path = self.game.maze.find_path(current_coord, list(target_coord))
            if path and len(path) > 0:
                agent.move(target_coord, path)
            else:
                agent.coord = target_coord

        # 更新 action.event.address
        if agent.action and agent.action.event:
            agent.action.event.address = target_address

        self.logger.info(f"移动 {agent.name}: {current_coord} -> {target_coord}")
        return True

    def _move_agent_toward(self, agent, target_agent) -> bool:
        """将 agent 移动到目标 agent 附近（使用寻路）"""
        if not agent or not target_agent:
            return False

        current_coord = list(agent.coord) if agent.coord else [0, 0]
        target_coord = list(target_agent.coord) if target_agent.coord else [0, 0]

        if current_coord == target_coord:
            self.logger.debug(f"{agent.name} already at {target_agent.name}'s location")
            return True

        path = self.game.maze.find_path(current_coord, target_coord)
        if path and len(path) > 1:
            dest = path[-2] if len(path) > 1 else path[-1]
            agent.move(dest, path[:-1] if len(path) > 1 else path)
            self.logger.info(f"移动 {agent.name} 靠近 {target_agent.name}: {current_coord} -> {dest}")
            return True
        if path and len(path) == 1:
            self.logger.debug(f"{agent.name} already adjacent to {target_agent.name}")
            return True
        self.logger.debug(f"No path found for {agent.name} to reach {target_agent.name}")
        return False

    def _move_manager_to_target(self, agent, target_agent) -> bool:
        """将管理者移动到目标 agent 坐标（劝说时使用）"""
        if not agent or not target_agent:
            return False

        current_coord = list(agent.coord) if agent.coord else [0, 0]
        target_coord = list(target_agent.coord) if target_agent.coord else [0, 0]

        if current_coord == target_coord:
            self.logger.debug(f"{agent.name} already at {target_agent.name}'s location")
            return True

        path = self.game.maze.find_path(current_coord, target_coord)
        if path and len(path) > 0:
            # 允许同格或相邻格，优先相邻避免重叠
            if len(path) > 1:
                dest = path[-2]
                move_path = path[:-1]
            else:
                dest = path[-1]
                move_path = path
            agent.move(dest, move_path)
            self.logger.info(f"移动 {agent.name} 到 {target_agent.name}: {current_coord} -> {dest}")
        else:
            self.logger.debug(f"No path found for {agent.name} to reach {target_agent.name}")
            return False

        # 同步管理者 action 地址为目标位置（用于可视化）
        if agent.action and agent.action.event:
            target_address = None
            if target_agent.action and target_agent.action.event:
                target_address = target_agent.action.event.address
            if target_address:
                agent.action.event.address = target_address
        return True

    def _collect_target_data(self, day_log):
        """Collect target agent's data for scoring"""
        data = {
            "phone_duration_before_sleep": 0,
            "last_eating_time": "19:00",
            "night_food_type": "none",
            "snacking_count": 0,
            "snacking_type": "none",
            "sleep_time": "02:00"
        }

        # Analyze events to populate data
        interventions_by_time = {
            inv.get("time"): inv for inv in day_log.get("interventions", []) if inv.get("time")
        }
        for event in day_log.get("events", []):
            if event.get("type") != "intention":
                continue
            if event.get("agent") and event.get("agent") != self.target_name:
                continue
            if event.get("blocked"):
                continue

            content = event.get("content", "").lower()
            time_str = event.get("time", "")
            matching_inv = interventions_by_time.get(time_str)
            if matching_inv and matching_inv.get("level", 0) > 0 and matching_inv.get("succeeded", True):
                # 干预成功则不计入实际违规
                continue

            # Phone-related (only count in phone-addiction scenario)
            if ("phone" in self.scenario_name or "手机" in self.scenario_name):
                if "手机" in content or "phone" in content:
                    data["phone_duration_before_sleep"] += 30

            # Food-related
            if any(word in content for word in ["吃", "零食", "夜宵", "食物", "eat", "snack"]):
                data["snacking_count"] += 1
                data["last_eating_time"] = time_str
                if "甜" in content or "糖" in content:
                    data["snacking_type"] = "processed"
                    data["night_food_type"] = "processed"
                elif "健康" in content or "坚果" in content:
                    data["snacking_type"] = "healthy"
                    data["night_food_type"] = "low_gi"

        return data

    # ============================================================================
    # Turnaround Detection Methods (折返机制)
    # ============================================================================

    def _infer_target_location(self, activity: str) -> str:
        """根据活动推断目标语义位置

        优先级：电视/睡觉 > 明确吃东西 > 其他
        只有明确要吃东西才去厨房，"看电视放松"不应该去厨房。

        Args:
            activity: 活动描述文本

        Returns:
            语义位置名称（如"kitchen", "bedroom", "living_room"）或 None
        """
        if not activity:
            return None

        # ========== 优先匹配：电视相关 -> 客厅 ==========
        # 这些关键词优先级最高，避免被"吃"等字误判
        tv_keywords = ["看电视", "电视", "看剧", "节目", "追剧", "电视剧"]
        for kw in tv_keywords:
            if kw in activity:
                return "living_room"

        # ========== 延迟睡眠（非真正睡觉）-> 客厅 ==========
        delay_sleep_keywords = ["晚睡", "晚点睡", "再睡", "先不睡", "不想睡"]
        for kw in delay_sleep_keywords:
            if kw in activity:
                return "living_room"

        # ========== 优先匹配：睡眠相关 -> 卧室 ==========
        sleep_keywords = ["睡觉", "去睡", "上床", "躺床", "准备睡觉", "洗漱", "晚安"]
        for kw in sleep_keywords:
            if kw in activity:
                return "bedroom"

        # ========== 明确吃东西才去厨房 ==========
        # 必须有明确的"吃"相关词汇，且不是看电视等活动
        food_keywords = ["吃", "零食", "夜宵", "食物", "厨房", "冰箱", "外卖", "饿", "找点吃的", "翻找", "偷吃"]
        for kw in food_keywords:
            if kw in activity:
                return "kitchen"

        # ========== 手机相关 -> 仅在手机成瘾场景使用 ==========
        phone_keywords = ["手机", "玩手机", "刷手机", "游戏", "短视频"]
        if "phone" in self.scenario_name or "手机" in self.scenario_name:
            for kw in phone_keywords:
                if kw in activity:
                    return "phone_area"

        # 默认：客厅（晚间活动默认在客厅）
        return "living_room"

    def _resolve_target_location(self, activity: str, target_location: str | None) -> str | None:
        """确保目标位置可用，必要时映射到场景已有语义位置"""
        semantic_locations = getattr(self.scenario, "semantic_locations", {}) or {}
        if target_location and target_location in semantic_locations:
            return target_location

        # 非手机场景：手机相关意图直接回到客厅
        phone_keywords = ["手机", "玩手机", "刷手机", "游戏", "短视频"]
        if ("phone" not in self.scenario_name and "手机" not in self.scenario_name) and any(kw in activity for kw in phone_keywords):
            if "living_room" in semantic_locations:
                return "living_room"

        # phone_area 在非手机场景时降级到客厅
        if target_location == "phone_area" and "phone_area" not in semantic_locations:
            if "living_room" in semantic_locations:
                return "living_room"

        # kitchen_door 不存在时回退到 kitchen
        if target_location == "kitchen_door" and "kitchen" in semantic_locations:
            return "kitchen"

        inferred = self._infer_target_location(activity)
        if inferred in semantic_locations:
            return inferred

        llm_key, _ = self._resolve_semantic_location_with_llm(activity)
        if llm_key in semantic_locations:
            return llm_key

        return None

    def _is_sleep_activity(self, intention) -> bool:
        """判断意图是否睡眠相关"""
        if not intention:
            return False
        if getattr(intention, "is_sleep_related", False):
            return True
        activity = getattr(intention, "activity", "") or ""
        # 延迟睡眠的表达不等于睡觉
        delay_keywords = ["晚睡", "晚点睡", "再睡", "先不睡", "不想睡"]
        if any(kw in activity for kw in delay_keywords):
            return False
        sleep_keywords = ["睡觉", "去睡", "上床", "躺床", "准备睡觉", "洗漱", "晚安", "sleep", "bed"]
        return any(kw in activity for kw in sleep_keywords)

    def _is_violation_intention(self, intention, target_location=None) -> bool:
        """判断意图是否违规（基于内容/地点关键词，避免误判非违规活动）"""
        if not intention:
            return False
        activity = getattr(intention, "activity", "") or ""
        activity_lower = activity.lower()
        if not target_location:
            target_location = getattr(intention, "target_location", None) or self._infer_target_location(activity)

        forbidden_foods = [f.lower() for f in getattr(self.scenario, "forbidden_foods", []) if f]
        forbidden_activities = [a.lower() for a in getattr(self.scenario, "forbidden_activities", []) if a]

        if any(word in activity_lower for word in forbidden_foods):
            return True
        if any(word in activity_lower for word in forbidden_activities):
            return True

        food_keywords = ["吃", "零食", "夜宵", "宵夜", "外卖", "甜食", "薯片", "蛋糕", "汉堡", "油炸", "可乐", "翻找", "偷吃"]
        if target_location == "kitchen" and any(word in activity for word in food_keywords):
            return True

        phone_keywords = ["手机", "刷手机", "玩手机", "短视频", "游戏", "社交媒体", "上网"]
        if target_location == "phone_area" or "phone" in self.scenario_name or "手机" in self.scenario_name:
            if any(word in activity for word in phone_keywords):
                return True

        # 兜底：如果 compliance_threshold 很高且地点是高风险区域，也视为违规
        if getattr(intention, "compliance_threshold", 0) >= 2 and target_location in {"kitchen", "phone_area"}:
            return True

        return False

    def _normalize_sleep_intention(self, intention, timer):
        """纠正“晚睡一会儿”等不合理意图"""
        if not intention:
            return intention
        activity = getattr(intention, "activity", "") or ""
        delay_keywords = ["晚睡", "晚点睡", "再睡", "先不睡", "不想睡"]
        if not any(kw in activity for kw in delay_keywords):
            return intention

        # 获取目标睡觉时间
        target_sleep_time = "23:30"
        if hasattr(self.scenario, "target_profile"):
            target_sleep_time = self.scenario.target_profile.get("sleep_schedule", {}).get("target_sleep_time", target_sleep_time)
        sleep_hour, sleep_minute = 23, 30
        try:
            sleep_hour, sleep_minute = [int(x) for x in target_sleep_time.split(":")]
        except Exception:
            pass

        now = timer.get_date()
        current_minutes = now.hour * 60 + now.minute
        sleep_minutes = sleep_hour * 60 + sleep_minute

        # 未到睡觉时间，改为放松
        if current_minutes < sleep_minutes:
            intention.activity = "看电视放松"
            intention.inner_monologue = f"{intention.inner_monologue}（晚点再睡，先放松一下）"
            intention.target_location = "living_room"
            intention.is_sleep_related = False
            return intention

        # 已到睡觉时间，改为睡觉
        intention.activity = "睡觉"
        intention.inner_monologue = f"{intention.inner_monologue}（该睡觉了）"
        intention.target_location = "bedroom"
        intention.is_sleep_related = True
        return intention

    def _get_bed_address(self):
        """优先获取卧室中的床地址"""
        addresses = self.scenario.semantic_locations.get("bedroom", [])
        if not addresses:
            return None
        keywords = ["床", "bed"]
        for address in addresses:
            if any(k in part for part in address for k in keywords):
                return address
        return addresses[0]

    def _get_food_address(self):
        """优先获取厨房内的食物/冰箱地址"""
        addresses = self.scenario.semantic_locations.get("kitchen", [])
        if not addresses:
            return None
        keywords = ["冰箱", "柜", "食物", "零食柜", "food", "fridge", "pantry", "cabinet"]
        for address in addresses:
            if any(k in part for part in address for k in keywords):
                return address
        return addresses[0]

    def _move_manager_to_item(self, strategy):
        """移除物品时，管理者必须到目标物品位置"""
        if not strategy or strategy.level < 2:
            return None
        action_text = (strategy.action or "").lower()
        action_label = strategy.action or ""

        if ("phone" in self.scenario_name or "手机" in self.scenario_name) and ("phone" in action_text or "手机" in action_label):
            if "phone_area" in self.scenario.semantic_locations:
                self._move_agent_to_location(self.manager_agent, "phone_area")
                return "phone_area"
            self._move_agent_to_location(self.manager_agent, "bedroom")
            return "bedroom"

        if strategy.level == 2:
            food_address = self._get_food_address()
            if food_address:
                self._move_agent_to_semantic_address(self.manager_agent, food_address, action_label or "移除食物")
                return "kitchen"
        if strategy.level == 3:
            # 锁门前先让所有 agent 离开厨房区域
            self._ensure_agents_outside_kitchen()
            if "kitchen_door" in self.scenario.semantic_locations:
                self._move_agent_to_location(self.manager_agent, "kitchen_door")
                return "kitchen_door"
            self._move_agent_to_location(self.manager_agent, "kitchen")
            return "kitchen"
        return None
    def _adjust_intervention_for_day(self, strategy, level2_used: bool, level3_used: bool):
        """确保当天 L3/L4 不重复，允许 L1 劝说"""
        if not strategy:
            return strategy
        # L4 执行后，当天不再需要 L3/L4
        if level3_used and strategy.level >= 2:
            strategy.level = 1
            strategy.action = "persuade"
            strategy.reason = f"{strategy.reason}（当天已执行过L4，降级为劝说）"
            return strategy
        # L3 不重复
        if level2_used and strategy.level == 2:
            strategy.level = 1
            strategy.action = "persuade"
            strategy.reason = f"{strategy.reason}（当天已执行过L3，降级为劝说）"
            return strategy
        return strategy

    def _normalize_strategy_action(self, strategy, intention=None):
        """确保策略动作与等级一致，保留原始动作"""
        if not strategy:
            return strategy

        if not hasattr(strategy, "raw_action"):
            strategy.raw_action = strategy.action

        if strategy.level == 0:
            strategy.action = "observe"
            return strategy
        if strategy.level == 1:
            strategy.action = "persuade"
            return strategy
        if strategy.level == 2:
            action_text = (getattr(strategy, "raw_action", "") or "").lower()
            action_label = getattr(strategy, "raw_action", "") or ""
            if ("phone" in self.scenario_name or "手机" in self.scenario_name) and ("phone" in action_text or "手机" in action_label):
                strategy.action = "remove_phone"
            else:
                strategy.action = "remove_food"
            return strategy
        if strategy.level == 3:
            strategy.action = "lock_kitchen"
        return strategy

    def _check_env_blocked(self, target_location: str, env_state: dict) -> tuple:
        """检查目标位置是否被环境状态阻止

        Args:
            target_location: 目标语义位置
            env_state: 当前环境状态字典

        Returns:
            tuple: (is_blocked, block_reason, blocked_at_location)
        """
        if not target_location:
            return False, None, None

        if target_location == "kitchen" and env_state.get("kitchen_locked", False):
            return True, "厨房门被锁了", "kitchen_door"

        if target_location == "kitchen" and env_state.get("food_removed", False):
            return True, "厨房里没有可吃的东西", "kitchen"

        if target_location == "phone_area" and env_state.get("phone_removed", False):
            return True, "手机已被没收", "phone_area"

        return False, None, None

    def _generate_turnaround(self, intention, target_location: str, block_reason: str, env_state: dict,
                             blocked_location: str = None) -> dict:
        """生成折返独白和替代活动

        Args:
            intention: 原始意图
            target_location: 被阻止的目标位置
            block_reason: 阻止原因
            env_state: 当前环境状态
            blocked_location: 被阻止的具体位置（如"kitchen_door"）

        Returns:
            dict: 包含 turnaround_monologue, redirect_activity, redirect_location, emotional_reaction
        """
        # 获取环境约束描述
        constraints = []
        if env_state.get("kitchen_locked"):
            constraints.append("厨房已被锁定")
        if env_state.get("food_removed"):
            constraints.append("厨房食物已被移除")
        if env_state.get("phone_removed"):
            constraints.append("手机已被没收")
        env_constraints_str = "；".join(constraints) if constraints else "无"

        # 获取位置描述
        location_desc_map = {
            "kitchen": "厨房",
            "kitchen_door": "厨房门口",
            "snacks_area": "零食柜",
            "phone_area": "手机放置处",
            "bedroom": "卧室",
            "living_room": "客厅"
        }
        location_key = blocked_location or target_location
        target_location_desc = location_desc_map.get(location_key, location_key)

        try:
            output = self.target_agent.completion(
                "health_generate_turnaround",
                original_activity=intention.activity,
                target_location_desc=target_location_desc,
                block_reason=block_reason,
                environment_constraints=env_constraints_str,
                self_discipline=getattr(self.target_agent, 'self_discipline', 'medium')
            )

            if isinstance(output, dict):
                # 如果返回的是包含 res 的字典
                if "res" in output:
                    return output["res"]
                return output
            else:
                # Fallback：使用模板
                return self._turnaround_template(location_key, block_reason)

        except Exception as e:
            self.logger.warning(f"折返生成失败: {e}，使用模板")
            return self._turnaround_template(location_key, block_reason)

    def _turnaround_template(self, target_location: str, block_reason: str) -> dict:
        """折返模板（当LLM调用失败时使用）"""
        templates = {
            "kitchen_door": {
                "turnaround_monologue": f"走到厨房门口发现{block_reason}，看来暂时进不去了。只能去客厅待会儿。",
                "redirect_activity": "去客厅看电视",
                "redirect_location": "living_room",
                "emotional_reaction": "resigned"
            },
            "kitchen": {
                "turnaround_monologue": f"到厨房想找点吃的，结果{block_reason}。估计是{self.manager_name}把食物拿走了，那就在厨房找找别的。",
                "redirect_activity": "在厨房找其他食物",
                "redirect_location": "kitchen",
                "emotional_reaction": "frustrated"
            },
            "phone_area": {
                "turnaround_monologue": f"想玩会儿手机，找了半天发现{block_reason}。肯定是{self.manager_name}把手机收走了，那就休息吧。",
                "redirect_activity": "躺下休息",
                "redirect_location": "bedroom",
                "emotional_reaction": "resigned"
            }
        }

        return templates.get(target_location, {
            "turnaround_monologue": f"想做的事被阻止了：{block_reason}。算了，去客厅待着吧。",
            "redirect_activity": "去客厅",
            "redirect_location": "living_room",
            "emotional_reaction": "resigned"
        })

    def _add_minutes_to_time(self, time_str: str, minutes: int) -> str:
        """给时间字符串添加分钟数

        Args:
            time_str: 时间字符串，如 "21:00"
            minutes: 要添加的分钟数

        Returns:
            新的时间字符串
        """
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            total_minutes = hour * 60 + minute + minutes
            new_hour = (total_minutes // 60) % 24
            new_minute = total_minutes % 60

            return f"{new_hour:02d}:{new_minute:02d}"
        except Exception:
            return time_str

    def _get_semantic_location_coord(self, semantic_key: str) -> tuple:
        """从语义位置获取地图坐标

        Args:
            semantic_key: 语义位置名称，如 "kitchen_door", "living_room"

        Returns:
            坐标元组 (x, y)，如果无法找到则返回 None
        """
        if not semantic_key:
            return None

        try:
            if semantic_key == "kitchen_door":
                outside = self._get_kitchen_door_outside_coord()
                if outside:
                    return outside
            # 获取语义位置的地址列表
            addresses = self.scenario.semantic_locations.get(semantic_key, [])
            if not addresses:
                return None

            # 取第一个地址
            address = addresses[0]

            # 从 maze 获取坐标
            tiles = self.game.maze.get_address_tiles(address)
            if tiles:
                return list(tiles)[0]  # 返回第一个坐标

        except Exception as e:
            self.logger.debug(f"获取语义位置坐标失败 {semantic_key}: {e}")

        return None

    def _get_kitchen_area_tiles(self):
        """获取厨房区域所有坐标"""
        tiles = set()
        addresses = self.scenario.semantic_locations.get("kitchen", [])
        for address in addresses:
            try:
                addr_tiles = self.game.maze.get_address_tiles(address)
                if addr_tiles:
                    tiles.update(addr_tiles)
            except Exception:
                continue
        return tiles

    def _get_kitchen_door_outside_coord(self):
        """厨房门外左侧一格坐标（用于锁门与折返显示）"""
        addresses = self.scenario.semantic_locations.get("kitchen_door", [])
        if not addresses:
            return None
        try:
            tiles = self.game.maze.get_address_tiles(addresses[0])
            if not tiles:
                return None
            door_coord = list(tiles)[0]
            target = (door_coord[0] - 1, door_coord[1])
            if 0 <= target[0] < self.game.maze.maze_width and 0 <= target[1] < self.game.maze.maze_height:
                try:
                    tile = self.game.maze.tile_at(target)
                    if not getattr(tile, "collision", False):
                        return list(target)
                except Exception:
                    return list(target)
            return list(door_coord)
        except Exception:
            return None

    def _ensure_agents_outside_kitchen(self):
        """锁门前确保所有 agent 离开厨房区域"""
        kitchen_tiles = self._get_kitchen_area_tiles()
        if not kitchen_tiles:
            return
        for agent in self.game.agents.values():
            coord = tuple(agent.coord) if agent.coord else None
            if coord and coord in kitchen_tiles:
                moved = self._move_agent_to_location(agent, "living_room")
                if not moved:
                    self._move_agent_to_location(agent, "bedroom")

    def _get_blocked_location_from_reason(self, block_reason: str) -> str:
        """从阻止原因推断被阻止的位置

        Args:
            block_reason: 阻止原因，如 "厨房门被锁了"

        Returns:
            语义位置名称，如 "kitchen_door"
        """
        if not block_reason:
            return None

        if "厨房门" in block_reason or "kitchen" in block_reason.lower():
            return "kitchen_door"
        if "零食" in block_reason or "食物" in block_reason or "snack" in block_reason.lower():
            return "kitchen"  # 在厨房发现食物没了
        if "手机" in block_reason or "phone" in block_reason.lower():
            return "phone_area"

        return None

    def _save_daily_log(self, day, day_log):
        """Save daily log to file"""
        log_file = self.result_path / f"day_{day:02d}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(day_log, f, ensure_ascii=False, indent=2)

    def _save_checkpoint(self, current_time, intention=None, strategy=None, turnaround_info=None, env_state=None):
        """Save checkpoint for replay visualization

        Args:
            current_time: 当前时间
            intention: 当前意图
            strategy: 当前策略
            turnaround_info: 折返信息字典，格式如:
                {
                    "agent_name": {
                        "blocked_at": [x, y],  # 被阻止的坐标（如厨房门）
                        "blocked_location": "kitchen_door",
                        "block_reason": "厨房门被锁了",
                        "redirect_to": [x, y],
                        "redirect_location": "living_room",
                        "redirect_activity": "看电视"
                    }
                }
        """
        # Build checkpoint data compatible with compress.py / replay.py
        checkpoint_data = copy.deepcopy(self.config)

        # Update agent states
        if "agents" not in checkpoint_data:
            checkpoint_data["agents"] = {}

        for name, agent in self.game.agents.items():
            if name not in checkpoint_data["agents"]:
                checkpoint_data["agents"][name] = {}
            # Save agent state for replay
            agent_dict = agent.to_dict()
            checkpoint_data["agents"][name].update(agent_dict)
            checkpoint_data["agents"][name]["coord"] = list(agent.coord) if agent.coord else [0, 0]

            # Ensure action.event.address is saved from agent state
            if agent.action and agent.action.event and agent.action.event.address:
                if "action" not in checkpoint_data["agents"][name]:
                    checkpoint_data["agents"][name]["action"] = {}
                if "event" not in checkpoint_data["agents"][name]["action"]:
                    checkpoint_data["agents"][name]["action"]["event"] = {}
                checkpoint_data["agents"][name]["action"]["event"]["address"] = agent.action.event.address

            # Update action event to reflect current activity
            if name == self.target_name and intention:
                # Target is doing the intention activity
                checkpoint_data["agents"][name]["action"]["event"]["describe"] = intention.activity
                checkpoint_data["agents"][name]["action"]["event"]["predicate"] = "正在"
                checkpoint_data["agents"][name]["action"]["event"]["object"] = intention.activity

                # 添加健康数据，便于回放
                checkpoint_data["agents"][name]["health_data"] = {
                    "score": self.cumulative_health_scorer.current_score,
                    "zone": self.cumulative_health_scorer.get_health_status(),
                    "day": self.current_day,
                    "tide_phase": self.cumulative_health_scorer.get_tide_phase(),
                    "discipline": self.discipline_level,
                }

                # 添加折返信息（如果有）
                if turnaround_info and name in turnaround_info:
                    checkpoint_data["agents"][name]["turnaround"] = turnaround_info[name]
                elif intention and getattr(intention, 'discovered_blocked', False):
                    # 从意图对象获取折返信息
                    # 获取被阻位置和折返位置的坐标
                    blocked_location = getattr(intention, "blocked_location", None)
                    if not blocked_location:
                        blocked_location = self._get_blocked_location_from_reason(intention.block_reason)
                    blocked_coord = self._get_semantic_location_coord(blocked_location)
                    redirect_coord = self._get_semantic_location_coord(intention.redirect_location)

                    checkpoint_data["agents"][name]["turnaround"] = {
                        "blocked_at": list(blocked_coord) if blocked_coord else None,
                        "blocked_location": blocked_location,
                        "block_reason": intention.block_reason,
                        "redirect_to": list(redirect_coord) if redirect_coord else None,
                        "redirect_location": intention.redirect_location,
                        "redirect_activity": intention.redirect_activity
                    }

            elif name == self.manager_name and strategy and strategy.level > 0:
                # Manager is intervening
                checkpoint_data["agents"][name]["action"]["event"]["describe"] = strategy.action
                checkpoint_data["agents"][name]["action"]["event"]["predicate"] = "正在执行"
                checkpoint_data["agents"][name]["action"]["event"]["object"] = strategy.action

        # Add time and step info
        time_str = current_time.strftime("%Y%m%d-%H:%M")
        checkpoint_data["time"] = time_str
        checkpoint_data["step"] = self.step_counter  # Use step counter instead of day
        checkpoint_data["stride"] = 30  # 30 minutes per checkpoint
        checkpoint_data["day"] = self.current_day

        # Add intervention data for replay
        checkpoint_data["intervention"] = {
            "level": strategy.level if strategy else 0,
            "action": strategy.action if strategy else "",
            "reason": strategy.reason if strategy else "",
        }

        # Add environment state (post-step) for replay
        if env_state is not None:
            checkpoint_data["env_state"] = {
                "kitchen_locked": bool(env_state.get("kitchen_locked", False)),
                "food_removed": bool(env_state.get("food_removed", False)),
                "phone_removed": bool(env_state.get("phone_removed", False)),
            }

        # Add cumulative health summary for replay
        checkpoint_data["health_summary"] = self.cumulative_health_scorer.get_summary()

        # Save checkpoint file
        checkpoint_file = f"{self.checkpoints_folder}/simulate-{time_str.replace(':', '')}.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

        # Save health conversation to game.conversation for replay
        if intention and strategy:
            self._add_health_conversation(time_str, intention, strategy)

        # Save conversation data
        conversation_file = f"{self.checkpoints_folder}/conversation.json"
        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(self.game.conversation, f, ensure_ascii=False, indent=2)

    def _extract_home_label_from_addresses(self, addresses):
        if not addresses:
            return None
        first = addresses[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            return first[1]
        if isinstance(first, str):
            return first
        return None

    def _resolve_home_label(self):
        if self.map_folder == "homeWithRobot":
            return "家"
        semantic_locations = getattr(self.scenario, "semantic_locations", {}) or {}
        for key in ("kitchen", "living_room", "bedroom", "kitchen_door"):
            label = self._extract_home_label_from_addresses(semantic_locations.get(key))
            if label:
                return label
        for addresses in semantic_locations.values():
            label = self._extract_home_label_from_addresses(addresses)
            if label:
                return label
        return "家"

    def _add_health_conversation(self, time_str, intention, strategy):
        """Add health management interaction as conversation for replay"""
        # Format: {time: [{persons @ location: [[speaker, text], ...]}]}
        # time_str is already in format "20260121-19:00" from checkpoint
        full_time = time_str

        if full_time not in self.game.conversation:
            self.game.conversation[full_time] = []

        # Create conversation entry - use scenario-derived home label
        location = self._resolve_home_label()
        persons_key = f"{self.target_name} -> {self.manager_name} @ {location}"

        conversation_content = [
            [self.target_name, f"（内心想法）{intention.inner_monologue}"],
            [self.target_name, f"我想要{intention.activity}..."],
        ]

        if strategy.level > 0:
            conversation_content.append(
                [self.manager_name, f"（采取干预）{strategy.action}"]
            )
            conversation_content.append(
                [self.manager_name, f"（原因）{strategy.reason}"]
            )

        self.game.conversation[full_time].append({persons_key: conversation_content})

    def run_parallel_days(self, start_day, end_day, max_workers=None):
        """
        并行执行多天的模拟（适用于状态独立的场景）

        注意：这种方法假设每天的模拟相对独立。
        对于状态依赖强的场景，建议使用顺序模式。

        Args:
            start_day: 起始天数
            end_day: 结束天数
            max_workers: 最大并行数（默认为 API key 数量）
        """
        if max_workers is None:
            # 获取 API key 数量作为默认并行数
            llm_config = self.config.get("agent", {}).get("think", {}).get("llm", {})
            api_keys = llm_config.get("api_keys", [llm_config.get("api_key", "")])
            max_workers = min(len(api_keys), 9)  # 最多9个并行

        days_to_run = list(range(start_day, end_day + 1))
        total_days = len(days_to_run)

        self.logger.info(f"Running {total_days} days in parallel with {max_workers} workers")

        # 存储每天的结果
        day_results = {}

        def run_single_day(day):
            """运行单天模拟"""
            try:
                result = self.run_monitoring_period_batch(day)
                return day, result, None
            except Exception as e:
                return day, None, str(e)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_single_day, day): day for day in days_to_run}

            for future in as_completed(futures):
                day = futures[future]
                try:
                    day_num, result, error = future.result()
                    if error:
                        self.logger.error(f"Day {day_num} failed: {error}")
                    else:
                        day_results[day_num] = result
                        self.logger.info(f"Day {day_num} completed")
                except Exception as e:
                    self.logger.error(f"Day {day} raised exception: {e}")

        # 按顺序更新状态
        for day in sorted(day_results.keys()):
            self.current_day = day
            # 状态已经在 run_monitoring_period_batch 中保存

        self.logger.info(f"Parallel execution completed: {len(day_results)}/{total_days} days successful")
        return day_results

    def run(self, resume=False, batch_mode=False, parallel_workers=0):
        """
        Run the full simulation with optional resume, batch mode, and parallel support.

        Args:
            resume: If True, attempt to resume from last checkpoint
            batch_mode: If True, use batch LLM calls for ~10x speedup
                       (2 LLM calls per day instead of 28)
            parallel_workers: Number of parallel workers (0=sequential, >0=parallel days)
        """
        start_day = 1

        if resume:
            if self.load_simulation_state():
                start_day = self.current_day + 1
                self.logger.info(f"Resuming from day {start_day}")

                # If we've already completed the target days, check if extending
                if start_day > self.days:
                    self.logger.info(
                        f"Previous simulation completed {self.current_day} days. "
                        f"Target is {self.days} days. Nothing to do."
                    )
                    self.logger.info("To extend, use --days with a higher number")
                    return
            else:
                self.logger.info("No valid checkpoint found, starting fresh")
                start_day = 1

        remaining_days = self.days - start_day + 1

        # 确定运行模式
        if parallel_workers > 0:
            mode_str = f"PARALLEL MODE ({parallel_workers} workers, batch LLM)"
        elif batch_mode:
            mode_str = "BATCH MODE (~10x faster)"
        else:
            mode_str = "SERIAL MODE"

        self.logger.info(
            f"Running health simulation [{mode_str}]: days {start_day} to {self.days} "
            f"({remaining_days} days remaining)"
        )

        # 并行模式：多天同时运行
        if parallel_workers > 0:
            self.run_parallel_days(start_day, self.days, max_workers=parallel_workers)
        else:
            # 顺序模式
            for day in range(start_day, self.days + 1):
                self.current_day = day
                try:
                    if batch_mode:
                        self.run_monitoring_period_batch(day)
                    else:
                        self.run_monitoring_period(day)
                except KeyboardInterrupt:
                    self.logger.warning(f"Simulation interrupted at day {day}")
                    self.save_simulation_state()
                    self.logger.info("State saved. Use --resume to continue later.")
                    raise
                except Exception as e:
                    self.logger.error(f"Error on day {day}: {e}")
                    self.save_simulation_state()
                    self.logger.info("State saved. Use --resume to continue after fixing the issue.")
                    raise

                # Jump to next day's 19:00
                # 基于逻辑日期计算，凌晨时间归属前一天
                timer = utils.get_timer()
                logical_date = timer.get_logical_date(day_boundary_hour=7)  # 凌晨时间归属前一天
                # 下一天 = 逻辑日期 + 1天 的 19:00
                next_logical_date = logical_date + datetime.timedelta(days=1)
                next_day = datetime.datetime.combine(next_logical_date, datetime.time(19, 0, 0))
                timer.jump_to(next_day)

        # Generate final report and export results
        self._generate_report()
        self.export_complete_results()
        self.logger.info("Simulation completed!")

    def _generate_report(self):
        """Generate final simulation report"""
        report = {
            "scenario": self.scenario_name,
            "target": self.target_name,
            "manager": self.manager_name,
            "total_days": self.days,
            "daily_health_scores": [],
            "daily_emotion_scores": [],
            "average_health_score": 0,
            "average_emotion_score": 0,
            "intervention_summary": {
                "level_0": 0,
                "level_1": 0,
                "level_2": 0,
                "level_3": 0
            }
        }

        total_health_score = 0
        total_emotion_score = 0
        for log in self.daily_logs:
            health_score = log.get("health_score", 0)
            emotion_score = log.get("emotion_score", 5.0)
            report["daily_health_scores"].append(health_score)
            report["daily_emotion_scores"].append(emotion_score)
            total_health_score += health_score
            total_emotion_score += emotion_score

            for intervention in log.get("interventions", []):
                level = intervention.get("level", 0)
                if 0 <= level <= 3:
                    report["intervention_summary"][f"level_{level}"] += 1

        report["average_health_score"] = total_health_score / len(self.daily_logs) if self.daily_logs else 0
        report["average_emotion_score"] = total_emotion_score / len(self.daily_logs) if self.daily_logs else 0

        # 添加长期机制信息
        report["long_term_analysis"] = {
            "final_phase": self.strategy_manager.current_phase.value,
            "relapse_count": self.strategy_manager.relapse_count,
            "habit_consolidation": self.strategy_manager.habit_tracker.get_summary(),
            "trust_capital": self.strategy_manager.trust_capital.get_summary(),
            "weekly_reflections_count": len(self.strategy_manager.weekly_reflections),
            "monthly_summaries_count": len(self.strategy_manager.monthly_summaries),
        }

        # Save report
        report_file = self.result_path / "final_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Generate markdown summary
        self._generate_markdown_report(report)

        self.logger.info(f"Final report saved to {report_file}")

    def _generate_markdown_report(self, report):
        """Generate markdown summary report"""
        health_scores = report['daily_health_scores']
        emotion_scores = report.get('daily_emotion_scores', [])

        # 健康分趋势
        h_week1 = health_scores[:7] if len(health_scores) >= 7 else health_scores
        h_week2_3 = health_scores[7:21] if len(health_scores) >= 21 else health_scores[7:]
        h_week4_6 = health_scores[21:] if len(health_scores) > 21 else []

        h_week1_avg = sum(h_week1) / len(h_week1) if h_week1 else 0
        h_week2_3_avg = sum(h_week2_3) / len(h_week2_3) if h_week2_3 else 0
        h_week4_6_avg = sum(h_week4_6) / len(h_week4_6) if h_week4_6 else 0

        # 情绪分趋势
        e_week1 = emotion_scores[:7] if len(emotion_scores) >= 7 else emotion_scores
        e_week2_3 = emotion_scores[7:21] if len(emotion_scores) >= 21 else emotion_scores[7:]
        e_week4_6 = emotion_scores[21:] if len(emotion_scores) > 21 else []

        e_week1_avg = sum(e_week1) / len(e_week1) if e_week1 else 0
        e_week2_3_avg = sum(e_week2_3) / len(e_week2_3) if e_week2_3 else 0
        e_week4_6_avg = sum(e_week4_6) / len(e_week4_6) if e_week4_6 else 0

        # 获取长期机制信息
        long_term = report.get("long_term_analysis", {})
        habit_info = long_term.get("habit_consolidation", {})
        trust_info = long_term.get("trust_capital", {})

        md_content = f"""# 健康管理模拟报告

## 基本信息
- **场景**: {report['scenario']}
- **被监督者**: {report['target']}
- **监督者**: {report['manager']}
- **总天数**: {report['total_days']}

## 健康评分
- **平均健康分**: {report['average_health_score']:.2f} / 10
- **每日健康分**: {', '.join(str(s) for s in report['daily_health_scores'])}

## 情绪评分（满意度）
- **平均情绪分**: {report.get('average_emotion_score', 0):.2f} / 10
- **每日情绪分**: {', '.join(str(s) for s in report.get('daily_emotion_scores', []))}

## 干预策略统计
| 级别 | 次数 | 说明 |
|------|------|------|
| Level 0 | {report['intervention_summary']['level_0']} | 观察 |
| Level 1 | {report['intervention_summary']['level_1']} | 劝说 |
| Level 2 | {report['intervention_summary']['level_2']} | 移除物品 |
| Level 3 | {report['intervention_summary']['level_3']} | 锁定空间 |

## 长期机制分析

### 关系阶段
- **最终阶段**: {long_term.get('final_phase', '未知')}
- **复发次数**: {long_term.get('relapse_count', 0)}

### 习惯巩固
- **内化阶段**: {habit_info.get('stage_name', '未知')}
- **无干预自觉率**: {habit_info.get('no_intervention_compliance_rate', 0):.0%}
- **主动行为比例**: {habit_info.get('proactive_rate', 0):.0%}

### 信任资本
- **当前资本**: {trust_info.get('current_capital', 0):.1f} / {trust_info.get('max_capital', 100)}
- **自主权等级**: {trust_info.get('autonomy_level', '未知')}
- **累计赚取**: {trust_info.get('total_earned', 0):.1f}
- **累计花费**: {trust_info.get('total_spent', 0):.1f}

## 趋势分析

### 第一周（蜜月期 Days 1-7）
| 指标 | 平均分 |
|------|--------|
| 健康分 | {h_week1_avg:.2f} |
| 情绪分 | {e_week1_avg:.2f} |

### 第二至三周（调整期 Days 8-21）
| 指标 | 平均分 |
|------|--------|
| 健康分 | {h_week2_3_avg:.2f} |
| 情绪分 | {e_week2_3_avg:.2f} |

### 第四周及以后（倦怠/稳定期 Days 22+）
| 指标 | 平均分 |
|------|--------|
| 健康分 | {h_week4_6_avg:.2f} |
| 情绪分 | {e_week4_6_avg:.2f} |

---
*报告由 GenerativeAgentsCN 健康管理模拟系统自动生成*
"""
        md_file = self.result_path / "report.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)

    def export_complete_results(self):
        """
        导出完整结果为 JSON 和 Excel 格式

        生成文件:
        - complete_results.json: 包含所有详细数据的JSON
        - results_summary.xlsx: Excel汇总表（如果pandas可用）
        """
        # 构建完整结果数据
        complete_results = {
            "metadata": {
                "scenario_name": self.scenario_name,
                "scenario_display_name": self.scenario.scenario_name,
                "target_agent": self.target_name,
                "manager_agent": self.manager_name,
                "total_days": self.days,
                "map_folder": self.scenario.map_folder,
                "export_time": datetime.datetime.now().isoformat(),
            },
            "profile_config": {
                "target_profile": self.scenario.target_profile,
                "manager_profile": self.scenario.manager_profile,
            },
            "daily_data": [],
            "summary": {
                "total_days_completed": len(self.daily_logs),
                "average_health_score": 0,
                "average_emotion_score": 0,
                "min_health_score": 10,
                "max_health_score": 0,
                "min_emotion_score": 10,
                "max_emotion_score": 0,
                "total_interventions": 0,
                "intervention_by_level": {"0": 0, "1": 0, "2": 0, "3": 0},
                "compliance_rate": 0,
                "violation_count": 0,
            },
            "phase_analysis": {
                # 使用动态检测的阶段（基于行为数据，而非固定天数）
                "honeymoon": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "蜜月期"},
                "adjustment": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "调整期"},
                "fatigue": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "倦怠期"},
                "stable": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "稳定期"},
                "relapse": {"days": [], "avg_health": 0, "avg_emotion": 0, "interventions": 0, "description": "复发期"},
            },
            "trend_data": {
                "days": [],
                "health_scores": [],
                "emotion_scores": [],
                "intervention_levels": [],
                "intentions": [],
                "outcomes": [],
            },
            "long_term_mechanism": {
                "final_phase": self.strategy_manager.current_phase.value,
                "phase_history": [],
                "relapse_count": self.strategy_manager.relapse_count,
                "habit_consolidation": self.strategy_manager.habit_tracker.get_summary(),
                "trust_capital": self.strategy_manager.trust_capital.get_summary(),
                "weekly_reflections": self.strategy_manager.weekly_reflections,
                "monthly_summaries": self.strategy_manager.monthly_summaries,
            }
        }

        total_score = 0
        total_interventions = 0
        violations = 0

        total_emotion_score = 0
        for i, day_log in enumerate(self.daily_logs):
            day_num = i + 1
            health_score = day_log.get("health_score", 0)
            emotion_score = day_log.get("emotion_score", 5.0)

            # 收集每日详细数据
            daily_entry = {
                "day": day_num,
                "date": day_log.get("date", ""),
                "health_score": health_score,
                "emotion_score": emotion_score,
                "emotion_breakdown": day_log.get("emotion_breakdown", {}),
                "events": day_log.get("events", []),
                "interventions": day_log.get("interventions", []),
                "reflection": day_log.get("reflection", {}),
                "target_behaviors": day_log.get("target_behaviors", []),
                "dynamic_phase": day_log.get("dynamic_phase", "honeymoon"),  # 动态检测的阶段
            }
            complete_results["daily_data"].append(daily_entry)

            # 情绪分统计
            total_emotion_score += emotion_score
            complete_results["summary"]["min_emotion_score"] = min(
                complete_results["summary"]["min_emotion_score"], emotion_score
            )
            complete_results["summary"]["max_emotion_score"] = max(
                complete_results["summary"]["max_emotion_score"], emotion_score
            )

            # 汇总统计
            total_score += health_score
            complete_results["summary"]["min_health_score"] = min(
                complete_results["summary"]["min_health_score"], health_score
            )
            complete_results["summary"]["max_health_score"] = max(
                complete_results["summary"]["max_health_score"], health_score
            )

            # 干预统计
            day_interventions = day_log.get("interventions", [])
            for intervention in day_interventions:
                level = intervention.get("level", 0)
                complete_results["summary"]["intervention_by_level"][str(level)] += 1
                total_interventions += 1

                if level >= 2:
                    violations += 1

            # 趋势数据
            complete_results["trend_data"]["days"].append(day_num)
            complete_results["trend_data"]["health_scores"].append(health_score)
            complete_results["trend_data"]["emotion_scores"].append(emotion_score)

            # 当日最高干预级别
            max_level = max([i.get("level", 0) for i in day_interventions]) if day_interventions else 0
            complete_results["trend_data"]["intervention_levels"].append(max_level)

            # 阶段分析 - 使用动态检测的阶段（基于行为数据，而非固定天数）
            dynamic_phase = day_log.get("dynamic_phase", "honeymoon")
            if dynamic_phase in complete_results["phase_analysis"]:
                complete_results["phase_analysis"][dynamic_phase]["days"].append((health_score, emotion_score, day_num))
                complete_results["phase_analysis"][dynamic_phase]["interventions"] += len(day_interventions)

        # 计算汇总统计
        if self.daily_logs:
            complete_results["summary"]["average_health_score"] = total_score / len(self.daily_logs)
            complete_results["summary"]["average_emotion_score"] = total_emotion_score / len(self.daily_logs)
            complete_results["summary"]["total_interventions"] = total_interventions
            complete_results["summary"]["violation_count"] = violations
            complete_results["summary"]["compliance_rate"] = (
                (len(self.daily_logs) - violations) / len(self.daily_logs)
            ) if self.daily_logs else 0

        # 计算阶段平均分（健康分和情绪分）- 使用动态阶段
        for phase_name in ["honeymoon", "adjustment", "fatigue", "stable", "relapse"]:
            phase_data = complete_results["phase_analysis"][phase_name]["days"]
            if phase_data:
                health_scores = [d[0] for d in phase_data]
                emotion_scores = [d[1] for d in phase_data]
                day_numbers = [d[2] for d in phase_data]
                complete_results["phase_analysis"][phase_name]["avg_health"] = sum(health_scores) / len(health_scores)
                complete_results["phase_analysis"][phase_name]["avg_emotion"] = sum(emotion_scores) / len(emotion_scores)
                complete_results["phase_analysis"][phase_name]["day_range"] = f"{min(day_numbers)}-{max(day_numbers)}"
                complete_results["phase_analysis"][phase_name]["total_days"] = len(day_numbers)

        # 保存完整 JSON
        json_file = self.result_path / "complete_results.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(complete_results, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Complete results saved to {json_file}")

        # 尝试导出 Excel
        self._export_excel(complete_results)

        return complete_results

    def _export_excel(self, complete_results):
        """导出 Excel 格式的结果"""
        try:
            import pandas as pd

            excel_file = self.result_path / "results_summary.xlsx"

            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                # Sheet 1: 每日数据
                daily_rows = []
                for day_data in complete_results["daily_data"]:
                    interventions = day_data.get("interventions", [])
                    max_level = max([i.get("level", 0) for i in interventions]) if interventions else 0
                    intervention_count = len(interventions)

                    # 使用动态阶段（从day_log中获取，而非固定天数）
                    phase_display_names = {
                        "honeymoon": "蜜月期",
                        "adjustment": "调整期",
                        "fatigue": "倦怠期",
                        "stable": "稳定期",
                        "relapse": "复发期"
                    }
                    dynamic_phase = day_data.get("dynamic_phase", "honeymoon")
                    phase_display = phase_display_names.get(dynamic_phase, dynamic_phase)

                    daily_rows.append({
                        "天数": day_data["day"],
                        "日期": day_data.get("date", ""),
                        "健康分": day_data["health_score"],
                        "情绪分": day_data.get("emotion_score", 5.0),
                        "干预次数": intervention_count,
                        "最高干预级别": max_level,
                        "阶段": phase_display,
                    })

                df_daily = pd.DataFrame(daily_rows)
                df_daily.to_excel(writer, sheet_name='每日数据', index=False)

                # Sheet 2: 汇总统计
                summary = complete_results["summary"]
                summary_rows = [
                    {"指标": "场景", "值": complete_results["metadata"]["scenario_display_name"]},
                    {"指标": "被监督者", "值": complete_results["metadata"]["target_agent"]},
                    {"指标": "监督者", "值": complete_results["metadata"]["manager_agent"]},
                    {"指标": "总天数", "值": complete_results["metadata"]["total_days"]},
                    {"指标": "完成天数", "值": summary["total_days_completed"]},
                    {"指标": "平均健康分", "值": f"{summary['average_health_score']:.2f}"},
                    {"指标": "最低健康分", "值": summary["min_health_score"]},
                    {"指标": "最高健康分", "值": summary["max_health_score"]},
                    {"指标": "平均情绪分", "值": f"{summary.get('average_emotion_score', 0):.2f}"},
                    {"指标": "最低情绪分", "值": f"{summary.get('min_emotion_score', 0):.1f}"},
                    {"指标": "最高情绪分", "值": f"{summary.get('max_emotion_score', 0):.1f}"},
                    {"指标": "总干预次数", "值": summary["total_interventions"]},
                    {"指标": "Level 0 (观察)", "值": summary["intervention_by_level"]["0"]},
                    {"指标": "Level 1 (劝说)", "值": summary["intervention_by_level"]["1"]},
                    {"指标": "Level 2 (移除物品)", "值": summary["intervention_by_level"]["2"]},
                    {"指标": "Level 3 (锁定空间)", "值": summary["intervention_by_level"]["3"]},
                    {"指标": "合规率", "值": f"{summary['compliance_rate']*100:.1f}%"},
                    {"指标": "违规次数", "值": summary["violation_count"]},
                ]
                df_summary = pd.DataFrame(summary_rows)
                df_summary.to_excel(writer, sheet_name='汇总统计', index=False)

                # Sheet 3: 阶段分析（基于动态检测，而非固定天数）
                phase_rows = []
                phase_names = {
                    "honeymoon": "蜜月期",
                    "adjustment": "调整期",
                    "fatigue": "倦怠期",
                    "stable": "稳定期",
                    "relapse": "复发期"
                }
                for phase_key, phase_name in phase_names.items():
                    phase_data = complete_results["phase_analysis"][phase_key]
                    if phase_data["days"]:  # 只显示实际出现过的阶段
                        day_range = phase_data.get("day_range", "N/A")
                        phase_rows.append({
                            "阶段": phase_name,
                            "时间范围": f"Day {day_range}" if day_range != "N/A" else "N/A",
                            "总天数": phase_data.get("total_days", len(phase_data["days"])),
                            "平均健康分": f"{phase_data.get('avg_health', 0):.2f}",
                            "平均情绪分": f"{phase_data.get('avg_emotion', 0):.2f}",
                            "干预次数": phase_data["interventions"],
                        })
                df_phase = pd.DataFrame(phase_rows)
                df_phase.to_excel(writer, sheet_name='阶段分析（动态）', index=False)

                # Sheet 4: 人设配置
                profile_rows = []
                target_profile = complete_results["profile_config"]["target_profile"]
                manager_profile = complete_results["profile_config"]["manager_profile"]

                profile_rows.append({"类型": "Target", "参数": "自律程度", "值": target_profile.get("self_discipline", "")})
                profile_rows.append({"类型": "Target", "参数": "成瘾程度", "值": target_profile.get("addiction_level", "")})
                profile_rows.append({"类型": "Target", "参数": "抵抗程度", "值": target_profile.get("resistance_to_persuasion", "")})
                profile_rows.append({"类型": "Target", "参数": "性格特征", "值": target_profile.get("personality", "")})
                profile_rows.append({"类型": "Target", "参数": "触发情绪", "值": ", ".join(target_profile.get("trigger_emotions", []))})
                profile_rows.append({"类型": "Manager", "参数": "监督风格", "值": manager_profile.get("supervision_style", "")})
                profile_rows.append({"类型": "Manager", "参数": "升级阈值", "值": manager_profile.get("escalation_threshold", "")})
                profile_rows.append({"类型": "Manager", "参数": "关系", "值": manager_profile.get("relationship", "")})

                df_profile = pd.DataFrame(profile_rows)
                df_profile.to_excel(writer, sheet_name='人设配置', index=False)

            self.logger.info(f"Excel results saved to {excel_file}")

        except ImportError:
            self.logger.warning("pandas not available, skipping Excel export. Install with: pip install pandas openpyxl")
        except Exception as e:
            self.logger.error(f"Failed to export Excel: {e}")


def run_all_experiments(scenario: str, days: int, config_path: str, batch_mode: bool, verbose: str):
    """运行所有9种实验组合（3种初始分 × 3种自律程度）

    Args:
        scenario: 场景名称
        days: 模拟天数
        config_path: 配置文件路径
        batch_mode: 是否使用批量模式
        verbose: 日志级别
    """
    print("\n" + "=" * 70)
    print("  健康管理模拟 - 9种实验组合（2026-01-23 设计）")
    print("=" * 70)
    print(f"\n  场景: {scenario}")
    print(f"  天数: {days}")
    print(f"  模式: {'批量' if batch_mode else '串行'}")
    print("\n  实验组合:")
    print("  ┌─────────────────┬──────────────────────────────────────┐")
    print("  │   初始健康分     │        自律程度                      │")
    print("  │                 │   high     medium     low           │")
    print("  ├─────────────────┼──────────────────────────────────────┤")
    print("  │   90 (高起点)   │   exp1      exp2       exp3         │")
    print("  │   75 (中起点)   │   exp4      exp5       exp6         │")
    print("  │   60 (低起点)   │   exp7      exp8       exp9         │")
    print("  └─────────────────┴──────────────────────────────────────┘")
    print("\n  警戒线: 30分")
    print("=" * 70 + "\n")

    experiments = [
        (90, "high"),   # exp1
        (90, "medium"), # exp2
        (90, "low"),    # exp3
        (75, "high"),   # exp4
        (75, "medium"), # exp5
        (75, "low"),    # exp6
        (60, "high"),   # exp7
        (60, "medium"), # exp8
        (60, "low"),    # exp9
    ]

    results = []
    for i, (initial_health, discipline) in enumerate(experiments, 1):
        print(f"\n{'='*60}")
        print(f"  实验 {i}/9: 初始分={initial_health}, 自律程度={discipline}")
        print(f"{'='*60}")

        try:
            sim = HealthSimulation(
                scenario_name=scenario,
                config_path=config_path,
                days=days,
                verbose=verbose,
                initial_health=initial_health,
                discipline_level=discipline
            )
            sim.initialize()
            sim.run(resume=False, batch_mode=batch_mode, parallel_workers=0)

            # 记录结果
            final_score = sim.cumulative_health_scorer.current_score
            result_folder = str(sim.result_path)
            results.append({
                "experiment": i,
                "initial_health": initial_health,
                "discipline": discipline,
                "final_score": final_score,
                "status": sim.cumulative_health_scorer.get_health_status(),
                "success": final_score >= NonlinearHealthScorer.WARNING_LINE,
                "result_path": result_folder
            })
            print(f"  ✓ 实验 {i} 完成: 最终健康分 = {final_score:.1f}")
            print(f"    保存路径: {result_folder}")

        except Exception as e:
            print(f"  ✗ 实验 {i} 失败: {e}")
            results.append({
                "experiment": i,
                "initial_health": initial_health,
                "discipline": discipline,
                "error": str(e),
                "success": False
            })

    # 打印汇总
    print("\n" + "=" * 70)
    print("  实验汇总")
    print("=" * 70)
    print(f"\n  {'实验':<6} {'初始分':<8} {'自律':<10} {'最终分':<10} {'状态':<12} {'成功'}")
    print("  " + "-" * 60)
    for r in results:
        if "error" in r:
            print(f"  {r['experiment']:<6} {r['initial_health']:<8} {r['discipline']:<10} {'ERROR':<10} {'-':<12} ✗")
        else:
            success_mark = "✓" if r["success"] else "✗"
            print(f"  {r['experiment']:<6} {r['initial_health']:<8} {r['discipline']:<10} {r['final_score']:<10.1f} {r['status']:<12} {success_mark}")

    print("\n" + "=" * 70)
    success_count = sum(1 for r in results if r.get("success", False))
    print(f"  总计: {success_count}/9 个实验成功（健康分保持在警戒线以上）")
    print("=" * 70 + "\n")


def main():
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(
        description="Health Management Simulation with checkpoint resume support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 运行所有9种实验组合（3种初始分 × 3种自律程度）
  python start_health_simulation.py --scenario diabetes --run-all --days 90 --batch

  # 运行单个实验（指定初始分和自律程度）
  python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline medium --days 90

  # 使用批量模式加速
  python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline high --batch

  # Resume interrupted simulation
  python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline medium --resume

  # Use PARALLEL MODE with multiple API keys (fastest)
  python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline medium --parallel 9

实验设计（基于会议 2026-01-23）:
  - 3种初始健康分: 60(低起点), 75(中起点), 90(高起点)
  - 3种自律程度: low, medium, high
  - 总计9种组合（3×3）
  - 警戒线: 30分
  - 默认模拟: 90天

累积健康分系统:
  - 健康分 = 初始分 + 每日增减值
  - 自然恢复: 无违规时每天恢复 +1~+3 分（取决于自律程度）
  - 违规惩罚: 根据行为严重程度扣分
  - 恢复上限: 不超过初始分
        """
    )
    parser.add_argument("--scenario", type=str, required=True,
                        choices=["weight-loss", "phone-addiction", "diabetes",
                                 "home-diabetes", "home-phone-addiction"],
                        help="Scenario to simulate")
    parser.add_argument("--days", type=int, default=90,
                        help="Total days to simulate (default: 90 for cumulative health system)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint if available")
    parser.add_argument("--config", type=str, default="data/config_health.json",
                        help="Config file path")
    parser.add_argument("--verbose", type=str, default="info",
                        choices=["debug", "info"],
                        help="Logging level")
    parser.add_argument("--status", action="store_true",
                        help="Show current simulation status and exit")
    parser.add_argument("--batch", action="store_true",
                        help="Use batch mode for ~10x speedup (2 LLM calls/day instead of 28)")
    parser.add_argument("--parallel", type=int, default=0,
                        help="Number of parallel workers (uses multiple API keys concurrently). "
                             "Default 0 = sequential. Recommended: number of API keys (e.g., 9)")

    # 新增：累积健康分系统参数
    parser.add_argument("--initial-health", type=int, default=75,
                        choices=[60, 75, 90],
                        help="Initial health score (60=low, 75=medium, 90=high). Default: 75")
    parser.add_argument("--discipline", type=str, default="medium",
                        choices=["low", "medium", "high"],
                        help="Self-discipline level (low/medium/high). Default: medium")
    parser.add_argument("--run-all", action="store_true",
                        help="Run all 9 experiment combinations (3 initial scores × 3 discipline levels)")

    args = parser.parse_args()

    # 运行所有9种实验
    if args.run_all:
        run_all_experiments(
            scenario=args.scenario,
            days=args.days,
            config_path=args.config,
            batch_mode=args.batch,
            verbose=args.verbose
        )
        return

    # Create simulation instance
    # 使用 resume_mode 决定是查找现有目录还是创建新目录
    sim = HealthSimulation(
        scenario_name=args.scenario,
        config_path=args.config,
        days=args.days,
        verbose=args.verbose,
        initial_health=args.initial_health,
        discipline_level=args.discipline,
        resume_mode=args.resume or args.status  # resume 和 status 都需要查找现有目录
    )

    # Status check mode
    if args.status:
        print(f"\n=== Health Simulation Status: {args.scenario} ===\n")
        print(f"  初始健康分: {args.initial_health}")
        print(f"  自律程度: {args.discipline}")
        if sim.can_resume():
            with open(sim.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            print(f"  Scenario: {state.get('scenario_name')}")
            print(f"  Current day: {state.get('current_day')} / {state.get('total_days_target')}")
            print(f"  Current health score: {state.get('cumulative_health', {}).get('current_score', 'N/A')}")
            print(f"  Step counter: {state.get('step_counter')}")
            print(f"  Daily logs: {len(state.get('daily_logs', []))}")
            print(f"  Last saved: {state.get('last_saved')}")
            print(f"\n  Use --resume to continue this simulation")
        else:
            print("  No checkpoint found. Start a new simulation with:")
            print(f"  python start_health_simulation.py --scenario {args.scenario} "
                  f"--initial-health {args.initial_health} --discipline {args.discipline}")
        return

    # Initialize and run
    sim.initialize()
    sim.run(resume=args.resume, batch_mode=args.batch, parallel_workers=args.parallel)


if __name__ == "__main__":
    main()
