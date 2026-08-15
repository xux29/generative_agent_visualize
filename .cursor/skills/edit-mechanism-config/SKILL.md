---
name: edit-mechanism-config
description: >-
  Safely edit health simulation mechanism parameter JSON (active.json / proposals)
  within allowed schema paths only. Use when the user asks to tune weights,
  thresholds, probabilities, relapse/mood/satisfaction/health parameters, or
  change mechanism config via chat, CLI, or visualization—not when changing
  Python formulas or adding new mechanisms.
---

# 编辑机制参数 JSON

在 `generative_agents/` 工作目录下操作。JSON 只是**配置层**，不是机制本体。

## 硬性范围（允许）

仅可改这些路径下的**已有或 schema 允许的参数字段**：

- `generative_agents/data/mechanism/active.json`
- `generative_agents/data/mechanism/defaults/v0_baseline.json`（一般不要直接改；改 active 或 proposal）
- `generative_agents/data/mechanism/versions/*.json`（通过 CLI save，不要手改历史快照）
- Proposal 配置：`data/mechanism/proposals/<id>/config.json`（推荐 AI 先改这里）

配置命名空间仅限：

```text
meta.*
simulation.subject | health | relapse | mood | compliance
simulation.behavior_scores | habit | satisfaction | composite
management.intervention | tidal | relationship_phases
management.trust_capital | habit_consolidation
management.manager_learning | over_intervention | reflection
```

## 硬性禁止（越权即停）

- 修改 `modules/**`、`start*.py`、`frontend/**`、`tools/**`（本 skill 不做代码改动）
- 修改 `data/prompts/**`（非 mechanism prompts）或任意非 `data/mechanism/` 配置
- 写入已排除字段（schema 会剥离且无效）：
  - `natural_recovery` / `natural_recovery_range`
  - `blocked_violation_factor`
  - `MAX_EFFECTIVE_VIOLATIONS` / `max_effective_violations`
- `self_discipline` 只能是 `low` | `medium` | `high`
- 把「新增公式/状态/规则」伪装成只改 JSON——那是机制问题，改用 skill `edit-health-mechanisms`

## 何时用参数 vs 机制

| 用户意图 | 做法 |
|----------|------|
| 概率/权重/阈值偏大偏小 | **本 skill：改 JSON** |
| 缺变量、缺公式分支、要新状态机 | 切换到 `edit-health-mechanisms` |
| 不确定 | 先查 `data/mechanism/registry.json` 与 `get_path(...)` 消费点；能点分路径表示则改 JSON |

## 推荐流程（优先 proposal，勿直接污染 live）

在 `generative_agents/`：

```bash
# 1) 开草稿（不改 live）
python tools/model_cli.py propose --name <短名> --note "<原因>" --by ai

# 2) 改单个点分路径
python tools/model_cli.py edit-config --proposal <P> --path simulation.relapse.base_prob --value 0.10

# 3) 校验
python tools/model_cli.py validate --proposal <P>

# 4) 冻结为 model（仍不进 live）
python tools/model_cli.py promote --proposal <P>

# 5) 仅当用户明确批准时才落地
python tools/model_cli.py approve --model <M> --config-only
```

若用户明确要求「直接改 active」且范围很小：

1. 先 `python tools/mechanism_cli.py save --name before_<名> --note "AI 改参前"`
2. 编辑 `data/mechanism/active.json`（只动目标字段）
3. `python tools/mechanism_cli.py show` 核对
4. 告知如何 `rollback`

## 直接改 JSON 时的规则

1. 先读 `active.json` / `defaults/v0_baseline.json` 确认字段已存在。
2. **只改需要的叶子字段**；不要整文件重排无关键、不要美化整棵树。
3. `value` 用合法 JSON 标量/对象（CLI `--value` 会尝试 `json.loads`）。
4. 改完说明：改了哪些 `path`、旧值→新值、是否已 approve。

## 决策树

```text
用户要调模拟表现
  ├─ 只是拧旋钮（已有字段）→ 本 skill
  ├─ 需要新旋钮但公式里还没有 → edit-health-mechanisms（先加代码再暴露 JSON）
  └─ 要动日循环/Agent.think/地图 → 拒绝，超出健康机制配置范围
```

## 参考

- 字段说明：`docs/机制参数JSON使用指南.md`
- 架构边界：`docs/健康机制双层架构与AI编辑.md`
- 注册表：`data/mechanism/registry.json`
