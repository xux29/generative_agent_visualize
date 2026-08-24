"""界面 22 项可调参数的语义、JSON 映射与模拟影响（供专家 UI 与 AI 编辑共用）。

AI 只能改 UI 键（set_ui_param）；底层 JSON 叶子路径是映射结果，不是专家看到的旋钮名。
权威文档：docs/mechanism/界面可调参数.md
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
        label="违规惩罚（非线性）",
        section="health",
        slider_low="轻",
        slider_high="重",
        meaning="未阻止违规时，健康分基础扣分力度（非线性随当前健康分缩放）。",
        mechanism="健康分演算",
        formula="penalty = min(penaltyStrength × √(health/100) × (1 + cumulativeSpeed × 连违规天数), dailyPenaltyCap)",
        json_mapping="缩放 simulation.health.nonlinear.discipline_params.{high,medium,low}.violation_penalty_range（自律高者惩罚更轻）",
        increase_effect="违规后健康分掉得更快，模拟更「严」。",
        decrease_effect="违规惩罚减轻，健康分更抗折腾。",
        related_ui=["cumulativeSpeed", "dailyPenaltyCap", "complianceBonus"],
        hidden_context="不是改单一 JSON 数字，而是按自律档位成比例缩放扣分区间。",
        tab_kpis="Tab2 健康分因子：violation 分量、health_p50、violation_days",
    ),
    "complianceBonus": UiParamGuideEntry(
        key="complianceBonus",
        label="遵从奖励",
        section="health",
        slider_low="少",
        slider_high="多",
        meaning="无违规时每日健康分恢复量，上限不超过初始健康分。",
        mechanism="健康分演算",
        formula="无违规日：health += complianceBonus（受自律档位倍率影响）",
        json_mapping="simulation.health.discipline_params.{high,medium,low}.compliance_bonus 同比例缩放",
        increase_effect="好天数更容易回血，长期健康分更高。",
        decrease_effect="遵从奖励变少，健康分恢复慢。",
        related_ui=["penaltyStrength", "plateauStubbornness"],
        tab_kpis="Tab2：compliance_bonus 分量",
    ),
    "cumulativeSpeed": UiParamGuideEntry(
        key="cumulativeSpeed",
        label="持续恶化加速下滑",
        section="health",
        slider_low="缓",
        slider_high="急",
        meaning="进入平台期后，连续违规导致健康分加速下滑的速度（分/天）。",
        mechanism="健康分演算",
        formula="连违规项：× (1 + cumulativeSpeed × consecutiveViolations)",
        json_mapping="simulation.health.nonlinear.discipline_params.*.cumulative_factor",
        increase_effect="连续犯错时健康分雪崩更快。",
        decrease_effect="连续违规的累积惩罚更温和。",
        related_ui=["penaltyStrength", "dailyPenaltyCap"],
        tab_kpis="Tab2：decline_acceleration 分量",
    ),
    "plateauStubbornness": UiParamGuideEntry(
        key="plateauStubbornness",
        label="平台期机制",
        section="health",
        slider_low="易破",
        slider_high="顽固",
        meaning="连续好天后进入「平台期」的长度（天）；平台期内自然恢复受限。",
        mechanism="健康分演算",
        formula="平台期持续 plateauStubbornness 天",
        json_mapping="simulation.health.nonlinear.discipline_params.*.plateau_duration（整数天）",
        increase_effect="好状态维持更久才进入平台，短期更稳。",
        decrease_effect="更快进入平台期，健康分更难继续升。",
        related_ui=["complianceBonus", "cumulativeSpeed"],
        tab_kpis="Tab2：natural_recovery / 平台相关分量",
    ),
    "dailyPenaltyCap": UiParamGuideEntry(
        key="dailyPenaltyCap",
        label="每日最大扣分限制",
        section="health",
        slider_low="低",
        slider_high="高",
        meaning="单日健康分扣分上限，防止一天内崩盘。",
        mechanism="健康分演算",
        formula="penalty  capped by dailyPenaltyCap",
        json_mapping="simulation.health.nonlinear.max_penalty（存为负数绝对值）",
        increase_effect="允许单日扣更多分，极端日更惨。",
        decrease_effect="单日扣分有更低天花板，抗单日冲击。",
        related_ui=["penaltyStrength", "cumulativeSpeed"],
        tab_kpis="Tab2：cap_hits、violation 分量",
    ),
    "noiseSigma": UiParamGuideEntry(
        key="noiseSigma",
        label="日常随机波动",
        section="health",
        slider_low="小",
        slider_high="大",
        meaning="每日健康分的随机扰动幅度，模拟生活噪声。",
        mechanism="健康分演算",
        formula="daily_noise ~ N(0, noiseSigma)",
        json_mapping="simulation.health.nonlinear.discipline_params.*.noise_sigma",
        increase_effect="健康分曲线更抖，结果更不确定。",
        decrease_effect="曲线更平滑、可预测。",
        related_ui=[],
        tab_kpis="Tab2：daily_noise 分量",
    ),
    "baseRelapseProb": UiParamGuideEntry(
        key="baseRelapseProb",
        label="基础概率",
        section="relapse",
        slider_low="低",
        slider_high="高",
        meaning="放松管控后被管者「又干坏事」的基准概率（乘算因子之前）。",
        mechanism="复发概率",
        formula="prob = baseRelapseProb × 自律修正 × 成瘾修正 × 放松时间修正 × 习惯保护 × (1 + 复发倾向修正)",
        json_mapping="simulation.relapse.base_prob（1:1 直写）",
        increase_effect="放松后更容易复发违规。",
        decrease_effect="放松后更不容易复发。",
        related_ui=["disciplineCorrection", "relaxTimeSensitivity", "habitProtection", "relapseSwing"],
        hidden_context="主体 simulation.subject 的 self_discipline / addiction_level 会乘在修正表里，但 UI 不能改 subject。",
        tab_kpis="Tab3：relapse_probability_pct",
    ),
    "disciplineCorrection": UiParamGuideEntry(
        key="disciplineCorrection",
        label="自律修正",
        section="relapse",
        slider_low="放大",
        slider_high="缩小",
        meaning="整体缩放「自律等级 → 复发概率」修正表；高自律者复发应更低。",
        mechanism="复发概率",
        formula="× discipline_mod[self_discipline]",
        json_mapping="整体缩放 simulation.relapse.discipline_mod.{very_low…very_high}",
        increase_effect="自律对复发的保护/放大效果更强。",
        decrease_effect="自律差异对复发影响变弱。",
        related_ui=["baseRelapseProb", "addictionCorrection"],
        hidden_context="表里 very_low…very_high 是内置档位，UI 键只调整体倍率。",
        tab_kpis="Tab3：disciplineCorrection 因子",
    ),
    "addictionCorrection": UiParamGuideEntry(
        key="addictionCorrection",
        label="成瘾修正",
        section="relapse",
        slider_low="弱",
        slider_high="强",
        meaning="整体缩放「成瘾程度 → 复发概率」修正表。",
        mechanism="复发概率",
        formula="× addiction_mod[addiction_level]",
        json_mapping="整体缩放 simulation.relapse.addiction_mod.{none…severe}",
        increase_effect="成瘾对复发的放大更明显。",
        decrease_effect="成瘾差异影响减弱。",
        related_ui=["baseRelapseProb", "disciplineCorrection"],
        tab_kpis="Tab3：addictionCorrection 因子",
    ),
    "relaxTimeSensitivity": UiParamGuideEntry(
        key="relaxTimeSensitivity",
        label="放松时间",
        section="relapse",
        slider_low="迟钝",
        slider_high="敏锐",
        meaning="管控放松越久，复发概率上升的速度。",
        mechanism="复发概率",
        formula="time_mod = 1 + (days_relaxed / days_divisor) × per_unit；UI 缩放 per_unit",
        json_mapping="simulation.relapse.time_mod.per_unit（相对基准 0.15 缩放）",
        increase_effect="放松几天后复发概率涨得更快。",
        decrease_effect="放松后复发概率上升更慢。",
        related_ui=["baseRelapseProb", "interventionTendency", "healthSafeThreshold"],
        tab_kpis="Tab3：relaxTimeSensitivity 因子",
    ),
    "habitProtection": UiParamGuideEntry(
        key="habitProtection",
        label="习惯保护",
        section="relapse",
        slider_low="弱",
        slider_high="强",
        meaning="连续无违规天数越长，复发概率被压低越多。",
        mechanism="复发概率",
        formula="habit_mod = max(floor, 1 - streak × streak_factor)",
        json_mapping="simulation.relapse.habit_mod.streak_factor",
        increase_effect="好习惯对复发的抑制更强。",
        decrease_effect="习惯保护弱，复发更易发生。",
        related_ui=["baseRelapseProb", "relapseSwing"],
        tab_kpis="Tab3：habitProtection 因子",
    ),
    "relapseSwing": UiParamGuideEntry(
        key="relapseSwing",
        label="复发倾向",
        section="relapse",
        slider_low="小",
        slider_high="大",
        meaning="被管者内在「复发倾向」对概率的加性摆幅。",
        mechanism="复发概率",
        formula="+ relapse_tendency × tendency_weight",
        json_mapping="simulation.relapse.tendency_mod.tendency_weight",
        increase_effect="倾向性个体更容易在放松时复发。",
        decrease_effect="倾向性影响减弱。",
        related_ui=["baseRelapseProb", "habitProtection"],
        tab_kpis="Tab3：relapseSwing 因子",
    ),
    "baseSatisfaction": UiParamGuideEntry(
        key="baseSatisfaction",
        label="基础满意度",
        section="satisfaction",
        slider_low="低",
        slider_high="高",
        meaning="被管者对管理方式的满意度基线（与当日干预无关部分）。",
        mechanism="满意度",
        formula="satisfaction = baseSatisfaction - 强度惩罚 - 频率惩罚 - 过度干预惩罚 + 替代奖励 + 时机奖励 + 情绪修正",
        json_mapping="simulation.satisfaction.base_score",
        increase_effect="整体满意度更高，更耐受干预。",
        decrease_effect="整体满意度偏低，更易不满。",
        related_ui=["interventionSensitivity", "frequencyPenalty", "overInterventionPenalty"],
        tab_kpis="Tab4：baseSatisfaction 柱",
    ),
    "interventionSensitivity": UiParamGuideEntry(
        key="interventionSensitivity",
        label="强度惩罚",
        section="satisfaction",
        slider_low="轻",
        slider_high="重",
        meaning="干预等级越高，满意度扣分越多。",
        mechanism="满意度",
        formula="强度惩罚 ∝ intervention_level × sensitivity",
        json_mapping="simulation.satisfaction.intervention_level_weights + discipline_phase_modifiers.*.intervention_sensitivity",
        increase_effect="高强度干预更招反感。",
        decrease_effect="高强度干预对满意度伤害小。",
        related_ui=["interventionIntensity", "frequencyPenalty", "baseSatisfaction"],
        tab_kpis="Tab4：interventionSensitivity 柱",
    ),
    "frequencyPenalty": UiParamGuideEntry(
        key="frequencyPenalty",
        label="频率惩罚",
        section="satisfaction",
        slider_low="轻",
        slider_high="重",
        meaning="同一天干预次数越多，满意度额外扣分越多。",
        mechanism="满意度",
        formula="频率惩罚 ∝ 干预次数 × frequencyPenalty",
        json_mapping="simulation.satisfaction.frequency_penalty.per_intervention",
        increase_effect="频繁干预快速拉低满意度。",
        decrease_effect="多次干预对满意度影响小。",
        related_ui=["interventionTendency", "interventionSensitivity"],
        tab_kpis="Tab4：frequencyPenalty 柱",
    ),
    "overInterventionPenalty": UiParamGuideEntry(
        key="overInterventionPenalty",
        label="过度干预惩罚",
        section="satisfaction",
        slider_low="轻",
        slider_high="重",
        meaning="健康分仍高于警戒线却严管时触发的满意度惩罚。",
        mechanism="满意度",
        formula="健康 > healthSafeThreshold 且干预过重 → 扣分",
        json_mapping="simulation.satisfaction.overintervention.base_penalty",
        increase_effect="「健康挺好还管太紧」时更不满。",
        decrease_effect="过管惩罚轻，满意度更稳。",
        related_ui=["healthSafeThreshold", "interventionIntensity", "interventionTendency"],
        tab_kpis="Tab4：overInterventionPenalty 柱",
    ),
    "alternativeCompensation": UiParamGuideEntry(
        key="alternativeCompensation",
        label="替代奖励",
        section="satisfaction",
        slider_low="少",
        slider_high="多",
        meaning="提供替代选项/自主空间时的满意度补偿上限。",
        mechanism="满意度",
        formula="+ min(autonomy_gain, alternativeCompensation)",
        json_mapping="simulation.satisfaction.autonomy_modifier_cap",
        increase_effect="给替代方案时满意度加更多。",
        decrease_effect="替代奖励弱，自主感补偿少。",
        related_ui=["baseSatisfaction", "timelinessEffect"],
        tab_kpis="Tab4：alternativeCompensation 柱",
    ),
    "timelinessEffect": UiParamGuideEntry(
        key="timelinessEffect",
        label="时机奖励",
        section="satisfaction",
        slider_low="弱",
        slider_high="强",
        meaning="干预时机合理（reasonable/preventive）时的满意度加分幅度。",
        mechanism="满意度",
        formula="+ reasonability_modifier × timelinessEffect",
        json_mapping="simulation.satisfaction.intervention_reasonability.reasonable",
        increase_effect="及时干预更增满意度。",
        decrease_effect="时机奖励弱。",
        related_ui=["baseSatisfaction", "interventionTendency"],
        tab_kpis="Tab4：timelinessEffect 柱",
    ),
    "interventionIntensity": UiParamGuideEntry(
        key="interventionIntensity",
        label="干预强度",
        section="management",
        slider_low="温和",
        slider_high="强硬",
        meaning="管理者出手力度（松紧度），直接影响干预等级分布。",
        mechanism="管理机制",
        formula="tightness ≈ interventionIntensity（关系阶段 modifier）",
        json_mapping="management.relationship_phases.adjustment.intervention_modifier",
        increase_effect="干预更硬，违规更少但满意度/复发风险需权衡。",
        decrease_effect="干预更温和，满意度可能更好但约束弱。",
        related_ui=["interventionTendency", "healthSafeThreshold", "interventionSensitivity"],
        tab_kpis="Tab5 管理：干预强度",
    ),
    "interventionTendency": UiParamGuideEntry(
        key="interventionTendency",
        label="干预倾向",
        section="management",
        slider_low="保守",
        slider_high="激进",
        meaning="多快从观察(L0)升级到实际干预；越激进 L0 越少。",
        mechanism="管理机制",
        formula="early_intervention_base 越低 → 倾向越高",
        json_mapping="management.manager_learning.early_intervention_base（反向映射）",
        increase_effect="更早、更频繁干预，违规可能降但满意度/过管风险升。",
        decrease_effect="更常观察等待，干预次数降。",
        related_ui=["interventionIntensity", "healthSafeThreshold", "frequencyPenalty"],
        tab_kpis="Tab5：干预倾向 / early_intervention_base",
    ),
    "healthSafeThreshold": UiParamGuideEntry(
        key="healthSafeThreshold",
        label="健康分警戒线",
        section="management",
        slider_low="低",
        slider_high="高",
        meaning="健康分高于此值时，管理者可放松干预；也参与过管判定。",
        mechanism="管理机制",
        formula="health > threshold → 允许 relax；与 overIntervention 联动",
        json_mapping="management.over_intervention.health_safe_threshold（UI 为 0–100，JSON 存 0–10  scale）",
        increase_effect="更高才放松，整体干预更频。",
        decrease_effect="更容易进入放松，干预更少。",
        related_ui=["overInterventionPenalty", "interventionTendency", "interventionIntensity"],
        hidden_context="UI 显示 50–90 分制；JSON 里可能是 0–10，勿手改 JSON 须用 UI 键。",
        tab_kpis="Tab5：健康分警戒线",
    ),
    "emotionWarning": UiParamGuideEntry(
        key="emotionWarning",
        label="情绪警戒线",
        section="management",
        slider_low="低",
        slider_high="高",
        meaning="情绪低于此值时触发满意度保护/预警逻辑。",
        mechanism="管理机制",
        formula="mood < emotionWarning → 保护机制",
        json_mapping="management.over_intervention.emotion_warning_threshold",
        increase_effect="更容易判定情绪差，保护触发更勤。",
        decrease_effect="只有情绪很差才触发保护。",
        related_ui=["baseSatisfaction", "overInterventionPenalty"],
        tab_kpis="Tab5：情绪警戒线",
    ),
}

SECTION_FORMULAS = {
    "health": "健康分：penalty = min(penaltyStrength × √(health/100) × (1 + cumulativeSpeed × 连违规), dailyPenaltyCap)；无违规 +complianceBonus",
    "relapse": "复发：prob = baseRelapseProb × 自律修正 × 成瘾修正 × 放松时间 × 习惯保护 × (1 + 倾向修正)",
    "satisfaction": "满意度：base - 强度 - 频率 - 过管 + 替代 + 时机 + 情绪修正",
    "management": "管理：interventionIntensity 定松紧；interventionTendency 定多快出手；healthSafeThreshold / emotionWarning 定触发阈值",
}


def get_ui_param_guide(ui_key: str) -> Dict[str, Any]:
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


def format_guide_for_system_prompt(max_chars: int = 12000) -> str:
    """Condensed catalog injected into editor system prompt."""
    lines = [
        "## 界面 22 项参数（专家 UI 旋钮 ↔ AI 的 ui_key）",
        "",
        "重要：专家看到的是中文标签+滑杆；AI 必须用 ui_key 调 set_ui_param。",
        "不要直接改 simulation.subject.* / 潮汐 / 行为表等内置 JSON；它们不在界面暴露。",
        "每个 UI 键会映射到若干底层 JSON 叶子（见 json_mapping）；映射由 ui_tunable.py 维护。",
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
        lines.append(
            f"- **{spec.key}**（{g.label}，{g.slider_low}↔{g.slider_high}，"
            f"范围 {spec.min_value}–{spec.max_value}）：{g.meaning} "
            f"↑{g.increase_effect} ↓{g.decrease_effect} "
            f"→ JSON: {g.json_mapping}"
        )
        if g.related_ui:
            lines.append(f"  关联 UI 键: {', '.join(g.related_ui)}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（详见 explain_ui_param 工具）"
    return text


def enrich_param_specs(cfg: dict) -> List[Dict[str, Any]]:
    """list_ui_params 返回：当前值 + 语义摘要。"""
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
                "value": read_ui_param(cfg, spec.key),
                "meaning": g.meaning,
                "increase_effect": g.increase_effect,
                "decrease_effect": g.decrease_effect,
                "json_mapping": g.json_mapping,
            }
        )
    return out


def summarize_probe_impact(probe: Dict[str, Any]) -> Dict[str, Any]:
    """从 probe_ui_param_delta 结果提取 AI 可读的影响摘要。"""
    ui_key = probe.get("ui_key", "")
    guide = get_ui_param_guide(ui_key) if ui_key in UI_PARAM_GUIDE else {}
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
        bs = before.get("score")
        as_ = after.get("score")
        summary["kpi_changes"].append(
            {"kpi": "satisfaction_score", "before": bs, "after": as_, "delta": _delta(as_, bs)}
        )
    elif section == "management":
        summary["kpi_changes"].append(
            {
                "kpi": "management_params",
                "before": [p.get("value") for p in (before.get("params") or [])],
                "after": [p.get("value") for p in (after.get("params") or [])],
            }
        )

    bf = before.get("factors") or before.get("bars") or []
    af = after.get("factors") or after.get("bars") or []
    factor_changes = []
    for item in af:
        key = item.get("ui_key") or item.get("key") or item.get("label")
        prev = next((x for x in bf if (x.get("ui_key") or x.get("key") or x.get("label")) == key), None)
        if prev and "current_impact" in item:
            factor_changes.append(
                {
                    "factor": key,
                    "impact_before": prev.get("current_impact"),
                    "impact_after": item.get("current_impact"),
                }
            )
        elif prev and "value" in item:
            factor_changes.append(
                {"factor": key, "before": prev.get("value"), "after": item.get("value")}
            )
    if factor_changes:
        summary["factor_changes"] = factor_changes[:8]

    return summary


def _delta(after: Any, before: Any) -> Optional[float]:
    try:
        if after is None or before is None:
            return None
        return round(float(after) - float(before), 4)
    except (TypeError, ValueError):
        return None
