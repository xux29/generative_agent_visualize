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

## 4. 注册表中已登记的机制（摘要）

见 `data/mechanism/registry.json`，主要包括：

| ID | 说明 | 配置路径（若有） |
|----|------|------------------|
| health_score | 非线性健康分 | `simulation.health` |
| mood | 情绪分 | `simulation.mood` |
| satisfaction | 满意度 | `simulation.satisfaction` |
| relapse | 复发概率 | `simulation.relapse` |
| habit | 习惯 streak | `simulation.habit` |
| compliance | 劝说服从 | `simulation.compliance` |
| intention | 意图生成 | — + prompts |
| management | 长期管理策略 | `management` |
| asymmetric_game | 信息不对称博弈 | （参数尚未全部外置） |
| scenario | 场景语义 | `semantic_mapping.json` |

---

## 5. 本地保留、不要提交的内容

以下为运行时/测试产物，已写入 `.gitignore`，请留在本地：

- `data/mechanism/models/`
- `data/mechanism/proposals/`
- `data/mechanism/sandboxes/`
- `data/mechanism/versions/v_*.json`（测试存档；仓库只跟踪 `v0_baseline.json` + 干净的 `manifest.json`）
- `generative_agents/results/`（仿真结果）

---

## 6. 与老师沟通时的一句话

> 健康机制代码统一在 `health_mechanisms/`，参数继续用 JSON；AI 可以改机制文件和参数两层，JSON 只是配置接口；改动先进 proposal/model，经校验与批准后才进 live，并支持回滚。
