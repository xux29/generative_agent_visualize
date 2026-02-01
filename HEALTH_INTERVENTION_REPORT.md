# 健康干预模拟系统 - 项目架构与使用指南

本报告专注于基于斯坦福AI小镇汉化版魔改的**健康干预模拟功能**，不包含原版小镇的通用功能。

**当前分支**: `feature/nonlinear-health-scoring`
**核心更新**: 非线性健康分计算系统 + 累积健康分系统

---

## 一、项目演进历史（基于Git提交记录）

| 提交 | 描述 | 新增功能 |
|------|------|----------|
| `35d894b` | mom and daughter firstly | 首次实现妈妈-女儿监管关系 |
| `37dff00` | 可达性/手机可用性显示前端 | 前端显示监管状态 |
| `e724639` | 厨房逻辑全局性 | 全局厨房可达性控制 |
| `eb0aa7c` | diabetesHome | 糖尿病场景 |
| `709201b` | 妻子管丈夫减肥的场景 | 减肥监管场景(cphome) |
| `89fb02d` | 父母管女儿玩手机的案例 | 手机成瘾场景(home) |
| `b8803e3` | 健康管理模拟系统 | 完整45天模拟、数据收集、评分系统 |
| `65c9205` | **非线性健康分计算系统** | 阈值效应、累积损伤、边际递减、随机波动 |

---

## 二、系统架构

### 2.1 核心角色模型

系统采用 **Supervisor-Supervised（监管者-被监管者）** 双角色架构：

```
┌─────────────────────────────────────────────────────────────┐
│                    健康干预模拟系统                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    监控/干预    ┌─────────────┐           │
│  │  Supervisor │ ─────────────→ │  Supervised │           │
│  │  (监管者)    │                │  (被监管者)  │           │
│  │  如：山姆    │ ←───────────── │  如：亚当    │           │
│  └─────────────┘    反馈/抵抗    └─────────────┘           │
│         │                              │                   │
│         ▼                              ▼                   │
│  ┌─────────────┐               ┌─────────────┐            │
│  │ 策略评估     │               │ 意图生成     │            │
│  │ (Strategy)  │               │ (Intention) │            │
│  └─────────────┘               └─────────────┘            │
│                                                             │
│  干预手段：手机可用性控制 | 厨房可达性控制                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块一览

| 模块 | 路径 | 功能 |
|------|------|------|
| **Intention** | `modules/intention.py` | 被监管者的行为意图（活动、持续时间、屈服阈值） |
| **Strategy** | `modules/strategy.py` | 监管者的干预策略（4个等级：观察→劝说→移除→锁定） |
| **Scorer** | `modules/scorer.py` | 线性健康分（规则计算）+ 满意度（LLM评估） |
| **NonlinearHealthScorer** | `modules/scorer_nonlinear.py` | **[新]** 非线性健康分计算系统 |
| **ScenarioConfig** | `modules/scenario_config.py` | **[新]** 场景配置加载器 |
| **HealthAgentMixin** | `modules/agent_health.py` | **[新]** Agent健康管理扩展（复发机制） |
| **AsymmetricGameEngine** | `modules/asymmetric_game.py` | **[新]** 非对称博弈引擎 |
| **DailySettlement** | `modules/daily_settlement.py` | 每日结算（收集数据、触发反思） |
| **DataCollector** | `modules/data_collector.py` | 数据收集与导出（JSON/CSV） |
| **start_health_simulation.py** | 根目录 | 健康模拟主入口 |
| **start_health_simulation_visual.py** | 根目录 | **[新]** 可视化版健康模拟（支持位置更新） |
| **compress_health.py** | 根目录 | **[新]** 健康数据压缩（独立于compress.py） |
| **replay_health.py** | 根目录 | **[新]** 健康可视化服务器（端口5001） |

---

## 三、非线性健康分系统（核心创新）

### 3.1 设计理念

相比线性系统的固定 `penalty` 和 `recovery`，非线性系统模拟真实人类健康指标的动态变化：

| 特性 | 线性系统 | 非线性系统 |
|------|----------|------------|
| 违规惩罚 | 固定值（如-10） | 随机范围 + 区间敏感度 + 累积系数 |
| 自然恢复 | 固定值（如+3） | 边际递减 + 区间恢复倍数 + 习惯加成 |
| 日常变化 | 完全可预测 | 随机波动（模拟生理变异） |
| 极端情况 | 线性下滑 | 底线保护 + 底线增强 |

### 3.2 健康区间系统

```python
HEALTH_ZONES = {
    EMERGENCY: (0-29)   # 紧急：需要医疗干预，恢复极其缓慢
    DANGER:    (30-49)  # 危险：接近生理极限，微小违规可能崩溃
    WARNING:   (50-69)  # 预警：缓冲减少，敏感度上升
    NORMAL:    (70-89)  # 正常：基线状态
    SAFE:      (90-100) # 安全：生理缓冲充足，小违规影响小
}
```

每个区间有不同的：
- **敏感度 (sensitivity)**: 违规惩罚的倍数
- **恢复倍数 (recovery_mult)**: 自然恢复的速度

### 3.3 自律程度参数

| 参数 | 高自律 | 中自律 | 低自律 |
|------|--------|--------|--------|
| 违规惩罚范围 | 7-10 | 4-5 | 3.5-4.5 |
| 自然恢复范围 | 4.5-6.5 | 3.5-4.5 | 2.5-3.5 |
| 累积系数 | 0.04 | 0.03 | 0.01 |
| 日常波动 σ | 0.3 | 0.5 | 0.6 |
| 韧性 | 1.3 | 1.2 | 1.3 |

### 3.4 核心公式

**每日健康分变化**:
```
ΔHealth = Recovery + Compliance - Penalty - Acceleration + Noise

新健康分 = max(0, min(初始分, 当前分 + ΔHealth))
```

**违规惩罚（非线性）**:
```python
penalty = base_penalty              # 随机基础值
        × cumulative_mult           # 累积系数 (1 + 连续违规 × factor)
        × zone_sensitivity          # 区间敏感度
        × resilience_mult           # 韧性修正
        × floor_protection          # 底线保护（健康分<30时惩罚降低）
        × violation_count           # 违规次数
```

**自然恢复（非线性）**:
```python
recovery = base_recovery            # 随机基础值
         × distance_factor          # 边际递减 sqrt(1 - current/initial)
         × zone_recovery_mult       # 区间恢复倍数
         × habit_mult               # 习惯加成 (1 + min(0.3, 连续好天数 × 0.02))
         × floor_boost              # 底线增强（健康分<30时恢复加速）
```

### 3.5 底线保护机制

**防止健康分雪崩**:
- 健康分 < 15: 惩罚降至 10%（"濒死状态"）
- 健康分 < 30: 惩罚降至 30%（"危险状态"）
- 健康分 < 50: 惩罚降至 60%（"警戒状态"）

**加速恢复**:
- 健康分 < 15: 恢复 ×5（"重症监护"）
- 健康分 < 30: 恢复 ×3（"住院治疗"）
- 健康分 < 50: 恢复 ×1.5（"门诊治疗"）

---

## 四、干预机制详解

### 4.1 意图生成（Intention）

被监管者根据当前状态生成真实意图：

**输入因素**：
- 自律度（low/medium/high）
- 当前心情（normal/stressed/depressed）
- 连续自律天数
- 手机/厨房可用状态

**输出**：
```json
{
    "intention": "玩手机",
    "duration": 120,
    "inner_monologue": "今天工作太累了，想放松一下",
    "compliance_threshold": 2
}
```

### 4.2 策略评估（Strategy）

| 等级 | 名称 | 动作示例 | 适用场景 |
|------|------|----------|----------|
| **Level 0** | 观察 | 不干预 | 被监管者行为健康 |
| **Level 1** | 劝说 | 口头提醒 | 心情差时避免激化 |
| **Level 2** | 移除 | 拿走手机/零食 | 中等强度干预 |
| **Level 3** | 锁定 | 锁厨房门 | 时间很晚+习惯差 |

### 4.3 干预执行流程

```
Phase 1: 收集意图
    └→ 所有被监管者生成意图（并行）

Phase 2: 评估策略
    └→ 监管者评估每个被监管者的意图（串行）

Phase 3: 执行干预
    ├→ 有干预：执行动作，时间推进10分钟
    └→ 无干预：时间跳跃到下一个意图结束

Phase 4: 完成意图
    └→ 记录不健康行为（手机时长、进食事件）
```

### 4.4 复发机制（潮汐性变化）

**核心概念**：被管了变好，放松后可能"复发"

```python
# agent_health.py 中的复发相关属性
self.is_in_relapse = False           # 是否处于复发状态
self.days_since_last_bad_behavior = 0  # 距离上次不良行为的天数
self.relapse_tendency = 0.0          # 复发倾向 (0-1)
self.behavior_quality_history = []   # 行为质量历史
```

复发概率受以下因素影响：
- 自律程度
- 成瘾程度
- 放松时间长度

---

## 五、场景配置系统

### 5.1 ScenarioConfig 类

新增的场景配置加载器，支持：

```python
class ScenarioConfig:
    # 基础配置
    scenario_name: str      # 场景名称
    target_agent: str       # 被监管者名称
    manager_agent: str      # 监管者名称
    map_folder: str         # 地图文件夹（默认village）

    # 人设配置
    target_profile: {
        "self_discipline": "low/medium/high",
        "addiction_level": "none/low/moderate/high/severe",
        "resistance_to_persuasion": 0.0-1.0,
        "age": int,
        "personality_traits": [],
        "background": str
    }

    manager_profile: {
        "supervision_style": "gentle/supportive/adaptive/strict",
        "escalation_threshold": int,
        "relationship": str
    }
```

### 5.2 预配置场景

| 场景ID | 角色 | 核心矛盾 |
|--------|------|----------|
| **phone-addiction** | 山姆 → 亚当 | 孩子手机成瘾 vs 家长监管 |
| **weight-loss** | 山姆 → 亚当 | 减肥目标 vs 深夜偷吃 |
| **diabetes** | 山姆 → 亚当 | 糖尿病控制 vs 偷吃甜食 |
| **home-diabetes** | 自定义角色 | 家庭糖尿病场景 |
| **home-phone-addiction** | 自定义角色 | 家庭手机成瘾场景 |

---

## 六、使用方法

### 6.1 命令行接口

```bash
cd generative_agents

# 基本用法
python start_health_simulation.py --scenario <场景> [选项]
```

### 6.2 必需参数

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--scenario` | 场景名称 | `weight-loss`, `phone-addiction`, `diabetes`, `home-diabetes`, `home-phone-addiction` |

### 6.3 可选参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--days` | 模拟天数 | 90 |
| `--initial-health` | 初始健康分 | 75 (可选: 60, 75, 90) |
| `--discipline` | 自律程度 | medium (可选: low, medium, high) |
| `--resume` | 从检查点恢复 | - |
| `--batch` | 批处理模式（~10倍加速） | - |
| `--parallel N` | 并行工作线程数 | 0（顺序执行） |
| `--verbose` | 日志级别 | info (可选: debug, info) |
| `--status` | 显示模拟状态后退出 | - |
| `--run-all` | 运行所有9种实验组合 | - |

### 6.4 使用示例

```bash
# 手机成瘾场景（默认参数）
python start_health_simulation.py --scenario phone-addiction

# 减肥场景，5天测试
python start_health_simulation.py --scenario weight-loss --days 5

# 糖尿病场景，低初始健康分，高自律
python start_health_simulation.py --scenario diabetes --initial-health 60 --discipline high

# 恢复之前中断的模拟
python start_health_simulation.py --scenario phone-addiction --resume

# 批处理模式加速
python start_health_simulation.py --scenario weight-loss --batch

# 并行运行（需要多个API密钥）
python start_health_simulation.py --scenario diabetes --parallel 4

# 运行所有9种实验组合（3种初始分 × 3种自律程度）
python start_health_simulation.py --scenario phone-addiction --run-all
```

### 6.5 实验组合矩阵

使用 `--run-all` 参数时，自动运行以下9种组合：

| 初始健康分 | 低自律 | 中自律 | 高自律 |
|------------|--------|--------|--------|
| 60（低） | ✓ | ✓ | ✓ |
| 75（中） | ✓ | ✓ | ✓ |
| 90（高） | ✓ | ✓ | ✓ |

---

## 七、可视化系统

### 7.1 独立的可视化 Pipeline

健康模拟可视化采用**完全独立的 Pipeline**，不影响原有的 `start.py` / `compress.py` / `replay.py`：

```
原有流程（不受影响）：
  start.py       -> results/checkpoints/{name}/
  compress.py    -> results/compressed/{name}/
  replay.py      -> http://127.0.0.1:5000/

健康模拟流程（完全独立）：
  start_health_simulation_visual.py  -> results/health/{scenario}/{run}/
  compress_health.py                 -> results/compressed/health-{scenario}-{run}/
  replay_health.py                   -> http://127.0.0.1:5001/
```

### 7.2 可视化数据结构

```
results/
├── health/                           # 原始模拟数据
│   └── phone-addiction/              # scenario 名称
│       ├── init75_medium_20260130_162408/   # 运行实例（含时间戳）
│       │   ├── checkpoints/          # Checkpoint 文件
│       │   ├── simulation.log        # 日志
│       │   └── simulation_state.json # 恢复状态
│       └── init75_medium_latest -> ...      # 软链接指向最新
│
└── compressed/                       # 压缩后的可视化数据
    └── health-phone-addiction-init75_medium_20260130_162408/
        ├── movement.json             # 移动数据（含健康分字段）
        └── simulation.md             # 时间线报告
```

### 7.3 可视化界面布局

采用**右侧边栏**设计，主游戏区域在左侧，健康信息面板在右侧：

```
┌─────────────────────────────────────┬──────────────────┐
│                                     │  模拟进度        │
│                                     │  Day 15 / 90     │
│                                     ├──────────────────┤
│                                     │  健康状态        │
│          游戏地图                    │  75.0           │
│        (Phaser 渲染)                │  [NORMAL]        │
│                                     │  🌊 正常期       │
│                                     ├──────────────────┤
│                                     │  当前干预        │
│                                     │  Level 1 - 劝说  │
│                                     ├──────────────────┤
│                                     │  操作说明        │
│                                     │  🖱️ 滚轮: 缩放   │
│                                     │  🖱️ Shift+拖动   │
├─────────────────────────────────────┴──────────────────┤
│  [亚当] [山姆]    点击角色可查看详情                      │
└─────────────────────────────────────────────────────────┘
```

### 7.4 健康区域颜色编码

| 区域 | 分数范围 | 颜色 | CSS类 |
|------|----------|------|-------|
| SAFE | 90-100 | 绿色 | `.zone-safe` |
| NORMAL | 70-89 | 蓝色 | `.zone-normal` |
| WARNING | 50-69 | 黄色 | `.zone-warning` |
| DANGER | 30-49 | 橙色 | `.zone-danger` |
| EMERGENCY | 0-29 | 红色 | `.zone-emergency` |

### 7.5 地图交互功能

| 操作 | 功能 |
|------|------|
| 🖱️ **滚轮** | 缩放地图 (0.3x - 2.0x) |
| 🖱️ **Shift+拖动** | 平移视角 |
| 🖱️ **中键拖动** | 平移视角 |
| ⌨️ **方向键** | 移动视角 |
| 🖱️ **点击角色** | 居中显示该角色 |

### 7.6 可视化使用流程

```bash
cd generative_agents

# 1. 运行可视化版健康模拟
python start_health_simulation_visual.py --scenario phone-addiction --days 45

# 2. 查看可用的运行实例
python compress_health.py --list

# 3. 压缩数据（默认压缩最新运行）
python compress_health.py --scenario phone-addiction

# 或压缩指定运行
python compress_health.py --scenario phone-addiction --run init75_medium_20260130_162408

# 4. 启动可视化服务器
python replay_health.py

# 5. 浏览器打开
#    http://127.0.0.1:5001/
#    或直接访问特定模拟：
#    http://127.0.0.1:5001/?name=health-phone-addiction-init75_medium_20260130_162408
```

### 7.7 movement.json 健康数据字段

可视化版 `movement.json` 除了标准字段外，还包含：

```json
{
  "is_health_simulation": true,
  "all_movement": {
    "1": {
      "亚当": {
        "location": "卧室，床",
        "movement": [20, 65],
        "action": "😴 睡觉",
        "health_score": 75.0,
        "health_zone": "NORMAL",
        "day": 1,
        "tide_phase": "normal",
        "intervention_level": 0,
        "intervention_action": ""
      }
    }
  }
}
```

---

## 八、输出数据

### 8.1 输出目录结构

```
results/health/<scenario>/
├── init60_low_<timestamp>/        # 初始分60 + 低自律
│   ├── checkpoint_day_XX.json     # 每日检查点
│   ├── daily_log.json             # 每日详细日志
│   └── summary.json               # 模拟总结
├── init75_medium_<timestamp>/     # 初始分75 + 中自律
└── init90_high_<timestamp>/       # 初始分90 + 高自律
```

### 8.2 非线性评分器输出示例

```json
{
  "day": 15,
  "initial_score": 75.0,
  "new_score": 58.3,
  "change": -4.2,
  "zone": "WARNING",
  "components": {
    "violation": -5.8,
    "cumulative_multiplier": 1.06,
    "daily_noise": 0.3
  },
  "consecutive_good_days": 0,
  "consecutive_bad_days": 2,
  "consecutive_violations": 3,
  "in_plateau": false,
  "below_warning": false
}
```

---

## 九、新增提示词模板

健康干预系统新增的提示词模板（位于 `data/prompts/`）：

| 模板 | 功能 |
|------|------|
| `generate_intention.txt` | 生成被监管者的真实行为意图 |
| `evaluate_strategy.txt` | 监管者评估干预策略 |
| `satisfaction.txt` | 被监管者评估满意度 |
| `generate_persuasion.txt` | 生成劝说内容 |
| `daily_reflection.txt` | 监管者每日反思 |
| `phone_unavailable.txt` | 手机不可用时的替代活动 |

---

## 十、与原版的主要区别

| 方面 | 原版斯坦福小镇 | 健康干预版 |
|------|---------------|-----------|
| **角色关系** | 平等的25个智能体 | Supervisor-Supervised层级 |
| **时间范围** | 全天24小时 | 聚焦夜间19:00-02:00 |
| **模拟周期** | 单次运行 | 90天长期模拟（可配置） |
| **数据收集** | 回放为主 | 健康分+满意度量化 |
| **干预机制** | 无 | 4级干预策略 |
| **环境控制** | 无 | 手机/厨房可达性 |
| **评分系统** | 无 | 线性 + 非线性双模式 |
| **复发机制** | 无 | 潮汐性行为变化 |
| **实验设计** | 无 | 9种组合自动运行 |

---

## 十一、相关文档

| 文档 | 路径 | 内容 |
|------|------|------|
| 评分公式完整文档 | `HEALTH_SCORING_FORMULAS.md` | 所有数学公式和参数定义 |
| 非线性分析 | `HEALTH_SCORING_NONLINEAR_ANALYSIS.md` | 非线性系统的设计原理 |
| 非线性系统总结 | `NONLINEAR_SYSTEM_SUMMARY.md` | 实施总结和调优结果 |
| 集成指南 | `NONLINEAR_SCORER_INTEGRATION.md` | 如何集成非线性评分器 |
| 完整使用指南 | `HEALTH_SIMULATION_COMPLETE_GUIDE.md` | 详细使用说明 |
| 场景配置总结 | `SCENARIO_CONFIG_SUMMARY.md` | 场景配置说明 |

---

## 十二、依赖安装

此分支需要额外安装以下依赖：

```bash
pip install magentic llama-index llama-index-embeddings-huggingface llama-index-embeddings-ollama
```

---

## 十三、总结

本健康干预模拟系统在斯坦福AI小镇的基础上，实现了：

1. **双角色架构**：Supervisor监管Supervised的行为
2. **意图-策略博弈**：被监管者生成意图，监管者评估策略
3. **非线性评分**：阈值效应、累积损伤、边际递减、随机波动
4. **底线保护**：防止健康分雪崩，模拟医疗干预
5. **复发机制**：潮汐性行为变化，更接近真实人类
6. **长期模拟**：90天数据收集与趋势分析
7. **环境控制**：手机可用性、厨房可达性等具身干预
8. **多场景支持**：手机成瘾、减肥、糖尿病等预配置场景
9. **实验矩阵**：9种组合（3初始分 × 3自律程度）自动运行
10. **批处理加速**：~10倍速度提升选项

适用于研究健康行为干预策略的有效性与用户体验平衡问题。
