"""Health Management Scenario Configuration Loader

This module provides utilities to load and manage semantic mappings
for different health management scenarios. It enables 100% reuse of
the existing village map by providing semantic interpretations of
existing locations.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


class ScenarioConfig:
    """Configuration for a health management scenario"""

    def __init__(self, scenario_data: dict):
        self.scenario_name = scenario_data.get("scenario_name", "")
        self.target_agent = scenario_data.get("target_agent", "")
        self.manager_agent = scenario_data.get("manager_agent", "")
        self.map_folder = scenario_data.get("map_folder", "village")  # Default to village map
        self.semantic_locations = scenario_data.get("semantic_locations", {})
        self.forbidden_foods = scenario_data.get("forbidden_foods", [])
        self.forbidden_activities = scenario_data.get("forbidden_activities", [])
        self.monitoring_hours = scenario_data.get("monitoring_hours", {})
        self.phone_allowed_hours = scenario_data.get("phone_allowed_hours", {})
        self.last_meal_deadline = scenario_data.get("last_meal_deadline", "")

        # 人设配置
        self.target_profile = scenario_data.get("target_profile", {})
        self.manager_profile = scenario_data.get("manager_profile", {})

    def get_target_self_discipline(self) -> str:
        """获取目标对象的自律程度

        Returns:
            str: very_low, low, medium, high, very_high
        """
        return self.target_profile.get("self_discipline", "medium")

    def get_target_addiction_level(self) -> str:
        """获取目标对象的成瘾程度

        Returns:
            str: none, low, moderate, high, severe
        """
        return self.target_profile.get("addiction_level", "moderate")

    def get_target_resistance(self) -> float:
        """获取目标对象对劝说的抵抗程度

        Returns:
            float: 0.0-1.0，越高越难被劝服
        """
        return self.target_profile.get("resistance_to_persuasion", 0.5)

    def get_manager_style(self) -> str:
        """获取管理者的监督风格

        Returns:
            str: gentle, supportive, adaptive, strict, firm_but_caring
        """
        return self.manager_profile.get("supervision_style", "adaptive")

    def get_escalation_threshold(self) -> int:
        """获取管理者升级干预的阈值

        Returns:
            int: 需要多少次失败才升级干预等级
        """
        return self.manager_profile.get("escalation_threshold", 2)

    def get_relationship(self) -> str:
        """获取管理者与目标的关系

        Returns:
            str: 配偶、朋友、机器人管家等
        """
        return self.manager_profile.get("relationship", "监督者")

    # ===== 新增：详细人设信息获取 =====

    def get_target_age(self) -> int:
        """获取目标对象的年龄"""
        return self.target_profile.get("age", 35)

    def get_target_name(self) -> str:
        """获取目标对象的名字/称呼"""
        return self.target_profile.get("name", self.target_agent)

    def get_target_personality_traits(self) -> List[str]:
        """获取目标对象的性格特征列表"""
        return self.target_profile.get("personality_traits", [])

    def get_target_background(self) -> str:
        """获取目标对象的背景故事"""
        return self.target_profile.get("background", "")

    def get_target_health_condition(self) -> str:
        """获取目标对象的健康状况"""
        return self.target_profile.get("health_condition", "")

    def get_target_weak_points(self) -> List[str]:
        """获取目标对象的弱点/容易触发的事物"""
        return self.target_profile.get("weak_points", [])

    def get_target_typical_excuses(self) -> List[str]:
        """获取目标对象的典型借口"""
        return self.target_profile.get("typical_excuses", [])

    def get_target_motivation(self) -> str:
        """获取目标对象的改变动机"""
        return self.target_profile.get("motivation", "")

    def get_target_rebellion_level(self) -> str:
        """获取目标对象的叛逆程度（适用于青少年）"""
        return self.target_profile.get("rebellion_level", "none")

    def get_manager_age(self) -> int:
        """获取管理者的年龄"""
        return self.manager_profile.get("age", 40)

    def get_manager_name(self) -> str:
        """获取管理者的名字/称呼"""
        return self.manager_profile.get("name", self.manager_agent)

    def get_manager_personality_traits(self) -> List[str]:
        """获取管理者的性格特征列表"""
        return self.manager_profile.get("personality_traits", [])

    def get_manager_intervention_approach(self) -> str:
        """获取管理者的干预方式描述"""
        return self.manager_profile.get("intervention_approach", "")

    def get_manager_typical_phrases(self) -> List[str]:
        """获取管理者的典型用语"""
        return self.manager_profile.get("typical_phrases", [])

    def get_manager_type(self) -> str:
        """获取管理者类型（human/robot）"""
        return self.manager_profile.get("type", "human")

    def get_manager_capabilities(self) -> List[str]:
        """获取管理者的能力（适用于机器人）"""
        return self.manager_profile.get("capabilities", [])

    def get_manager_limitations(self) -> List[str]:
        """获取管理者的局限性"""
        return self.manager_profile.get("limitations", [])

    def build_target_persona_prompt(self) -> str:
        """构建目标对象的完整人设描述（用于LLM prompt）"""
        profile = self.target_profile
        name = profile.get("name", self.target_agent)
        age = profile.get("age", "未知")
        personality = profile.get("personality", "")
        traits = profile.get("personality_traits", [])
        background = profile.get("background", "")
        health = profile.get("health_condition", "")
        triggers = profile.get("trigger_emotions", [])
        weak_points = profile.get("weak_points", [])
        excuses = profile.get("typical_excuses", [])

        prompt = f"""【被监管者人设】
姓名/称呼: {name}
年龄: {age}岁
性格: {personality}
性格特征: {', '.join(traits) if traits else '无特别说明'}
背景: {background if background else '无特别说明'}
健康状况: {health if health else '无特别说明'}
情绪触发点: {', '.join(triggers) if triggers else '无特别说明'}
容易破戒的点: {', '.join(weak_points) if weak_points else '无特别说明'}
常用借口: {', '.join(excuses) if excuses else '无特别说明'}
自律程度: {profile.get('self_discipline', 'medium')}
成瘾程度: {profile.get('addiction_level', 'moderate')}
对劝说的抵抗: {profile.get('resistance_to_persuasion', 0.5)}"""
        return prompt

    def build_manager_persona_prompt(self) -> str:
        """构建管理者的完整人设描述（用于LLM prompt）"""
        profile = self.manager_profile
        name = profile.get("name", self.manager_agent)
        manager_type = profile.get("type", "human")
        personality = profile.get("personality", "")
        traits = profile.get("personality_traits", [])
        relationship = profile.get("relationship", "监督者")
        approach = profile.get("intervention_approach", "")
        phrases = profile.get("typical_phrases", [])
        style = profile.get("supervision_style", "adaptive")

        prompt = f"""【监管者人设】
姓名/称呼: {name}
类型: {'机器人' if manager_type == 'robot' else '人类'}
与被监管者关系: {relationship}
性格: {personality if personality else '无特别说明'}
性格特征: {', '.join(traits) if traits else '无特别说明'}
监督风格: {style}
干预方式: {approach if approach else '无特别说明'}
常用语: {', '.join(phrases) if phrases else '无特别说明'}"""

        if manager_type == 'robot':
            capabilities = profile.get("capabilities", [])
            limitations = profile.get("limitations", [])
            prompt += f"""
机器人能力: {', '.join(capabilities) if capabilities else '基础监控'}
机器人局限: {', '.join(limitations) if limitations else '无特别说明'}"""

        return prompt

    def get_location_addresses(self, location_type: str) -> List[List[str]]:
        """Get all addresses for a semantic location type

        Args:
            location_type: Semantic location name (e.g., "kitchen", "bedroom")

        Returns:
            List of address paths (each path is a list of strings)
        """
        return self.semantic_locations.get(location_type, [])

    def get_first_location(self, location_type: str) -> Optional[List[str]]:
        """Get the first address for a semantic location type

        Args:
            location_type: Semantic location name

        Returns:
            Address path (list of strings) or None if not found
        """
        addresses = self.get_location_addresses(location_type)
        return addresses[0] if addresses else None

    def is_forbidden_activity(self, activity: str) -> bool:
        """Check if an activity is forbidden in this scenario

        Args:
            activity: Activity description

        Returns:
            True if forbidden, False otherwise
        """
        for forbidden in self.forbidden_activities + self.forbidden_foods:
            if forbidden in activity or activity in forbidden:
                return True
        return False


class ScenarioConfigLoader:
    """Loader for scenario configurations"""

    _instance = None
    _configs = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._configs:
            self._load_configs()

    def _load_configs(self):
        """Load all scenario configurations from semantic_mapping.json"""
        # health_mechanisms/scenario.py → generative_agents/data/semantic_mapping.json
        config_path = Path(__file__).resolve().parents[2] / "data" / "semantic_mapping.json"

        if not config_path.exists():
            raise FileNotFoundError(f"Semantic mapping config not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for scenario_key, scenario_data in data.items():
            self._configs[scenario_key] = ScenarioConfig(scenario_data)

    def get_scenario(self, scenario_name: str) -> Optional[ScenarioConfig]:
        """Get configuration for a specific scenario

        Args:
            scenario_name: Scenario identifier (e.g., "weight-loss", "phone-addiction")

        Returns:
            ScenarioConfig object or None if not found
        """
        return self._configs.get(scenario_name)

    def get_scenario_for_agent(self, agent_name: str) -> Optional[ScenarioConfig]:
        """Find scenario where agent is either target or manager

        Args:
            agent_name: Agent's name

        Returns:
            ScenarioConfig object or None if agent not found in any scenario
        """
        for config in self._configs.values():
            if agent_name in [config.target_agent, config.manager_agent]:
                return config
        return None

    def list_scenarios(self) -> List[str]:
        """Get list of all available scenario names"""
        return list(self._configs.keys())


# Singleton instance
_loader = None


def get_scenario_config(scenario_name: str) -> Optional[ScenarioConfig]:
    """Get configuration for a specific scenario

    Args:
        scenario_name: Scenario identifier

    Returns:
        ScenarioConfig object or None if not found
    """
    global _loader
    if _loader is None:
        _loader = ScenarioConfigLoader()
    return _loader.get_scenario(scenario_name)


def get_agent_scenario(agent_name: str) -> Optional[ScenarioConfig]:
    """Find scenario configuration for a specific agent

    Args:
        agent_name: Agent's name

    Returns:
        ScenarioConfig object or None if agent not in any scenario
    """
    global _loader
    if _loader is None:
        _loader = ScenarioConfigLoader()
    return _loader.get_scenario_for_agent(agent_name)
