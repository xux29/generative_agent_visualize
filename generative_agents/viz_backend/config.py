"""Paths and defaults for the visualization backend."""

from __future__ import annotations

from pathlib import Path

GA_ROOT = Path(__file__).resolve().parents[1]
RESULTS_HEALTH = GA_ROOT / "results" / "health"
SWEEP_RESULTS = GA_ROOT.parent / "docs" / "mechanism" / "param_impact" / "sweep_results.json"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5002

TAB_SECTIONS = (
    {"id": "health", "tab": 2, "title": "健康分因子分解", "mechanism": "健康分演算"},
    {"id": "relapse", "tab": 3, "title": "复发因子分解", "mechanism": "复发概率机制"},
    {"id": "satisfaction", "tab": 4, "title": "满意度因子构成", "mechanism": "满意度计算规则"},
    {"id": "management", "tab": 5, "title": "管理机制", "mechanism": "管理机制"},
)
