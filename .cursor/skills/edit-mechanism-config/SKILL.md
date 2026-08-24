---
name: edit-mechanism-config
description: >-
  Safely edit health simulation mechanism parameter JSON (active.json / proposals)
  within the 22 UI-exposed tunable parameters only. Use when the user asks to tune
  weights, thresholds, probabilities via chat, CLI, or visualization—not when changing
  Python formulas or adding new mechanisms.
---

# 编辑机制参数 JSON（仅界面 22 项）

在 `generative_agents/` 工作目录下操作。JSON 只是**配置层**，不是机制本体。

**唯一权威清单**：[`docs/mechanism/界面可调参数.md`](../../docs/mechanism/界面可调参数.md)  
代码映射：[`modules/mechanism_config/ui_tunable.py`](../../generative_agents/modules/mechanism_config/ui_tunable.py)

## 硬性范围（允许）

仅可改下列 **22 个 UI 键**（通过 `set_ui_param` 或映射后的 JSON 叶子路径）：

| 分区 | UI 键 |
|------|--------|
| 健康分 | `penaltyStrength`, `complianceBonus`, `cumulativeSpeed`, `plateauStubbornness`, `dailyPenaltyCap`, `noiseSigma` |
| 复发 | `baseRelapseProb`, `disciplineCorrection`, `addictionCorrection`, `relaxTimeSensitivity`, `habitProtection`, `relapseSwing` |
| 满意度 | `baseSatisfaction`, `interventionSensitivity`, `frequencyPenalty`, `overInterventionPenalty`, `alternativeCompensation`, `timelinessEffect` |
| 管理 | `interventionIntensity`, `interventionTendency`, `healthSafeThreshold`, `emotionWarning` |

写入位置：

- `generative_agents/data/mechanism/active.json`（仅用户明确要求直接改 live）
- Proposal：`data/mechanism/proposals/<id>/config.json`（**推荐**）

`edit_config` 的 `path` 必须在 `UI_TUNABLE_JSON_PATHS` 内；**优先** `set_ui_param(proposal_id, ui_key, value)`。

## 硬性禁止（越权即停）

- 修改 `modules/**`、前端、仿真入口（本 skill 不做代码改动）
- 修改 **不在上述 22 项** 的任何 JSON 字段（如 `simulation.subject.*`、`management.tidal.*`、`behavior_scores` 等）——这些已还原为机制内置，不在界面暴露
- 写入已排除字段：`natural_recovery`、`natural_recovery_range`、`blocked_violation_factor`、`MAX_EFFECTIVE_VIOLATIONS`
- 把「新增公式/状态/规则」伪装成只改 JSON → 改用 skill `edit-health-mechanisms`

## 何时用参数 vs 机制

| 用户意图 | 做法 |
|----------|------|
| 概率/权重/阈值偏大偏小，且落在 22 项内 | **本 skill：`set_ui_param`** |
| 要改 22 项以外的行为，或改公式结构 | 切换到 `edit-health-mechanisms` 或拒绝 |
| 不确定 | 先 `explain_ui_param` / `list_ui_params`；键不在表中则不可仅改 JSON |

## 推荐流程（优先 proposal，勿直接污染 live）

```bash
python tools/model_cli.py propose --name <短名> --note "<原因>" --by ai
# 可视化 / AI：set_ui_param 或 edit-config（白名单路径）
python tools/model_cli.py validate --proposal <P>
python tools/model_cli.py promote --proposal <P>
# 仅当用户明确批准：
python tools/model_cli.py approve --model <M> --config-only
```

## 参考

- 界面清单：[`docs/mechanism/界面可调参数.md`](../../docs/mechanism/界面可调参数.md)
- 架构边界：[`docs/健康机制双层架构与AI编辑.md`](../../docs/健康机制双层架构与AI编辑.md)
