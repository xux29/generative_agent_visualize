# 健康机制双层架构与 AI 编辑说明

本文档说明在 Stanford 小镇基座之上，对**健康干预仿真**所做的机制收拢、参数外置、AI 双编辑与轻量可视化改动（Phase 1–4）。

---

## 1. 设计目标

老师担心：若把 JSON 当成「整个模拟机制」，AI 会被 schema 限死，无法增改公式/状态机。

因此采用**双层架构**：

| 层 | 含义 | 存放位置 | 谁改 |
|----|------|----------|------|
| **Mechanism Code** | 机制本体（公式、状态、规则） | `modules/health_mechanisms/` + `data/mechanism/prompts/` | AI / 开发者 |
| **Mechanism Config** | 可调参数（权重、阈值、开关） | `data/mechanism/*.json` | 专家 / AI / CLI |

> JSON 是机制的**配置接口**，不是机制本身。

---

## 2. 目录与职责

```text
generative_agents/
├── modules/health_mechanisms/     # 机制代码统一入口（AI 可编辑）
│   ├── agent_mixin.py             # 意图 / 干预 / 复发 / 习惯
│   ├── scoring/                   # 健康分 / 情绪 / 满意度
│   ├── management/strategy.py     # 管理策略状态机
│   ├── asymmetric_game.py
│   ├── scenario.py
│   ├── prompts.py                 # HealthPromptsMixin
│   ├── registry.py                # 机制注册表 API
│   ├── model_version.py           # 统一 Model Version
│   ├── ai_edit.py                 # AI 双编辑 API
│   └── sandbox.py                 # 校验 / 短仿真沙箱
├── modules/mechanism_config/      # 参数加载 / VersionStore（参数层）
├── data/mechanism/
│   ├── active.json                # 当前生效参数
│   ├── defaults/v0_baseline.json
│   ├── registry.json              # 机制 → 实现 / 配置路径
│   ├── prompts/health_*.txt       # 健康 prompt 模板（主路径）
│   ├── versions/                  # 参数 JSON 版本（本地）
│   ├── models/                    # Model 快照（本地，不入库）
│   ├── proposals/                 # AI 草稿（本地，不入库）
│   └── sandboxes/                 # 沙箱工作区（本地，不入库）
├── tools/mechanism_cli.py         # 参数版本 CLI
├── tools/model_cli.py             # Model / AI 编辑 CLI
├── .cursor/skills/                # 对话约束 Skill（改参 / 改机制）
│   ├── edit-mechanism-config/
│   └── edit-health-mechanisms/
└── visualize_health.py / replay_health.py   # 原有结果可视化（未改机制面板）
```

旧路径（如 `modules/agent_health.py`）保留 **re-export**，兼容原有 import。

斯坦福基座（`start.py`、`agent.think`、memory、maze 寻路等）**未迁入**健康机制包。

---

## 3. 分阶段做了什么

### Phase 1 — 机制代码收拢

- 将健康相关实现迁入 `modules/health_mechanisms/`
- 旧模块改为 thin re-export
- 主入口 `start_health_simulation.py`、`agent.py` 改用新路径
- **不改公式语义**

### Phase 2 — 注册表 + Prompt 归位

- `data/mechanism/registry.json` + `registry.py`
- `health_*.txt` 主路径改为 `data/mechanism/prompts/`
- `Scratch` 继承 `HealthPromptsMixin`，从新目录加载模板

### Phase 3 — AI 双编辑 + Model Version + Sandbox

```text
propose（草稿，不改 live）
  → edit-config / edit-code（白名单）
  → validate / sandbox
  → promote → 不可变 model
  → approve（专家批准才写入 live）
  → rollback
```

**AI 可编辑白名单：**

- `modules/health_mechanisms/**`
- `data/mechanism/prompts/**`

禁止直接改基座（如 `modules/agent.py` 认知核）。

常用命令（在 `generative_agents/` 下）：

```bash
python tools/model_cli.py propose --name ai_fix --note "..."
python tools/model_cli.py edit-config --proposal P --path simulation.relapse.base_prob --value 0.10
python tools/model_cli.py edit-code --proposal P --file modules/health_mechanisms/... --from-file x.py
python tools/model_cli.py validate --proposal P
python tools/model_cli.py promote --proposal P
python tools/model_cli.py approve --model M
python tools/model_cli.py rollback --model M_prev
```

参数-only 版本仍可用：`python tools/mechanism_cli.py ...`

### Phase 4 — 可视化说明

原计划做过轻量「机制调整面板」，后已**删除**，继续使用既有：

- `replay_health.py`（地图回放）
- `visualize_health.py`（结果图表）

观察参数与版本请用 CLI / 直接读 `data/mechanism/`；架构对比见  
[健康机制改动前后对比.md](./健康机制改动前后对比.md)。

---

## 4. Cursor Agent Skills（对话式改参 / 改机制）

后续在可视化界面与 AI 对话时，由两个**项目级 Skill**约束 AI 的可写范围，避免越权改到斯坦福基座或编排代码。

| Skill | 路径 | 用途 |
|-------|------|------|
| `edit-mechanism-config` | [`.cursor/skills/edit-mechanism-config/SKILL.md`](../.cursor/skills/edit-mechanism-config/SKILL.md) | **只改参数 JSON**（权重、阈值、概率等） |
| `edit-health-mechanisms` | [`.cursor/skills/edit-health-mechanisms/SKILL.md`](../.cursor/skills/edit-health-mechanisms/SKILL.md) | **增删改机制代码**（公式、状态机、health prompts） |

### 4.1 如何选用

| 用户说法（示例） | 应触发的 Skill |
|------------------|----------------|
| 「把复发基线调低」「权重改一下」 | `edit-mechanism-config` |
| 「加一个环境压力因素」「改健康分公式」 | `edit-health-mechanisms` |
| 不确定 | 先查 `registry.json`：已有点分路径 → 改 JSON；否则先改代码再暴露参数 |

### 4.2 `edit-mechanism-config`（改参数）

**允许：**

- `data/mechanism/active.json`、proposal 的 `config.json`
- 命名空间：`meta` / `simulation.*` / `management.*`（schema 已有分区）

**禁止：**

- 改任何 `modules/**`、前端、仿真入口
- 写入已排除字段：`natural_recovery`、`natural_recovery_range`、`blocked_violation_factor`、`MAX_EFFECTIVE_VIOLATIONS`
- `self_discipline` 只能是 `low` | `medium` | `high`
- 用「只改 JSON」冒充新增机制逻辑

**推荐流程：** `model_cli propose → edit-config → validate → promote →（用户批准）approve --config-only`

### 4.3 `edit-health-mechanisms`（改机制）

**白名单（唯一可写代码区）：**

```text
modules/health_mechanisms/**
data/mechanism/prompts/health_*.txt
data/mechanism/registry.json
```

新旋钮经 `get_path(...)` 接入后，再用 config skill 写入 JSON。

**禁止（越权即停）：**

- `start.py`、`agent.think` / memory / maze 寻路主体
- `start_health_simulation*.py` 日循环（除非用户明确批准仅为挂钩）
- 旧 re-export 壳（`agent_health.py` 等）里写回逻辑
- `frontend/**`、`replay*.py`、`visualize_health.py`
- `modules/mechanism_config/**`（loader / VersionStore）
- 非 health 的 `data/prompts/**`

**推荐流程：** `propose → edit-code → validate → promote →（用户批准）approve`

### 4.4 与仿真内 LLM 的区别

| | 仿真内 LLM（意图/策略对话） | Cursor Skill 约束的 AI |
|--|---------------------------|------------------------|
| 输入 | Prompt + 当日状态 | 用户自然语言 + 仓库文件 |
| 输出 | Intention / Strategy 等运行时对象 | 改 JSON 和/或白名单内机制文件 |
| 能否改代码/参数文件 | 否 | 可以，但受上述白名单与批准流程约束 |

---

## 5. 注册表中已登记的机制（全量）

权威来源：[`generative_agents/data/mechanism/registry.json`](../generative_agents/data/mechanism/registry.json)。  
下表与注册表 **一一对应**（共 17 项），勿只截取部分。

| ID | 标题 | 实现 | 配置路径 / 数据 | 关联 prompts |
|----|------|------|-----------------|--------------|
| `health_score` | 健康分（非线性主路径） | `modules.health_mechanisms.scoring.nonlinear.NonlinearHealthScorer` | `simulation.health` | — |
| `health_score_linear` | 健康分（线性兼容） | `modules.health_mechanisms.scoring.linear.CumulativeHealthScorer` | `simulation.health` | — |
| `mood` | 情绪分 | `modules.health_mechanisms.scoring.nonlinear.Scorer.calculate_mood_score_with_discipline` | `simulation.mood` | — |
| `satisfaction` | 满意度 | `modules.health_mechanisms.scoring.nonlinear.Scorer.calculate_satisfaction_score` | `simulation.satisfaction` | — |
| `relapse` | 复发（被管者行为） | `modules.health_mechanisms.agent_mixin.HealthAgentMixin.calculate_relapse_probability` | `simulation.relapse` | — |
| `habit` | 习惯 streak / 倾向 | `modules.health_mechanisms.agent_mixin.HealthAgentMixin.update_habit_streak` | `simulation.habit` | — |
| `compliance` | 劝说服从 / 抵抗 | `modules.health_mechanisms.agent_mixin.HealthAgentMixin.react_to_persuasion` | `simulation.compliance` | `health_generate_persuasion`, `health_react_persuasion` |
| `intention` | 意图生成 | `modules.health_mechanisms.agent_mixin.HealthAgentMixin.generate_intention` | `simulation.subject` | `health_generate_intention`, `health_generate_intention_batch` |
| `violation` | 违规判定 / 睡眠意图归一 / 日终未阻止计数 | `modules.health_mechanisms.rules.violation` | 无（关键词等仍硬编码） | — |
| `env_block` | 环境阻止（锁厨/移食/收手机） | `modules.health_mechanisms.rules.env_block` | 无 | — |
| `turnaround` | 折返独白与当日干预降级 | `modules.health_mechanisms.rules.turnaround` | 无 | `health_generate_turnaround` |
| `intervention_execute` | 干预执行 | `modules.health_mechanisms.agent_mixin.HealthAgentMixin.execute_intervention` | `management.intervention` | — |
| `management` | 长期管理策略 | `modules.health_mechanisms.management.strategy.LongTermStrategyManager` | `management`（含 tidal / relationship_phases / trust_capital / habit_consolidation / manager_learning / over_intervention / reflection 等） | `health_evaluate_strategy`, `health_evaluate_strategy_batch`, `health_daily_reflection` |
| `asymmetric_game` | 信息不对称博弈 | `modules.health_mechanisms.asymmetric_game.AsymmetricGameEngine` | 无（`config_path: null`；参数尚未外置到 mechanism JSON） | — |
| `scenario` | 场景语义配置 | `modules.health_mechanisms.scenario.ScenarioConfig` | 无 JSON 配置路径；数据文件 `data/semantic_mapping.json` | — |
| `behavior_scores` | 行为分项表 | `modules.health_mechanisms.scoring.nonlinear.Scorer` | `simulation.behavior_scores` | — |
| `composite` | 综合评估 | `modules.health_mechanisms.scoring.nonlinear.Scorer.calculate_composite_score` | `simulation.composite` | — |

**AI 可编辑代码根目录**（registry `meta.editable_code_roots`）：

- `modules/health_mechanisms/`
- `data/mechanism/prompts/`

**配置根目录**：`data/mechanism/`

新增/删除机制时，必须同步更新 `registry.json`，并保持本文表格与之一致。

---

## 6. 本地保留、不要提交的内容

以下为运行时/测试产物，已写入 `.gitignore`，请留在本地：

- `data/mechanism/models/`
- `data/mechanism/proposals/`
- `data/mechanism/sandboxes/`
- `data/mechanism/versions/v_*.json`（测试存档；仓库只跟踪 `v0_baseline.json` + 干净的 `manifest.json`）
- `generative_agents/results/`（仿真结果）

---

## 7. 相关文档与 Skill

- [健康机制改动前后对比.md](./健康机制改动前后对比.md)
- [机制参数JSON使用指南.md](./机制参数JSON使用指南.md)
- [mechanism/](./mechanism/)（机制文档索引；含 [参数升降影响手册](./mechanism/机制参数升降影响手册.md)）
- Skill：`.cursor/skills/edit-mechanism-config/`、`.cursor/skills/edit-health-mechanisms/`

---

## 8. 与老师沟通时的一句话

> 健康机制代码统一在 `health_mechanisms/`，参数继续用 JSON；AI 通过两个 Skill 分别改参数与改机制，且白名单限制不能动基座；改动先进 proposal/model，经校验与批准后才进 live，并支持回滚。
