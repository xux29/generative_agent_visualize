"""active.json 参数路径 → 中文名 + 解释（供验参 Canvas / 手册使用）。"""

from __future__ import annotations

from typing import Dict, Tuple

# 叶子 / 片段词典
_TOKEN_ZH: Dict[str, str] = {
    "self_discipline": "自律等级",
    "addiction_level": "成瘾程度",
    "resistance_to_persuasion": "劝说抵抗基线",
    "initial_health": "初始健康分",
    "habit_formation_speed": "习惯形成速度",
    "warning_line": "健康警戒线",
    "plateau_duration": "平台期天数",
    "decline_rate": "平台后下滑速度",
    "mood_sensitivity": "心情敏感度",
    "violation_penalty": "违规扣分",
    "compliance_bonus": "遵从奖励",
    "improvement_threshold": "自律提升所需连好天数",
    "max_penalty": "单日最大扣分",
    "per_day": "每日习惯加成",
    "cap": "习惯加成上限",
    "lt_30": "健康<30 惩罚缩放",
    "lt_40": "健康<40 惩罚缩放",
    "lt_50": "健康<50 惩罚缩放",
    "lt_60": "健康<60 惩罚缩放",
    "lt_70": "健康<70 惩罚缩放",
    "else": "其它区间惩罚缩放",
    "sensitivity": "区间敏感度",
    "recovery_mult": "区间恢复倍率",
    "range": "分数区间",
    "violation_penalty_range": "违规扣分抽样范围",
    "cumulative_factor": "连续违规累积系数",
    "noise_sigma": "日变化噪声",
    "resilience": "抗压/回弹",
    "base_prob": "复发基础概率",
    "days_divisor": "放松时间除数",
    "per_unit": "每单位放松增量",
    "streak_factor": "习惯抑制系数",
    "floor": "习惯抑制下限",
    "tendency_weight": "复发倾向权重",
    "delta_good": "好天后倾向变化",
    "delta_bad": "坏天后倾向变化",
    "delta_relapse": "复发后倾向变化",
    "base_score": "基线分",
    "max_day": "阶段截止天",
    "per_intervention": "每次干预惩罚",
    "level_1": "一级干预惩罚",
    "level_2": "二级干预惩罚",
    "level_3": "三级干预惩罚",
    "health_lt": "忽视惩罚健康阈值",
    "when_no_intervention": "零干预忽视惩罚",
    "health_danger_lt": "危险健康阈值",
    "when_weak_intervention": "弱干预忽视惩罚",
    "min_level": "触发最低干预等级",
    "amount": "惩罚幅度",
    "intensity_weight": "干预强度权重",
    "revolt_chance_factor": "反抗概率系数",
    "low_resistance_persuade_threshold": "低抵抗劝通阈值",
    "low_resistance_persuade_chance": "低抵抗劝通概率",
    "streak_good_delta": "好天 streak 增量",
    "streak_bad_reset": "坏天后 streak 重置值",
    "tendency_delta_good": "好天倾向变化",
    "tendency_delta_bad": "坏天倾向变化",
    "autonomous": "自主阶段阈值",
    "internalized": "内化阶段阈值",
    "compliant": "顺从阶段阈值",
    "reasonable": "合理干预修正",
    "preventive": "预防性干预修正",
    "unnecessary": "多余干预修正",
    "intervention_sensitivity": "阶段干预敏感度",
    "base": "阶段基线偏移",
    "min_habit_streak": "过管判定·最低习惯天数",
    "min_health_score": "过管判定·最低健康",
    "base_penalty": "过管基础惩罚",
    "health_extra_per_point": "过管·健康额外惩罚",
    "streak_extra_per_day": "过管·streak 额外惩罚",
    "streak_extra_cap_days": "过管·streak 额外封顶天数",
    "level3_extra": "过管·L3 额外惩罚",
    "high_count_threshold": "过管·高频干预次数阈",
    "high_count_health": "过管·高频时健康阈",
    "high_count_extra": "过管·高频额外惩罚",
    "autonomy_modifier_cap": "自主选项满意度上限",
    "health": "健康权重/分项",
    "satisfaction": "满意度权重",
    "effectiveness": "效果权重",
    "excellent": "优秀阈",
    "good": "良好阈",
    "neutral": "中性阈",
    "poor": "较差阈",
    "A": "评级 A 阈",
    "B": "评级 B 阈",
    "C": "评级 C 阈",
    "D": "评级 D 阈",
    "max_level": "最高干预等级",
    "health_threshold_bad": "坏天健康阈值",
    "health_threshold_good": "好天健康阈值",
    "consecutive_good_days_to_relax": "连好后放松所需天数",
    "consecutive_bad_days_to_escalate": "连坏后升级所需天数",
    "relapse_probability_base": "策略侧复发基线",
    "patience_weight": "耐心权重",
    "initial": "初值",
    "good_delta": "好天变化量",
    "bad_delta": "坏天变化量",
    "over_intervention_delta": "过管信任变化",
    "relax_min": "放松所需最低信任",
    "good_streak_bonus_per_day": "连好信任日加成",
    "good_streak_bonus_cap": "连好信任加成上限",
    "good_streak_bonus_min_days": "连好加成起始天数",
    "intervention_modifier": "阶段干预倍率",
    "trust_earn_bonus": "阶段信任赚取倍率",
    "min_days": "最少停留天数",
    "conflict_threshold": "冲突退出阈",
    "intervention_resistance": "干预抵抗退出阈",
    "habit_compliance_rate": "习惯遵从率退出阈",
    "consecutive_good_days": "连好退出阈",
    "habit_internalization": "内化退出要求",
    "autonomy_level": "自主等级退出要求",
    "initial_capital": "初始信任资本",
    "max_capital": "信任资本上限",
    "min_capital": "信任资本下限",
    "high": "高档",
    "medium": "中档",
    "low": "低档",
    "very_low": "极低档",
    "very_high": "极高档",
    "none": "无",
    "moderate": "中等",
    "severe": "严重",
    "good_earn": "好天赚取",
    "proactive_earn": "主动行为赚取",
    "no_intervention_earn": "无干预赚取",
    "bad_loss": "坏天损失",
    "stable_bad_loss": "稳定期坏天损失",
    "relapse_loss": "复发损失",
    "no_intervention": "无干预证据权重",
    "proactive": "主动行为权重",
    "emotion": "情绪对齐权重",
    "min_opportunities": "最少观察次数",
    "success_understanding_delta_factor": "成功时理解度增速",
    "fail_understanding_delta": "失败时理解度增量",
    "cycle_understanding_delta_factor": "周期完成理解度增速",
    "efficiency_delta_low_level": "低强度成功效率增量",
    "efficiency_delta_high_level": "高强度成功效率增量",
    "early_intervention_base": "早干预阈值基数",
    "early_intervention_understanding_scale": "早干预·理解度缩放",
    "efficiency_from_understanding_scale": "效率←理解度缩放",
    "medium_min_base_level": "降级所需最低基线等级",
    "trend_understanding_min": "趋势判断最低理解度",
    "trend_avg_delta_threshold": "趋势平均变化阈",
    "emotion_warning_threshold": "情绪警告阈",
    "emotion_critical_threshold": "情绪危急阈",
    "high_trust_threshold": "高信任阈",
    "medium_trust_threshold": "中信任阈",
    "health_safe_threshold": "健康安全阈",
    "max_consecutive_high_interventions": "连续高强度干预上限",
    "low_emotion_days": "强制放松·低情绪天数",
    "duration_days": "强制放松持续天数",
    "high_intensity_min_level": "高强度最低等级",
    "soften_min_health": "软化所需最低健康",
    "weekly_period_days": "周反思周期",
    "monthly_period_days": "月反思周期",
    "weekly_high_intervention_threshold": "周干预过多阈",
    "weekly_low_intervention_threshold": "周干预过少阈",
    "baseline_minutes": "公式基线分钟",
    "coefficient": "公式系数",
    "coefficients": "场景系数",
    "sleep": "睡眠场景",
    "weight": "减肥场景",
    "diabetes": "糖尿病场景",
    "high_sugar_fat": "高糖高脂",
    "low_sugar_fat": "低糖低脂",
    "high_gi": "高升糖",
    "low_gi": "低升糖",
    "processed": "加工食品",
    "healthy": "健康食物",
    "excessive": "过量",
    "insufficient": "不足",
    "before_22": "22点前结束",
    "22_to_24": "22–24点结束",
    "0_to_1": "0–1点结束",
    "after_1": "凌晨1点后结束",
    "work": "工作用途",
    "gaming": "游戏",
    "video": "刷视频",
    "social": "社交",
    "emergency": "紧急区",
    "danger": "危险区",
    "warning": "预警区",
    "normal": "正常区",
    "safe": "安全区",
    "adjustment": "适应期",
    "formation": "形成期",
    "fatigue": "疲劳期",
    "honeymoon": "蜜月期",
    "stable": "稳定期",
    "relapse": "复发期",
    "food_type": "食物种类分项",
    "food_amount": "食量分项",
    "phone_end_time": "手机结束时间分项",
    "phone_activity": "手机活动类型分项",
    "meal_sleep_interval": "餐睡间隔公式",
    "continuous_phone": "连续刷机时长公式",
    "habit_bonus": "习惯恢复加成",
    "floor_protection": "低分区惩罚保护",
    "health_zones": "健康分区",
    "discipline_params": "按自律分档参数",
    "nonlinear": "非线性健康分",
    "discipline_mod": "自律复发乘子",
    "addiction_mod": "成瘾复发乘子",
    "time_mod": "放松时间修正",
    "habit_mod": "习惯复发抑制",
    "tendency_mod": "复发倾向修正",
    "phase_distributions": "阶段情绪分布",
    "frequency_penalty": "频率惩罚",
    "intensity_penalty": "强度惩罚",
    "habit_bonus_thresholds": "习惯心情加成阈",
    "neglect_penalty": "忽视惩罚",
    "plateau_penalty": "平台期强管惩罚",
    "discipline_accept_rate": "自觉/劝说接受率",
    "addiction_resistance_mod": "成瘾→抵抗修正",
    "discipline_resistance_mod": "自律→抵抗修正",
    "streak_modifier_thresholds": "streak→满意度修正阈",
    "internalization_thresholds": "内化阶段阈值",
    "intervention_level_weights": "干预等级满意度权重",
    "intervention_reasonability": "干预合理性修正",
    "discipline_phase_modifiers": "阶段满意度修正",
    "overintervention": "过管惩罚块",
    "weights": "权重",
    "effectiveness_thresholds": "效果分档阈",
    "rating_thresholds": "字母评级阈",
    "forced_relaxation": "强制放松",
    "efficiency_downgrade": "效率降级规则",
    "autonomy_thresholds": "自主档位资本阈",
    "daily": "日结算",
    "stage_thresholds": "阶段阈值",
    "exit_conditions": "退出条件",
    "trust_level": "潮汐信任",
    "scenarios": "场景配置",
    "weight_loss": "减肥场景配置",
    "moods": "情绪标签池",
    "over_intervention": "过管保护",
    "manager_learning": "管理者学习",
    "habit_consolidation": "习惯巩固",
    "trust_capital": "信任资本",
    "relationship_phases": "关系阶段",
    "intervention": "干预等级",
    "tidal": "潮汐松紧",
    "reflection": "周期反思",
    "subject": "主体",
    "relapse": "复发",
    "mood": "心情",
    "compliance": "遵从",
    "habit": "习惯",
    "satisfaction": "满意度",
    "composite": "综合评估",
    "behavior_scores": "行为分项",
}

_EXPLAIN: Dict[str, str] = {
    "simulation.subject.self_discipline": "被管者自律档位；影响健康扣分轻重、复发乘子、劝说接受率等。",
    "simulation.subject.addiction_level": "成瘾强度；越高越易复发、越难劝通。",
    "simulation.subject.resistance_to_persuasion": "对劝说的基础抵抗；越高越需要更强干预。",
    "simulation.subject.initial_health": "仿真开始时的健康分起点。",
    "simulation.subject.habit_formation_speed": "习惯形成快慢（主要影响 prompt 叙事）。",
    "simulation.relapse.base_prob": "管理者放松后，被管者「又干坏事」的基础概率。",
    "simulation.mood.base_score": "日心情分计算的起点。",
    "simulation.satisfaction.base_score": "日满意度计算的起点。",
    "management.intervention.max_level": "允许的最高干预等级（观察/劝说/移除/封锁）。",
    "management.tidal.trust_level.relax_min": "信任达到该值才允许潮汐式放松管控。",
    "management.trust_capital.initial_capital": "信任资本账户开局余额。",
    "management.over_intervention.emotion_critical_threshold": "情绪低于此值时更容易触发过管保护/强制松手。",
}


def _token_name(tok: str) -> str:
    if tok in _TOKEN_ZH:
        return _TOKEN_ZH[tok]
    if tok.isdigit():
        return f"{tok}天阈"
    return tok


def describe_param(path: str) -> Tuple[str, str]:
    """Return (中文名, 解释) for a dotted mechanism path."""
    if path in _EXPLAIN:
        # still build a short name from tokens
        parts = path.split(".")
        name = " · ".join(_token_name(p) for p in parts[2:] if p not in {"simulation", "management"})
        if not name:
            name = _token_name(parts[-1])
        return name, _EXPLAIN[path]

    parts = path.split(".")
    # drop simulation/management root
    core = parts[1:] if parts and parts[0] in {"simulation", "management"} else parts

    # behavior score pattern
    if len(core) >= 2 and core[0] == "behavior_scores":
        name = " · ".join(_token_name(p) for p in core[1:])
        scene = ""
        if core[-1] in {"sleep", "weight", "diabetes"}:
            scene = f"作用于{_token_name(core[-1])}；"
        return (
            name,
            f"{scene}该行为在分项表中的记分：升高=记分变宽（更「便宜」），降低=记分变严。",
        )

    # health zone
    if "health_zones" in core:
        name = " · ".join(_token_name(p) for p in core[core.index("health_zones") :])
        return name, "非线性健康分区规则：敏感度影响波动，恢复倍率影响回血快慢。"

    # discipline_params
    if "discipline_params" in core:
        idx = core.index("discipline_params")
        name = " · ".join(_token_name(p) for p in core[idx:])
        level = core[idx + 1] if idx + 1 < len(core) else ""
        level_zh = _token_name(level) if level else ""
        return name, f"仅当被管者自律为「{level_zh}」时生效的分档参数。"

    # tidal scenarios
    if "tidal" in core and "scenarios" in core:
        name = " · ".join(_token_name(p) for p in core[core.index("tidal") :])
        return name, "潮汐松紧策略：决定何时算好/坏天、何时放松或升级干预。"

    # relationship phases
    if "relationship_phases" in core:
        name = " · ".join(_token_name(p) for p in core[core.index("relationship_phases") :])
        return name, "长期关系阶段配置：干预倍率、信任赚取与阶段切换条件。"

    # relapse mods by enum key
    if core[0] == "relapse" and len(core) >= 3:
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "复发概率公式中的乘子或增量；升高通常使该条件下更易复发（或更强抑制，视字段语义）。"

    # mood phase moods list skipped usually; max_day etc.
    if core[0] == "mood":
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "心情分计算相关：基线、干预频率/强度惩罚、忽视与平台期不满等。"

    if core[0] == "compliance":
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "劝说服从与抵抗：接受率与抵抗修正共同决定能否劝通、是否需升级干预。"

    if core[0] == "habit":
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "习惯 streak / 倾向 / 内化：连好连坏如何改习惯状态，并联动复发与满意度。"

    if core[0] == "satisfaction":
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "对被管体验的满意度：干预是否过频、过强、不合理会拉低该分。"

    if core[0] == "composite":
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "综合评估卷面分：权重与评级阈值主要影响报告叙事，弱于日循环动力学。"

    if core[0] == "health":
        name = " · ".join(_token_name(p) for p in core[1:])
        return name, "健康分演算：警戒线、分区、违规惩罚、低分保护等决定曲线起伏。"

    # management generic
    if parts[0] == "management":
        name = " · ".join(_token_name(p) for p in core)
        bucket = core[0] if core else ""
        tips = {
            "trust_capital": "信任资本账户：赚取/损失决定能给多少自主权。",
            "habit_consolidation": "习惯巩固：用无干预自觉、主动行为等证据判断内化阶段。",
            "manager_learning": "管理者学习：成功/失败经验改变理解度与干预效率。",
            "over_intervention": "过管保护：情绪过低或连着狠管时强制降温。",
            "reflection": "周期反思：周/月回顾触发策略调整的时间窗与阈值阈。",
            "intervention": "干预等级上限与动作映射。",
            "tidal": "短期潮汐松紧与信任。",
            "relationship_phases": "长期关系阶段。",
        }
        return name, tips.get(bucket, "管理侧策略参数，影响管多严、何时放手、如何学习。")

    name = " · ".join(_token_name(p) for p in core)
    return name or path, "机制配置参数；升高/降低后见实测列对模拟侧面的影响。"
