"""界面可调参数语义、JSON 映射与模拟影响（供专家 UI 与 AI 编辑共用）。

权威文档：docs/界面可调参数.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from modules.mechanism_config.ui_tunable import UI_PARAM_SPECS, read_ui_param


@dataclass(frozen=True)
class UiParamGuideEntry:
    key: str
    label: str
    section: str
    slider_low: str
    slider_high: str
    meaning: str
    mechanism: str
    formula: str
    json_mapping: str
    increase_effect: str
    decrease_effect: str
    related_ui: List[str] = field(default_factory=list)
    hidden_context: str = ""
    tab_kpis: str = ""


UI_PARAM_GUIDE: Dict[str, UiParamGuideEntry] = {
    "penaltyStrength": UiParamGuideEntry(
        key="penaltyStrength",
        label='违规扣分（非线性）',
        section="health",
        slider_low='轻',
        slider_high='重',
        meaning='未阻止违规的基础扣分力度',
        mechanism='健康分演算',
        formula='penalty = min(penaltyStrength × √(health/100) × (1 + cumulativeSpeed × consecutiveViolations), dailyPenaltyCap)',
        json_mapping='缩放 simulation.health.nonlinear.discipline_params.*.violation_penalty_range',
        increase_effect='违规后健康分掉得更快。',
        decrease_effect='违规惩罚减轻。',
        related_ui=['cumulativeSpeed', 'dailyPenaltyCap', 'complianceBonus'],
        hidden_context='按自律档位成比例缩放扣分区间。',
        tab_kpis='Tab2',
    ),
    "complianceBonus": UiParamGuideEntry(
        key="complianceBonus",
        label='遵从加分',
        section="health",
        slider_low='少',
        slider_high='多',
        meaning='无违规时健康分恢复量，上限≤初始分',
        mechanism='健康分演算',
        formula='无违规日 health += complianceBonus',
        json_mapping='simulation.health.discipline_params.*.compliance_bonus',
        increase_effect='好天数更容易回血。',
        decrease_effect='遵从加分变少。',
        related_ui=['penaltyStrength', 'plateauStubbornness'],
        tab_kpis='Tab2',
    ),
    "cumulativeSpeed": UiParamGuideEntry(
        key="cumulativeSpeed",
        label='连续犯规加速下滑',
        section="health",
        slider_low='缓',
        slider_high='急',
        meaning='连续犯规后加速下滑',
        mechanism='健康分演算',
        formula='× (1 + cumulativeSpeed × consecutiveViolations)',
        json_mapping='simulation.health.nonlinear.discipline_params.*.cumulative_factor',
        increase_effect='连续犯规雪崩更快。',
        decrease_effect='累积惩罚更温和。',
        related_ui=['penaltyStrength', 'dailyPenaltyCap'],
        tab_kpis='Tab2',
    ),
    "plateauStubbornness": UiParamGuideEntry(
        key="plateauStubbornness",
        label='平台期机制',
        section="health",
        slider_low='易破',
        slider_high='顽固',
        meaning='连续好天后进入平台期的长度（天）',
        mechanism='健康分演算',
        formula='平台期持续 plateauStubbornness 天',
        json_mapping='simulation.health.nonlinear.discipline_params.*.plateau_duration',
        increase_effect='平台更顽固。',
        decrease_effect='平台更易打破。',
        related_ui=['complianceBonus'],
        tab_kpis='Tab2',
    ),
    "dailyPenaltyCap": UiParamGuideEntry(
        key="dailyPenaltyCap",
        label='每日最大扣分限制',
        section="health",
        slider_low='低',
        slider_high='高',
        meaning='单日扣分上限，防止单日崩溃',
        mechanism='健康分演算',
        formula='单日扣分 capped by dailyPenaltyCap',
        json_mapping='simulation.health.nonlinear.max_penalty（负数绝对值）',
        increase_effect='允许单日扣更多。',
        decrease_effect='单日扣分天花板更低。',
        related_ui=['penaltyStrength'],
        tab_kpis='Tab2',
    ),
    "noiseSigma": UiParamGuideEntry(
        key="noiseSigma",
        label='日常随机波动',
        section="health",
        slider_low='小',
        slider_high='大',
        meaning='每日健康分随机扰动幅度',
        mechanism='健康分演算',
        formula='noise ~ N(0, noiseSigma)',
        json_mapping='simulation.health.nonlinear.discipline_params.*.noise_sigma',
        increase_effect='曲线更抖。',
        decrease_effect='更平滑。',
        related_ui=[],
        tab_kpis='Tab2',
    ),
    "baseRelapseProb": UiParamGuideEntry(
        key="baseRelapseProb",
        label='违规基础概率',
        section="relapse",
        slider_low='低',
        slider_high='高',
        meaning='基准违规概率（放松后再次违规的可能性）',
        mechanism='违规概率',
        formula='prob = baseProb × 自律 × 成瘾 × 放松时间 × 习惯 + 倾向',
        json_mapping='simulation.relapse.base_prob',
        increase_effect='放松后更易违规。',
        decrease_effect='更不易违规。',
        related_ui=['disciplineCorrection', 'relaxTimeSensitivity'],
        tab_kpis='Tab3',
    ),
    "disciplineCorrection": UiParamGuideEntry(
        key="disciplineCorrection",
        label='自律修正',
        section="relapse",
        slider_low='放大',
        slider_high='缩小',
        meaning='控制自律对违规的放大/缩小倍数',
        mechanism='违规概率',
        formula='× discipline_mod[self_discipline]',
        json_mapping='缩放 simulation.relapse.discipline_mod.*',
        increase_effect='自律放大/保护更强（数值越大表倍率越大）。',
        decrease_effect='自律影响变弱。',
        related_ui=['baseRelapseProb'],
        hidden_context='滑杆左=放大(高值)、右=缩小(低值)，inverted。',
        tab_kpis='Tab3',
    ),
    "addictionCorrection": UiParamGuideEntry(
        key="addictionCorrection",
        label='成瘾修正',
        section="relapse",
        slider_low='弱',
        slider_high='强',
        meaning='成瘾越重，违规概率放大越多',
        mechanism='违规概率',
        formula='× addiction_mod[addiction]',
        json_mapping='缩放 simulation.relapse.addiction_mod.*',
        increase_effect='成瘾放大更强。',
        decrease_effect='成瘾影响减弱。',
        related_ui=['baseRelapseProb'],
        tab_kpis='Tab3',
    ),
    "relaxTimeSensitivity": UiParamGuideEntry(
        key="relaxTimeSensitivity",
        label='放松时间',
        section="relapse",
        slider_low='迟钝',
        slider_high='敏锐',
        meaning='放松越久，违规概率上升速度',
        mechanism='违规概率',
        formula='放松天数上升速度',
        json_mapping='simulation.relapse.time_mod.per_unit',
        increase_effect='放松后违规概率涨更快。',
        decrease_effect='上升更慢。',
        related_ui=['baseRelapseProb'],
        tab_kpis='Tab3',
    ),
    "habitProtection": UiParamGuideEntry(
        key="habitProtection",
        label='习惯保护',
        section="relapse",
        slider_low='弱',
        slider_high='强',
        meaning='连续无违规天数越长，违规概率越低',
        mechanism='违规概率',
        formula='1 - streak × streak_factor',
        json_mapping='simulation.relapse.habit_mod.streak_factor',
        increase_effect='习惯抑制更强。',
        decrease_effect='保护弱。',
        related_ui=['baseRelapseProb'],
        tab_kpis='Tab3',
    ),
    "relapseSwing": UiParamGuideEntry(
        key="relapseSwing",
        label='复发倾向',
        section="relapse",
        slider_low='小',
        slider_high='大',
        meaning='复发倾向摆幅（加项）',
        mechanism='违规概率',
        formula='+ tendency × weight',
        json_mapping='simulation.relapse.tendency_mod.tendency_weight',
        increase_effect='倾向摆幅更大。',
        decrease_effect='摆幅更小。',
        related_ui=['baseRelapseProb'],
        tab_kpis='Tab3',
    ),
    "baseSatisfaction": UiParamGuideEntry(
        key="baseSatisfaction",
        label='基础满意度',
        section="satisfaction",
        slider_low='低',
        slider_high='高',
        meaning='满意度基线',
        mechanism='满意度',
        formula='base - 强度 - 频率 - 过管 + 替代 + 时机',
        json_mapping='simulation.satisfaction.base_score',
        increase_effect='基线更高。',
        decrease_effect='基线更低。',
        related_ui=['interventionSensitivity'],
        tab_kpis='Tab4',
    ),
    "interventionSensitivity": UiParamGuideEntry(
        key="interventionSensitivity",
        label='干预强度扣分',
        section="satisfaction",
        slider_low='轻',
        slider_high='重',
        meaning='干预等级越高，满意度扣分越多',
        mechanism='满意度',
        formula='强度扣分 ∝ level × sensitivity',
        json_mapping='intervention_level_weights + phase sensitivity',
        increase_effect='高强度干预更招反感。',
        decrease_effect='强度伤害小。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab4',
    ),
    "frequencyPenalty": UiParamGuideEntry(
        key="frequencyPenalty",
        label='干预频率扣分',
        section="satisfaction",
        slider_low='轻',
        slider_high='重',
        meaning='干预次数越多，满意度扣分越多',
        mechanism='满意度',
        formula='次数 × frequencyPenalty',
        json_mapping='simulation.satisfaction.frequency_penalty.per_intervention',
        increase_effect='频繁干预更伤满意度。',
        decrease_effect='频率伤害小。',
        related_ui=['interventionTendency'],
        tab_kpis='Tab4',
    ),
    "overInterventionPenalty": UiParamGuideEntry(
        key="overInterventionPenalty",
        label='过度干预扣分',
        section="satisfaction",
        slider_low='轻',
        slider_high='重',
        meaning='健康分高于警戒线仍严管时触发',
        mechanism='满意度',
        formula='健康高仍严管 → 扣分',
        json_mapping='simulation.satisfaction.overintervention.base_penalty',
        increase_effect='过管更不满。',
        decrease_effect='过管惩罚轻。',
        related_ui=['healthSafeThreshold'],
        tab_kpis='Tab4',
    ),
    "alternativeCompensation": UiParamGuideEntry(
        key="alternativeCompensation",
        label='替代加分',
        section="satisfaction",
        slider_low='少',
        slider_high='多',
        meaning='提供替代选项时满意度的补偿分',
        mechanism='满意度',
        formula='+ 替代补偿',
        json_mapping='simulation.satisfaction.autonomy_modifier_cap',
        increase_effect='给替代时加更多分。',
        decrease_effect='补偿少。',
        related_ui=['timelinessEffect'],
        tab_kpis='Tab4',
    ),
    "timelinessEffect": UiParamGuideEntry(
        key="timelinessEffect",
        label='合理干预加分',
        section="satisfaction",
        slider_low='弱',
        slider_high='强',
        meaning='及时干预效果好时满意度加分',
        mechanism='满意度',
        formula='+ 合理干预加分',
        json_mapping='simulation.satisfaction.intervention_reasonability.reasonable',
        increase_effect='及时干预更增满意度。',
        decrease_effect='加分弱。',
        related_ui=['baseSatisfaction'],
        tab_kpis='Tab4',
    ),
    "interventionIntensity": UiParamGuideEntry(
        key="interventionIntensity",
        label='干预强度',
        section="management",
        slider_low='温和',
        slider_high='强硬',
        meaning='直接决定松紧度',
        mechanism='管理机制',
        formula='tightness = intensity × 阶段mod',
        json_mapping='management.intervention.intensity',
        increase_effect='整体更强硬。',
        decrease_effect='整体更温和。',
        related_ui=['HONEYMOON.mod', 'ADJUSTMENT.mod'],
        tab_kpis='Tab5',
    ),
    "interventionTendency": UiParamGuideEntry(
        key="interventionTendency",
        label='干预倾向',
        section="management",
        slider_low='保守',
        slider_high='激进',
        meaning='越激进→L0观察概率越低→实际干预率越高',
        mechanism='管理机制',
        formula='early_intervention_base 反向映射',
        json_mapping='management.manager_learning.early_intervention_base',
        increase_effect='更早更勤干预。',
        decrease_effect='更常观察。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "healthSafeThreshold": UiParamGuideEntry(
        key="healthSafeThreshold",
        label='健康分阈值',
        section="management",
        slider_low='低',
        slider_high='高',
        meaning='健康分高于此值时可放松干预',
        mechanism='管理机制',
        formula='health > threshold 可放松',
        json_mapping='management.over_intervention.health_safe_threshold（UI 50–90）',
        increase_effect='更高才放松。',
        decrease_effect='更容易放松。',
        related_ui=['SatisfactionWarning'],
        tab_kpis='Tab5',
    ),
    "SatisfactionWarning": UiParamGuideEntry(
        key="SatisfactionWarning",
        label='满意度阈值',
        section="management",
        slider_low='低',
        slider_high='高',
        meaning='满意度低于此值时触发满意度保护机制',
        mechanism='管理机制',
        formula='满意度/情绪低于阈值触发保护',
        json_mapping='management.over_intervention.emotion_warning_threshold',
        increase_effect='保护更易触发。',
        decrease_effect='只有更差才触发。',
        related_ui=['baseSatisfaction'],
        tab_kpis='Tab5',
    ),
    "HONEYMOON.mod": UiParamGuideEntry(
        key="HONEYMOON.mod",
        label='蜜月期强度修正',
        section="phase_honeymoon",
        slider_low='温和',
        slider_high='偏严',
        meaning='蜜月期整体干预修正系数（默认 0.8）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / honeymoon.intervention_modifier',
        increase_effect='阶段干预更严。',
        decrease_effect='阶段干预更温和。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "HONEYMOON.trustMul": UiParamGuideEntry(
        key="HONEYMOON.trustMul",
        label='蜜月期信任放大',
        section="phase_honeymoon",
        slider_low='弱',
        slider_high='强',
        meaning='信任→干预修正的放大倍数（默认 1.5）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / honeymoon.trust_earn_bonus',
        increase_effect='信任赚取更快。',
        decrease_effect='信任赚取变慢。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "HONEYMOON.minDays": UiParamGuideEntry(
        key="HONEYMOON.minDays",
        label='蜜月期最短天数',
        section="phase_honeymoon",
        slider_low='短',
        slider_high='长',
        meaning='蜜月期最短保持天数（默认 3）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / honeymoon.exit_conditions.min_days',
        increase_effect='蜜月更长。',
        decrease_effect='蜜月更短。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "HONEYMOON.conflictThreshold": UiParamGuideEntry(
        key="HONEYMOON.conflictThreshold",
        label='蜜月期冲突退出线',
        section="phase_honeymoon",
        slider_low='少',
        slider_high='多',
        meaning='累计冲突达此次数后退出蜜月期（默认 2）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / honeymoon.exit_conditions.conflict_threshold',
        increase_effect='更能容忍冲突。',
        decrease_effect='更早因冲突退出。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "ADJUSTMENT.mod": UiParamGuideEntry(
        key="ADJUSTMENT.mod",
        label='磨合期强度修正',
        section="phase_adjustment",
        slider_low='轻',
        slider_high='重',
        meaning='磨合期整体干预修正系数（默认 1.0）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / adjustment.intervention_modifier',
        increase_effect='磨合更严。',
        decrease_effect='磨合更轻。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "ADJUSTMENT.minDays": UiParamGuideEntry(
        key="ADJUSTMENT.minDays",
        label='磨合期最短天数',
        section="phase_adjustment",
        slider_low='短',
        slider_high='长',
        meaning='磨合期最短保持天数（默认 7）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / adjustment.exit_conditions.min_days',
        increase_effect='磨合最短期更长。',
        decrease_effect='更快可退出磨合。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "ADJUSTMENT.complianceThreshold": UiParamGuideEntry(
        key="ADJUSTMENT.complianceThreshold",
        label='磨合期退出遵从率',
        section="phase_adjustment",
        slider_low='低',
        slider_high='高',
        meaning='退出磨合期所需的最低遵从率（默认 0.6）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / adjustment.exit_conditions.habit_compliance_rate',
        increase_effect='退出要求更高遵从。',
        decrease_effect='更容易退出。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "ADJUSTMENT.streakThreshold": UiParamGuideEntry(
        key="ADJUSTMENT.streakThreshold",
        label='磨合期退出连好天数',
        section="phase_adjustment",
        slider_low='短',
        slider_high='长',
        meaning='退出磨合期所需的连续好天数（默认 5）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / adjustment.exit_conditions.consecutive_good_days',
        increase_effect='需更长连好。',
        decrease_effect='较短连好即可退出。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "FATIGUE.mod": UiParamGuideEntry(
        key="FATIGUE.mod",
        label='倦怠期强度修正',
        section="phase_fatigue",
        slider_low='轻',
        slider_high='重',
        meaning='倦怠期整体干预修正系数（默认 0.9）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / fatigue.intervention_modifier',
        increase_effect='倦怠期更严。',
        decrease_effect='倦怠期更轻。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "FATIGUE.minDays": UiParamGuideEntry(
        key="FATIGUE.minDays",
        label='倦怠期最短天数',
        section="phase_fatigue",
        slider_low='短',
        slider_high='长',
        meaning='倦怠期最短保持天数（默认 14）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / fatigue.exit_conditions.min_days',
        increase_effect='倦怠最短期更长。',
        decrease_effect='更快可离开倦怠。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "FATIGUE.internalizationReq": UiParamGuideEntry(
        key="FATIGUE.internalizationReq",
        label='倦怠期内化要求',
        section="phase_fatigue",
        slider_low='低',
        slider_high='高',
        meaning='退出倦怠期所需的内化分阈值',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / habit_consolidation.stage_thresholds.internalized + fatigue exit',
        increase_effect='需更高内化才进稳定。',
        decrease_effect='较低内化即可。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "STABLE.mod": UiParamGuideEntry(
        key="STABLE.mod",
        label='稳定期强度修正',
        section="phase_stable",
        slider_low='轻',
        slider_high='重',
        meaning='稳定期整体干预修正系数（默认 0.6）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / stable.intervention_modifier',
        increase_effect='稳定期仍偏严。',
        decrease_effect='稳定期更宽松。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "STABLE.trustMul": UiParamGuideEntry(
        key="STABLE.trustMul",
        label='稳定期信任修正',
        section="phase_stable",
        slider_low='弱',
        slider_high='强',
        meaning='稳定期信任→干预修正系数（默认 0.8）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / stable.trust_earn_bonus',
        increase_effect='稳定期信任加成强。',
        decrease_effect='信任加成弱。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "RELAPSE.mod": UiParamGuideEntry(
        key="RELAPSE.mod",
        label='复发期强度修正',
        section="phase_relapse",
        slider_low='轻',
        slider_high='重',
        meaning='复发期干预加严幅度（默认 1.3）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / relapse.intervention_modifier',
        increase_effect='复发期加严更多。',
        decrease_effect='复发期加严较少。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "RELAPSE.trustMul": UiParamGuideEntry(
        key="RELAPSE.trustMul",
        label='复发期信任修正',
        section="phase_relapse",
        slider_low='弱',
        slider_high='强',
        meaning='复发期信任→干预修正系数（默认 0.5）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / relapse.trust_earn_bonus',
        increase_effect='复发期信任恢复快。',
        decrease_effect='信任恢复慢。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
    "RELAPSE.streakThreshold": UiParamGuideEntry(
        key="RELAPSE.streakThreshold",
        label='复发期退出连好天数',
        section="phase_relapse",
        slider_low='短',
        slider_high='长',
        meaning='退出复发期所需的连续好天数（默认 5）',
        mechanism='长期关系阶段',
        formula='LongTermStrategyManager.PHASE_CONFIG',
        json_mapping='management.relationship_phases / relapse.exit_conditions.consecutive_good_days',
        increase_effect='需更长连好退出复发。',
        decrease_effect='较短即可退出。',
        related_ui=['interventionIntensity'],
        tab_kpis='Tab5',
    ),
}

SECTION_FORMULAS = {
    "health": "健康分演算：penalty = min(penaltyStrength × √(health/100) × (1 + cumulativeSpeed × 连违规), dailyPenaltyCap)",
    "relapse": "违规概率：prob = baseProb × 自律 × 成瘾 × 放松时间 × 习惯 + 倾向",
    "satisfaction": "满意度：基础 - 强度扣分 - 频率扣分 - 过管 + 替代 + 时机",
    "management": "管理：intensity×阶段mod 定松紧；tendency 定出手快慢；阈值触发保护",
    "phase_honeymoon": "蜜月期：建立规则，冲突达线退出",
    "phase_adjustment": "磨合期：遵从率与连好天数控制退出",
    "phase_fatigue": "倦怠期：内化分与最短天数",
    "phase_stable": "稳定期：低干预维持",
    "phase_relapse": "复发期：加严后连好退出",
}


def get_ui_param_guide(ui_key: str) -> Dict[str, Any]:
    from modules.mechanism_config.ui_tunable import _resolve_ui_key
    ui_key = _resolve_ui_key(ui_key)
    entry = UI_PARAM_GUIDE.get(ui_key)
    if not entry:
        raise KeyError(ui_key)
    spec = next(s for s in UI_PARAM_SPECS if s.key == ui_key)
    return {
        "key": entry.key,
        "label": entry.label,
        "section": entry.section,
        "section_formula": SECTION_FORMULAS.get(entry.section, ""),
        "slider_range": f"{entry.slider_low} ↔ {entry.slider_high}",
        "value_range": [spec.min_value, spec.max_value],
        "inverted": spec.inverted,
        "meaning": entry.meaning,
        "mechanism": entry.mechanism,
        "formula": entry.formula,
        "json_mapping": entry.json_mapping,
        "increase_effect": entry.increase_effect,
        "decrease_effect": entry.decrease_effect,
        "related_ui_keys": entry.related_ui,
        "hidden_context": entry.hidden_context,
        "tab_kpis": entry.tab_kpis,
        "expert_ui_note": "专家在可视化页看到的是本 label 与滑杆端点词，不是 JSON 路径。改参必须用 UI 键 set_ui_param。",
    }


def list_ui_param_guides() -> List[Dict[str, Any]]:
    return [get_ui_param_guide(spec.key) for spec in UI_PARAM_SPECS]


def format_guide_for_system_prompt(max_chars: int = 16000) -> str:
    lines = [
        f"## 界面 {len(UI_PARAM_SPECS)} 项参数（专家 UI 旋钮 ↔ AI 的 ui_key）",
        "",
        "权威文档：docs/界面可调参数.md",
        "重要：专家看到的是中文标签+滑杆；AI 必须用 ui_key 调 set_ui_param。",
        "每个 UI 键映射到若干底层 JSON 叶子（见 json_mapping）；由 ui_tunable.py 维护。",
        "",
    ]
    current_section = ""
    for spec in UI_PARAM_SPECS:
        g = UI_PARAM_GUIDE[spec.key]
        if g.section != current_section:
            current_section = g.section
            lines.append(f"### {g.mechanism}（{current_section}）")
            lines.append(SECTION_FORMULAS.get(current_section, ""))
            lines.append("")
        inv = " [inverted]" if spec.inverted else ""
        lines.append(
            f"- **{spec.key}**（{g.label}，{g.slider_low}↔{g.slider_high}{inv}，"
            f"范围 {spec.min_value}–{spec.max_value}）：{g.meaning} "
            f"↑{g.increase_effect} ↓{g.decrease_effect} "
            f"→ JSON: {g.json_mapping}"
        )
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（详见 explain_ui_param 工具）"
    return text


def enrich_param_specs(cfg: dict) -> List[Dict[str, Any]]:
    out = []
    for spec in UI_PARAM_SPECS:
        g = UI_PARAM_GUIDE[spec.key]
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "section": spec.section,
                "min": spec.min_value,
                "max": spec.max_value,
                "slider_low": spec.slider_low,
                "slider_high": spec.slider_high,
                "inverted": spec.inverted,
                "description": spec.description,
                "value": read_ui_param(cfg, spec.key),
                "meaning": g.meaning,
                "increase_effect": g.increase_effect,
                "decrease_effect": g.decrease_effect,
                "json_mapping": g.json_mapping,
            }
        )
    return out


def summarize_probe_impact(probe: Dict[str, Any]) -> Dict[str, Any]:
    ui_key = probe.get("ui_key", "")
    from modules.mechanism_config.ui_tunable import _resolve_ui_key
    ui_key_r = _resolve_ui_key(ui_key) if ui_key else ""
    guide = get_ui_param_guide(ui_key_r) if ui_key_r in UI_PARAM_GUIDE else {}
    before = probe.get("before") or {}
    after = probe.get("after") or {}
    section = probe.get("section", "")
    summary: Dict[str, Any] = {
        "ui_key": ui_key,
        "section": section,
        "guide": {
            "label": guide.get("label"),
            "meaning": guide.get("meaning"),
            "increase_effect": guide.get("increase_effect"),
            "decrease_effect": guide.get("decrease_effect"),
        },
        "kpi_changes": [],
    }
    if section == "health":
        bg = before.get("gauge") or {}
        ag = after.get("gauge") or {}
        for k in ("health_p50", "health_final"):
            if k in bg or k in ag:
                summary["kpi_changes"].append(
                    {"kpi": k, "before": bg.get(k), "after": ag.get(k), "delta": _delta(ag.get(k), bg.get(k))}
                )
    elif section == "relapse":
        bk = (before.get("kpis") or {}).get("relapse_probability_pct")
        ak = (after.get("kpis") or {}).get("relapse_probability_pct")
        summary["kpi_changes"].append(
            {"kpi": "relapse_probability_pct", "before": bk, "after": ak, "delta": _delta(ak, bk)}
        )
    elif section == "satisfaction":
        summary["kpi_changes"].append(
            {"kpi": "satisfaction_score", "before": before.get("score"), "after": after.get("score"),
             "delta": _delta(after.get("score"), before.get("score"))}
        )
    elif section.startswith("phase_") or section == "management":
        summary["kpi_changes"].append(
            {
                "kpi": "management_params",
                "before": [p.get("value") for p in (before.get("params") or [])],
                "after": [p.get("value") for p in (after.get("params") or [])],
            }
        )
    return summary


def _delta(after: Any, before: Any) -> Optional[float]:
    try:
        if after is None or before is None:
            return None
        return round(float(after) - float(before), 4)
    except (TypeError, ValueError):
        return None
