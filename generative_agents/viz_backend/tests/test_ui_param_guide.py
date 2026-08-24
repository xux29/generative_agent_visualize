"""Tests for UI parameter guide catalog."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from modules.mechanism_config.ui_param_guide import (
    UI_PARAM_GUIDE,
    enrich_param_specs,
    format_guide_for_system_prompt,
    get_ui_param_guide,
)
from modules.mechanism_config.ui_tunable import UI_PARAM_SPECS
from modules.mechanism_config import load_mechanism_config


def test_guide_covers_all_ui_keys():
    assert len(UI_PARAM_GUIDE) == 22
    for spec in UI_PARAM_SPECS:
        g = get_ui_param_guide(spec.key)
        assert g["label"]
        assert g["json_mapping"]
        assert g["increase_effect"]


def test_enrich_param_specs():
    cfg = load_mechanism_config()
    specs = enrich_param_specs(cfg)
    assert len(specs) == 22
    assert specs[0]["meaning"]
    assert "value" in specs[0]


def test_system_prompt_includes_mapping():
    text = format_guide_for_system_prompt()
    assert "baseRelapseProb" in text
    assert "set_ui_param" in format_guide_for_system_prompt() or "ui_key" in text
    assert "simulation.relapse.base_prob" in text or "JSON" in text


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        get_ui_param_guide("notARealKey")
