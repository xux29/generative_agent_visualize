---
name: edit-health-mechanisms
description: >-
  Safely add, modify, or remove health simulation mechanisms in code and prompts
  within the whitelisted health_mechanisms package. Use when the user asks to
  change formulas, state machines, relapse/health/mood logic, management
  strategy rules, or health prompts—not when only tuning existing JSON
  numeric parameters.
---

# 增删改健康模拟机制

在 `generative_agents/` 下工作。机制本体是 **Python + health prompts**；JSON 只挂可调参数。

## 硬性白名单（唯一可写代码区）

允许创建/修改/删除的路径**仅限**：

```text
generative_agents/modules/health_mechanisms/**          # 机制代码
generative_agents/data/mechanism/prompts/health_*.txt   # 健康 prompt 模板
generative_agents/data/mechanism/registry.json          # 登记实现与 config_path
```

可选配套（仅当新机制需要可调旋钮时）：

- 经 skill `edit-mechanism-config` 更新 `data/mechanism/active.json` / defaults 中的**新参数键**
- 不在本 skill 里改 `modules/mechanism_config/schema.py`，除非用户明确要求且仅为放开新键校验

## 硬性禁止（越权即停，必须拒绝）

不要修改、重构、移动下列内容（即使用户顺口提到「顺便」）：

| 禁止区 | 示例 |
|--------|------|
| 斯坦福基座 | `start.py`、`modules/agent.py` 的 `think/percept/reflect`、`memory/*`、`maze.py` 寻路主体 |
| 编排入口 | `start_health_simulation.py` / `_visual.py` 日循环（除非仅为 import 新机制且用户明确要求） |
| 旧兼容壳 | 不要把逻辑写回 `modules/agent_health.py` 等 re-export 文件 |
| 可视化/前端 | `frontend/**`、`replay*.py`、`visualize_health.py` |
| 通用 LLM/prompt 基座 | `modules/prompt/scratch.py` 非 health 部分、`data/prompts/` 非 `health_*` |
| 参数加载内核 | `modules/mechanism_config/**`（loader/version_store） |
| 其它 | `config_health.json` API 密钥、实验结果 `results/**` |

若需求落在禁止区：说明越权，建议改白名单内机制或请用户扩大授权。

## 参数问题还是机制问题？

| 信号 | 动作 |
|------|------|
| 「概率太大/太小」「权重调一下」且字段已在 JSON | 用 `edit-mechanism-config`，**本 skill 不改代码** |
| 「加一个环境压力因素」「改公式结构」「新状态」 | 本 skill |
| 只在 JSON 里塞新键但代码不读 | **无效**；必须先改代码 `get_path(...)` 再暴露 JSON |

## 推荐安全流程（proposal → validate → 批准）

```bash
cd generative_agents
python tools/model_cli.py propose --name <机制改动名> --note "<原因>" --by ai
# 在 proposal 内改代码（或先改 live 白名单文件再 snapshot——优先 proposal）
python tools/model_cli.py edit-code --proposal <P> \
  --file modules/health_mechanisms/<相对路径>.py --from-file <本地文件>
python tools/model_cli.py validate --proposal <P>
python tools/model_cli.py promote --proposal <P>
# 仅当用户明确同意落地：
python tools/model_cli.py approve --model <M>
```

直接改白名单文件时：改前建议 `python tools/model_cli.py snapshot --name before_<名>`；改后跑 validate / 短 import 冒烟。

## 修改现有机制

1. 查 `data/mechanism/registry.json` 找到 `implementation` 与 `config_path`。
2. 只编辑对应白名单文件中的目标函数/类。
3. 数值旋钮用 `get_path("simulation...." / "management....", default=...)`，default 保持原硬编码行为。
4. 不扩大修改面；不做无关格式化。
5. 若行为对用户可见，更新 registry 的 `title` / `prompts` 列表（如有）。

## 新增机制

清单（按序）：

1. 在 `modules/health_mechanisms/` 新增模块或扩展现有模块（命名清晰，如 `env_pressure.py`）。
2. 在日循环**已有挂钩点**被调用：优先从 `agent_mixin` / `scoring` / `management/strategy` 接入；**避免**改 `start_health_simulation.py`，除非无其它挂钩且用户批准。
3. 可调参数：`get_path` + 写入 `active.json` / `defaults/v0_baseline.json` 对应树（用 config skill）。
4. 登记 `registry.json`：
   ```json
   "my_mechanism": {
     "title": "...",
     "implementation": "modules.health_mechanisms....",
     "config_path": "simulation.xxx",
     "prompts": [],
     "editable_by_ai": true
   }
   ```
5. 若需 LLM：在 `prompts.py` 增加 `prompt_health_*`，模板放 `data/mechanism/prompts/health_*.txt`。
6. 验证：`python tools/model_cli.py validate` 或最小 import/单测；向用户报告接入点。

## 删除机制

1. 确认无仿真路径再调用；移除挂钩调用。
2. 删除或废弃白名单内实现；从 `registry.json` 去掉条目。
3. 可选清理 JSON 中仅该机制使用的键（经 config skill）。
4. 不要删除 re-export 壳文件（会破坏旧 import）。

## 输出给用户

每次改动结束说明：

- 改了哪些**白名单**文件
- 机制行为如何变化
- 是否新增/调整了 JSON 旋钮
- 是否已 validate；是否等待用户 `approve`

## 参考

- `docs/健康机制双层架构与AI编辑.md`
- `docs/健康机制改动前后对比.md`
- `data/mechanism/registry.json`
- 配对 skill：`edit-mechanism-config`
