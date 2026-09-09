"""Traceable daily curve values from serial town logs.

The empirical intent rate is NOT the relapse probability or a calibrated
probability predicted by the LLM. Preserve numerator/denominator for review.
"""


def observed_metrics(log, config, managed=True):
    events = [e for e in log.get("events", []) if e.get("type") == "intention"
              and e.get("execution_source") != "forced_02_00"]
    attempts = sum(bool(e.get("is_violation")) for e in events)
    p = config.get("ui_params", {})
    h, s = log["health_score"], log["emotion_score"]
    inputs = {"health": h, "satisfaction": s,
              "health_threshold": p.get("healthSafeThreshold", 75),
              "satisfaction_threshold": p.get("SatisfactionWarning", 4.5),
              "intensity": p.get("interventionIntensity", 1),
              "tendency": p.get("interventionTendency", .5)}
    gh = max(0, inputs["health_threshold"] - h) / 100
    gs = max(0, inputs["satisfaction_threshold"] - s) / 10
    raw = (1 + 2 * gh + .6 * inputs["intensity"]) * (.5 + .8 * inputs["tendency"]) * (1 - .5 * min(1, gs))
    return {"health": h, "satisfaction": s, "management_enabled": managed,
            "violation_intent_rate": attempts / len(events) if events else None,
            "violation_intent_numerator": attempts, "observed_slots": len(events),
            "violation_rate_definition": "empirical_intents_per_observed_slot_not_predicted_probability",
            "intervention_mechanism": min(100, max(0, raw / 3 * 100)) if managed else 0,
            "intervention_mechanism_formula": "intervention-curve-formula.md:parametric-v1",
            "intervention_mechanism_inputs": inputs,
            "actual_intervention_count": sum(i.get("level", 0) > 0 for i in log.get("interventions", []))}
