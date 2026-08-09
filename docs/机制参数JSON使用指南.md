# 机制参数 JSON 使用指南

通过 JSON 文件调控健康干预仿真的模拟/管理参数，支持版本存档与回退。  
主路径评分为 **非线性**（`NonlinearHealthScorer` + `Scorer`，均在 `scorer_nonlinear.py`）。

---

## 1. 文件位置

在 `generative_agents/` 下：

| 路径 | 作用 |
|------|------|
| `data/mechanism/active.json` | **当前生效**配置（默认仿真会加载） |
| `data/mechanism/defaults/v0_baseline.json` | 基线默认值（与 active 深合并） |
| `data/mechanism/versions/*.json` | 不可变历史快照 |
| `data/mechanism/versions/manifest.json` | 版本索引与当前 `active_id` |

---

## 2. 快速开始：改参并生效

```bash
cd generative_agents
```

### 步骤 A：直接改 active（适合临时试）

1. 编辑 `data/mechanism/active.json`（可只改需要的字段，缺失项会从 baseline 补齐）。
2. 立刻跑仿真即可生效：

```bash
python start_health_simulation.py --scenario diabetes --days 30
```

启动日志会打印当前机制配置的 `version_id` / `name`。

### 步骤 B：改完存档，方便回退（推荐）

```bash
# 1. 编辑 active.json 后存成新版本
python tools/mechanism_cli.py save --name 实验_提高复发 --note "base_prob=0.25"

# 2. 查看版本列表（带 * 的是当前 active）
python tools/mechanism_cli.py list

# 3. 若效果不好，回退到基线（回退前会自动再存一份）
python tools/mechanism_cli.py rollback v0_baseline
```

---

## 3. 仿真时指定 JSON / 版本

两个参数**互斥**：

| 参数 | 含义 |
|------|------|
| `--mechanism-config PATH` | 加载指定 JSON 文件进进程 |
| `--mechanism-version ID` | 加载 `versions/<ID>.json` 进进程 |

**注意**：`--mechanism-version` **只加载进当前进程**，不会改写 `active.json`（避免误覆盖）。若希望全局默认变成某版本，请用 CLI 的 `activate`。

```bash
# 用历史版本跑一次（不改 active）
python start_health_simulation.py \
  --scenario diabetes \
  --mechanism-version v0_baseline

# 用任意路径的 JSON 跑一次
python start_health_simulation.py \
  --scenario diabetes \
  --mechanism-config /path/to/my_mechanism.json

# 可视化入口同样支持
python start_health_simulation_visual.py \
  --scenario phone-addiction \
  --mechanism-version v0_baseline
```

Checkpoint / 结果 metadata 会写入 `mechanism_version_id`，便于复现。

---

## 4. CLI 命令一览

均在 `generative_agents/` 目录执行：

```bash
python tools/mechanism_cli.py list
python tools/mechanism_cli.py show
python tools/mechanism_cli.py show --version v0_baseline
python tools/mechanism_cli.py save --name 实验A --note "说明"
python tools/mechanism_cli.py activate <version_id>   # 复制为 active.json
python tools/mechanism_cli.py rollback <version_id>  # 等同回退；默认先 autosave
python tools/mechanism_cli.py diff <id_a> <id_b>
```

| 命令 | 作用 |
|------|------|
| `list` | 列出全部版本 |
| `show` | 看 active 或指定版本的关键字段摘要 |
| `save` | 把当前 `active.json` 存成新版本快照 |
| `activate` | 把某版本写成 `active.json`（之后默认仿真都用它） |
| `rollback` | 回退到某版本（默认先自动保存当前） |
| `diff` | 对比两个版本差异 |

---

## 5. JSON 结构（顶层）

```json
{
  "meta": {
    "version_id": "v0_baseline",
    "name": "baseline",
    "created_at": "2026-08-09T00:00:00Z",
    "note": "说明"
  },
  "simulation": {
    "subject": { },
    "health": { },
    "relapse": { },
    "mood": { },
    "compliance": { },
    "behavior_scores": { },
    "habit": { },
    "satisfaction": { },
    "composite": { }
  },
  "management": {
    "intervention": { },
    "tidal": { },
    "relationship_phases": { },
    "trust_capital": { },
    "habit_consolidation": { },
    "manager_learning": { },
    "over_intervention": { },
    "reflection": { }
  }
}
```

完整默认值见：`generative_agents/data/mechanism/defaults/v0_baseline.json`。  
参数含义表见：`docs/健康干预仿真_可调参数全景.md`。

### 常用字段示例

```json
{
  "simulation": {
    "subject": {
      "self_discipline": "medium",
      "initial_health": 75
    },
    "relapse": {
      "base_prob": 0.15
    },
    "health": {
      "warning_line": 30,
      "nonlinear": {
        "warning_line": 30
      }
    },
    "satisfaction": {
      "base_score": 6.0
    }
  }
}
```

- `self_discipline` **只能**是：`low` | `medium` | `high`。
- 非线性健康分请改 `simulation.health.nonlinear.*`（主路径）；线性字段多为兼容保留。

---

## 6. 代码中导入配置

```python
from modules.mechanism_config import (
    load_mechanism_config,
    get_mechanism_config,
    get_path,
    VersionStore,
)

# 加载 active（或指定路径）
cfg = load_mechanism_config()
# cfg = load_mechanism_config("data/mechanism/active.json")

# 读单个字段（带默认值）
base_prob = get_path("simulation.relapse.base_prob", default=0.15)

# 版本操作
store = VersionStore()
vid = store.save("实验A", note="说明")
store.activate(vid)
store.rollback("v0_baseline", autosave=True)
```

评分相关请从非线性模块导入：

```python
from modules.scorer_nonlinear import NonlinearHealthScorer, Scorer
```

---

## 7. 不会被 JSON 覆盖的项

以下按标注保留硬编码，写在 JSON 里也会被忽略/剥离：

- `natural_recovery` / `natural_recovery_range`
- `blocked_violation_factor`
- `MAX_EFFECTIVE_VIOLATIONS`

---

## 8. 推荐工作流

1. 从 `v0_baseline` 复制思路，改 `active.json` 中少数关键旋钮（如 `relapse.base_prob`、`health.nonlinear`）。
2. `save --name ...` 存档。
3. 用 `--mechanism-version <id>` 或 `activate` 后跑仿真，看曲线。
4. 不合适则 `rollback v0_baseline`，再开新版本继续试。

开发设计说明见：`docs/MECHANISM_CONFIG_DEV_PLAN.md`。
