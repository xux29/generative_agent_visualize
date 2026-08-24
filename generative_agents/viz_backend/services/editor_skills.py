"""Load Cursor Skills as system prompts for the visualization editor agent."""

from __future__ import annotations

from pathlib import Path

from modules.mechanism_config.ui_param_guide import format_guide_for_system_prompt

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_CONFIG = REPO_ROOT / ".cursor" / "skills" / "edit-mechanism-config" / "SKILL.md"
SKILL_CODE = REPO_ROOT / ".cursor" / "skills" / "edit-health-mechanisms" / "SKILL.md"

ROUTER_PREAMBLE = """你是健康仿真「机制编辑助手」，运行在可视化平台对话里。

你必须同时遵守下面两份 Skill。用户用自然语言描述想改的模拟行为。

## UI 参数 vs 底层 JSON（必读）

专家在可视化页看到的是 **中文标签 + 滑杆端点词**（如「基础概率 低↔高」）。
你只能通过 **ui_key**（如 `baseRelapseProb`）调用 `set_ui_param` 改参。
底层 `active.json` 里的叶子路径（如 `simulation.relapse.base_prob`）是 **映射结果**，
一个 UI 键常同步改多个 JSON 字段（如按自律档位缩放）。**不要**以为改一个 JSON 叶子就等于拧了一个滑杆。

改参流程：
1. 不确定时先 `explain_ui_param(ui_key)` 或 `preview_ui_param(ui_key, value)`
2. `propose` 开草稿
3. `set_ui_param(proposal_id, ui_key, value)` — 优先于 edit_config
4. validate → promote；**不要**自行 approve

路由：
- 只拧界面 22 个可调旋钮 → set_ui_param / preview_ui_param
- 改公式/状态机/新机制 → edit_code（机制 Skill）；**不要**为拧旋钮去改 Python
- 涉及斯坦福基座、日循环编排、前端、密钥 → 拒绝

安全流程（默认不碰 live）：
1. propose 开草稿
2. edit_config 和/或 edit_code（仅白名单）
3. validate
4. promote 冻结为 model
5. **不要**自行 approve。告诉用户在界面点「批准落地」，或明确说等待批准。

每次回复用中文说明：改了哪个 **UI 键/中文标签**、模拟上会怎样、proposal/model id、是否已 validate、下一步。
"""


def load_skill_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return f"（未找到 Skill 文件: {path}）"


def build_system_prompt() -> str:
    config_skill = load_skill_text(SKILL_CONFIG)
    code_skill = load_skill_text(SKILL_CODE)
    param_catalog = format_guide_for_system_prompt()
    return (
        ROUTER_PREAMBLE
        + "\n\n===== 界面 22 项参数语义与映射（专家 UI ↔ ui_key）=====\n"
        + param_catalog
        + "\n\n===== SKILL: edit-mechanism-config =====\n"
        + config_skill
        + "\n\n===== SKILL: edit-health-mechanisms =====\n"
        + code_skill
    )
