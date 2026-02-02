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
| `835ac00` | 基于LLM的健康模拟位置更新 | 位置移动与行为联动 |
| `214f6e6` | 修复可视化地图缩放控制 | 地图缩放交互优化 |
| `ffb5220` | 修复跨午夜日期计算 | 跨午夜模拟日期正确处理 |
| `b853b2c` | **Agent详情面板** | 显示角色profile信息（性格、背景等） |
| `a5bb20f` | **新场景地图** | 添加weight-loss-scene专用地图 |
| `195129b` | 更换减肥场景，优化可视化 | 减肥场景使用独立地图 |
| `fa36748` | 健康回放控制和时间线 | Timeline时间线导航 |
| `296266e` | **改进健康回放控件** | 倍速控制、播放控制优化 |

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
| **Strategy** | `modules/strategy.py` | 监管者策略（信任资本、习惯形成、阶段管理、情绪评分） |
| **Scorer** | `modules/scorer.py` | 线性健康分 + **情绪评分系统** |
| **NonlinearHealthScorer** | `modules/scorer_nonlinear.py` | 非线性健康分计算系统 |
| **ScenarioConfig** | `modules/scenario_config.py` | 场景配置加载器 |
| **HealthAgentMixin** | `modules/agent_health.py` | Agent健康管理扩展（复发机制） |
| **AsymmetricGameEngine** | `modules/asymmetric_game.py` | 非对称博弈引擎（隐藏目标、耐心、挫败感） |
| **Visualizer** | `modules/visualizer.py` | **[新]** 可视化数据生成器 |
| **start_health_simulation.py** | 根目录 | 健康模拟主入口 |
| **start_health_simulation_visual.py** | 根目录 | 可视化版健康模拟（支持位置更新） |
| **compress_health.py** | 根目录 | 健康数据压缩（**含profile信息导出**） |
| **replay_health.py** | 根目录 | 健康可视化服务器（端口5001） |

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

## 四、情绪评分系统（新增功能）

### 4.1 设计目标

追踪被监管者对干预的**主观感受**，平衡健康效果与用户体验。

### 4.2 情绪评分组成

```
最终情绪分 = 基础分 + 频率修正 + 强度修正 + 合理性修正 + 习惯加成 + 服从修正
```

| 组件 | 说明 | 范围 |
|------|------|------|
| **base_score** | 基准分（根据自律程度） | 5-7 |
| **frequency_modifier** | 干预频率惩罚 | -5 ~ 0 |
| **intensity_modifier** | 干预强度惩罚 | -5 ~ 0 |
| **reasonability_modifier** | 合理性加成（干预有依据） | 0 ~ +5 |
| **habit_bonus** | 习惯形成加成 | 0 ~ +2 |
| **compliance_modifier** | 服从行为加成 | 0 ~ +1 |

### 4.3 情绪区间

| 分数 | 状态 | 含义 |
|------|------|------|
| 8-10 | 满意 | 被监管者认可干预方式 |
| 5-7 | 中等 | 有些不满但可接受 |
| 3-4 | 低落 | 明显抵触情绪 |
| 0-2 | 极差 | 可能引发对抗或放弃 |

---

## 五、干预机制详解

### 5.1 意图生成（Intention）

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

### 5.2 策略评估（Strategy）

| 等级 | 名称 | 动作示例 | 适用场景 |
|------|------|----------|----------|
| **Level 0** | 观察 | 不干预 | 被监管者行为健康 |
| **Level 1** | 劝说 | 口头提醒 | 心情差时避免激化 |
| **Level 2** | 移除 | 拿走手机/零食 | 中等强度干预 |
| **Level 3** | 锁定 | 锁厨房门 | 时间很晚+习惯差 |

### 5.3 干预执行流程

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

### 5.4 复发机制（潮汐性变化）

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

## 六、场景配置系统

### 6.1 ScenarioConfig 类

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

### 6.2 预配置场景

| 场景ID | 角色 | 地图 | 核心矛盾 |
|--------|------|------|----------|
| **phone-addiction** | 山姆 → 亚当 | village | 孩子手机成瘾 vs 家长监管 |
| **weight-loss** | 伊莎贝拉 → 亚瑟 | **weight-loss-scene** | 减肥目标 vs 深夜偷吃 |
| **diabetes** | 玛丽亚 → 克劳斯 | village | 糖尿病控制 vs 偷吃甜食 |
| **home-diabetes** | 机器人 → 妈妈 | homeWithRobot | 家庭糖尿病场景 |
| **home-phone-addiction** | 机器人 → 女儿 | homeWithRobot | 家庭手机成瘾场景 |

### 6.3 场景地图

| 地图文件夹 | 说明 | 使用场景 |
|-----------|------|----------|
| `village` | 原版AI小镇地图 | phone-addiction, diabetes |
| `weight-loss-scene` | **[新]** 减肥场景专用家庭地图 | weight-loss |
| `homeWithRobot` | 机器人管家场景地图 | home-diabetes, home-phone-addiction |

---

## 七、使用方法

### 7.1 命令行接口

```bash
cd generative_agents

# 基本用法
python start_health_simulation.py --scenario <场景> [选项]
```

### 7.2 必需参数

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--scenario` | 场景名称 | `weight-loss`, `phone-addiction`, `diabetes`, `home-diabetes`, `home-phone-addiction` |

### 7.3 可选参数

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

### 7.4 使用示例

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

### 7.5 实验组合矩阵

使用 `--run-all` 参数时，自动运行以下9种组合：

| 初始健康分 | 低自律 | 中自律 | 高自律 |
|------------|--------|--------|--------|
| 60（低） | ✓ | ✓ | ✓ |
| 75（中） | ✓ | ✓ | ✓ |
| 90（高） | ✓ | ✓ | ✓ |

---

## 八、可视化系统

### 8.1 独立的可视化 Pipeline

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

### 8.2 可视化数据结构

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

### 8.3 可视化界面布局

采用**右侧边栏**设计，主游戏区域在左侧，健康信息面板在右侧：

```
┌─────────────────────────────────────┬──────────────────┐
│  [运行] [暂停] [显示对话]  倍速: 1x  │  模拟进度        │
│  ─────────────────────────────────  │  Day 15 / 90     │
│                                     ├──────────────────┤
│                                     │  健康状态        │
│          游戏地图                    │  75.0           │
│        (Phaser 渲染)                │  [NORMAL]        │
│                                     │  🌊 正常期       │
│                                     ├──────────────────┤
│                                     │  当前干预        │
│                                     │  Level 1 - 劝说  │
│                                     ├──────────────────┤
│                                     │  情绪评分        │
│                                     │  3.7 / 10        │
├─────────────────────────────────────┴──────────────────┤
│  Timeline: [Day1 ●●●][Day2 ●●●○][Day3 ○○○]...          │
├─────────────────────────────────────────────────────────┤
│  [亚瑟] [伊莎贝拉]    点击角色查看详情（含profile信息）   │
└─────────────────────────────────────────────────────────┘
```

### 8.4 回放控件功能

| 控件 | 功能 |
|------|------|
| **运行/暂停** | 控制回放播放状态 |
| **显示/隐藏对话** | 切换对话框显示 |
| **倍速选择** | 0.5x / 1x / 2x / 4x |
| **Timeline** | 按天分组的时间线，点击节点跳转 |

### 8.5 Agent详情面板

点击角色名称可展开详情面板，显示：
- 角色头像和名称
- 当前活动和位置
- **Profile信息**（从semantic_mapping.json加载）：
  - 角色描述（年龄、性别、性格）
  - 背景故事
  - 健康状况
  - 典型借口和弱点

### 8.6 健康区域颜色编码

| 区域 | 分数范围 | 颜色 | CSS类 |
|------|----------|------|-------|
| SAFE | 90-100 | 绿色 | `.zone-safe` |
| NORMAL | 70-89 | 蓝色 | `.zone-normal` |
| WARNING | 50-69 | 黄色 | `.zone-warning` |
| DANGER | 30-49 | 橙色 | `.zone-danger` |
| EMERGENCY | 0-29 | 红色 | `.zone-emergency` |

### 8.7 地图交互功能

| 操作 | 功能 |
|------|------|
| 🖱️ **滚轮** | 缩放地图 (0.1x - 3.0x) |
| 🖱️ **Shift+拖动** | 平移视角 |
| 🖱️ **中键拖动** | 平移视角 |
| ⌨️ **方向键** | 移动视角 |
| 🖱️ **点击角色** | 居中显示该角色 |
| 🖱️ **点击Timeline节点** | 跳转到指定时间步 |

### 8.8 可视化使用流程

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

### 8.9 movement.json 健康数据字段

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

## 九、输出数据

### 9.1 输出目录结构

```
results/health/<scenario>/
├── init60_low_<timestamp>/        # 初始分60 + 低自律
│   ├── checkpoint_day_XX.json     # 每日检查点
│   ├── daily_log.json             # 每日详细日志
│   └── summary.json               # 模拟总结
├── init75_medium_<timestamp>/     # 初始分75 + 中自律
└── init90_high_<timestamp>/       # 初始分90 + 高自律
```

### 9.2 每日数据输出示例（day_XX.json）

```json
{
  "day": 2,
  "date": "2026-02-03",
  "events": [...],
  "interventions": [...],
  "agents": {...},

  "health_score": 66.17,
  "health_change": 2.99,
  "health_breakdown": {
    "components": {
      "natural_recovery": 1.34,
      "compliance_bonus": 1.67,
      "daily_noise": -0.02
    },
    "zone": "WARNING",
    "consecutive_good_days": 1
  },

  "emotion_score": 3.7,
  "emotion_breakdown": {
    "base_score": 6.0,
    "frequency_modifier": -3.0,
    "intensity_modifier": -4.3,
    "reasonability_modifier": 4.5,
    "final_score": 3.7
  },

  "strategy_manager": {
    "state_update": {
      "trust_level": 0.74,
      "phase": "honeymoon",
      "habit_stage": "forced"
    },
    "trust_capital": {
      "current_capital": 56.0,
      "autonomy_level": "medium"
    }
  },

  "asymmetric_game": {
    "manager_hidden": {
      "goal": "establish_trust",
      "patience": 100.0
    },
    "managed_person": {
      "perceived_strictness": 0.66,
      "frustration": 0.65
    }
  },

  "dynamic_phase": "honeymoon",

  "reflection": {
    "today_summary": "...",
    "strategy_effectiveness": "...",
    "risk_patterns": [...],
    "tomorrow_focus": "..."
  }
}
```

### 9.3 核心输出字段说明

| 字段 | 说明 |
|------|------|
| **health_score** | 累积健康分（非线性计算） |
| **emotion_score** | 被监管者情绪评分（0-10） |
| **strategy_manager** | 策略管理器状态（信任度、阶段、习惯形成） |
| **asymmetric_game** | 非对称博弈状态（隐藏目标、耐心、挫败感） |
| **dynamic_phase** | 当前干预阶段（honeymoon/adjustment/plateau等） |
| **reflection** | 每日反思总结 |

---

## 十、新增提示词模板

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

## 十一、与原版的主要区别

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

## 十二、相关文档

| 文档 | 路径 | 内容 |
|------|------|------|
| 评分公式完整文档 | `HEALTH_SCORING_FORMULAS.md` | 所有数学公式和参数定义 |
| 非线性分析 | `HEALTH_SCORING_NONLINEAR_ANALYSIS.md` | 非线性系统的设计原理 |
| 非线性系统总结 | `NONLINEAR_SYSTEM_SUMMARY.md` | 实施总结和调优结果 |
| 集成指南 | `NONLINEAR_SCORER_INTEGRATION.md` | 如何集成非线性评分器 |
| 完整使用指南 | `HEALTH_SIMULATION_COMPLETE_GUIDE.md` | 详细使用说明 |
| 场景配置总结 | `SCENARIO_CONFIG_SUMMARY.md` | 场景配置说明 |

---

## 十三、依赖安装

此分支需要额外安装以下依赖：

```bash
pip install magentic llama-index llama-index-embeddings-huggingface llama-index-embeddings-ollama
```

---

## 十四、总结

本健康干预模拟系统在斯坦福AI小镇的基础上，实现了：

1. **双角色架构**：Supervisor监管Supervised的行为
2. **意图-策略博弈**：被监管者生成意图，监管者评估策略
3. **非线性评分**：阈值效应、累积损伤、边际递减、随机波动
4. **底线保护**：防止健康分雪崩，模拟医疗干预
5. **复发机制**：潮汐性行为变化，更接近真实人类
6. **长期模拟**：90天数据收集与趋势分析
7. **环境控制**：手机可用性、厨房可达性等具身干预
8. **多场景支持**：手机成瘾、减肥、糖尿病等预配置场景（含专用地图）
9. **实验矩阵**：9种组合（3初始分 × 3自律程度）自动运行
10. **批处理加速**：~10倍速度提升选项
11. **[新] 情绪评分系统**：追踪被监管者满意度变化
12. **[新] 非对称博弈引擎**：模拟信任建立、耐心消耗、叛逆冲动
13. **[新] Timeline可视化**：按天分组的时间线导航
14. **[新] Agent详情面板**：显示完整角色profile信息
15. **[新] 倍速回放控制**：支持0.5x-4x播放速度

适用于研究健康行为干预策略的有效性与用户体验平衡问题。

---

## 十五、地图添加指南

### 15.1 地图文件结构

每个场景地图需要以下文件：

```
frontend/static/assets/<地图名称>/
├── tilemap/
│   ├── tilemap.json          # Tiled 导出的地图文件（主文件）
│   ├── *.png                  # tileset 图片资源
│   └── *.tsx                  # tileset 定义文件（可选，需嵌入）
├── maze.json                  # 迷宫配置（定义空间地址和碰撞）
├── spatial_tree.json          # 空间树结构（层级地址定义）
└── agents/                    # Agent 资源（可选）
    └── <角色名>/
        ├── agent.json         # Agent 配置
        ├── portrait.png       # 头像
        └── texture.png        # 精灵图
```

### 15.2 tilemap.json 关键配置

**重要**：Phaser.js 不支持外部 tileset 引用，必须使用**嵌入式 tileset**。

❌ **错误方式**（外部引用）：
```json
"tilesets": [
    {
        "firstgid": 1,
        "source": "CuteRPG_Field_B(1).tsx"
    }
]
```

✅ **正确方式**（嵌入式）：
```json
"tilesets": [
    {
        "columns": 16,
        "firstgid": 1,
        "image": "CuteRPG_Field_B (1).png",
        "imageheight": 512,
        "imagewidth": 512,
        "margin": 0,
        "name": "CuteRPG_Field_B(1)",
        "spacing": 0,
        "tilecount": 256,
        "tileheight": 32,
        "tilewidth": 32
    }
]
```

### 15.3 从 Tiled 导出时的注意事项

1. **导出前**：在 Tiled 中选择 `Map` → `Embed Tileset` 嵌入所有外部 tileset
2. **或手动转换**：从 `.tsx` 文件提取属性并嵌入到 `tilemap.json`

**tsx 文件格式参考**：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" tiledversion="1.11.2"
         name="room"
         tilewidth="32"
         tileheight="32"
         tilecount="8284"
         columns="76">
    <image source="Room_Builder_32x32.png" width="2432" height="3488"/>
</tileset>
```

**转换为嵌入格式**：
```json
{
    "columns": 76,
    "firstgid": 257,
    "image": "Room_Builder_32x32.png",
    "imageheight": 3488,
    "imagewidth": 2432,
    "margin": 0,
    "name": "room",
    "spacing": 0,
    "tilecount": 8284,
    "tileheight": 32,
    "tilewidth": 32
}
```

### 15.4 maze.json 配置

```json
{
    "world": "the Ville",           // 世界名称（与 spatial_tree 对应）
    "tile_size": 32,                // 瓦片大小（像素）
    "size": [20, 30],               // [height, width] 注意顺序！
    "map": {
        "asset": "map",
        "tileset_groups": {...},
        "layers": [
            {"name": "1老两口的家", "tileset_group": "group_1"},
            {"name": "2客厅", "tileset_group": "group_1"},
            {"name": "collisions", "tileset_group": "group_1",
             "depth": -1, "collision": {"exclusion": [-1]}}
        ]
    },
    "tiles": [
        {
            "coord": [5, 4],
            "address": ["老两口的家"],
            "collision": true
        },
        {
            "coord": [22, 6],
            "address": ["老两口的家", "卧室", "床"]
        }
    ]
}
```

**层命名规则**：
- `1xxx` - sector（区域，如"老两口的家"）
- `2xxx` - arena（房间，如"客厅"、"卧室"）
- `3xxx` - game_object（物体，如"床"、"冰箱"）
- `collisions` - 碰撞层

### 15.5 spatial_tree.json 配置

定义层级空间结构：

```json
{
    "spatial": {
        "address": {
            "living_area": ["the Ville"]
        },
        "tree": {
            "the Ville": {
                "老两口的家": {
                    "客厅": ["钢琴", "沙发"],
                    "卫生间": ["马桶", "洗漱台"],
                    "卧室": ["床"],
                    "书房": ["笔记本电脑"],
                    "厨房": ["零食柜", "冰箱", "厨房的门", "咖啡机"]
                }
            }
        }
    }
}
```

### 15.6 常见问题排查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `External tilesets unsupported` | tileset 使用外部引用 | 将 tsx 内容嵌入 tilemap.json |
| `Cannot read properties of undefined` | tileset 数据不完整 | 检查所有 tileset 字段是否完整 |
| `No data found for Tileset: xxx` | tileset name 与前端代码不匹配 | 确保 tilemap.json 中的 name 与 main_script_health.html 中 addTilesetImage() 的第一个参数完全一致（注意空格） |
| `Image not found` | 图片路径错误 | 确保 `image` 字段指向同目录下的 png 文件 |
| `Agent无法移动` | 碰撞配置错误 | 检查 maze.json 中的 collision 字段 |
| `地址找不到` | spatial_tree 不匹配 | 确保 maze.json tiles 的 address 与 spatial_tree 一致 |

### 15.7 Tileset 名称匹配要求

**重要**：tilemap.json 中的 tileset `name` 字段必须与前端代码 `addTilesetImage()` 调用中的名称**完全匹配**。

前端代码位置：`frontend/templates/main_script_health.html`

**weight-loss-scene 需要的 tileset 名称**：
```javascript
// main_script_health.html 第 632-638 行
map.addTilesetImage("CuteRPG_Field_B (1)", "CuteRPG_Field_B (1)");
map.addTilesetImage("Room_Builder_32x32", "Room_Builder_32x32");
map.addTilesetImage("interiors_pt1", "interiors_pt1");
map.addTilesetImage("interiors_pt2", "interiors_pt2");
map.addTilesetImage("interiors_pt3 (1)", "interiors_pt3 (1)");
map.addTilesetImage("interiors_pt4", "interiors_pt4");
map.addTilesetImage("interiors_pt5", "interiors_pt5");
```

因此 tilemap.json 中的 tileset name 必须是：
| tileset name | 图片文件 |
|--------------|----------|
| `CuteRPG_Field_B (1)` | CuteRPG_Field_B (1).png |
| `Room_Builder_32x32` | Room_Builder_32x32.png |
| `interiors_pt1` | interiors_pt1.png |
| `interiors_pt2` | interiors_pt2.png |
| `interiors_pt3 (1)` | interiors_pt3 (1).png |
| `interiors_pt4` | interiors_pt4.png |
| `interiors_pt5` | interiors_pt5.png |

**注意空格**：`CuteRPG_Field_B (1)` 和 `interiors_pt3 (1)` 的括号前有空格！

### 15.8 weight-loss-scene 地图示例

当前 `weight-loss-scene` 地图配置：

- **地图尺寸**：30×20 tiles（宽×高）
- **场景**：老两口的家（客厅、卫生间、卧室、书房、厨房）
- **Tilesets**：7个嵌入式 tileset（名称必须与前端匹配）
  - CuteRPG_Field_B (1).png
  - Room_Builder_32x32.png
  - interiors_pt1-5.png

**使用此地图**：
```python
# 在 scenario_config.py 或命令行指定
--scenario weight-loss  # 自动使用 weight-loss-scene 地图
```
