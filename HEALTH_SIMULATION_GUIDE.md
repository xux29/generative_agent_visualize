# 健康管理智能体模拟系统 - 实施指南

## 项目概述

基于 GenerativeAgentsCN（斯坦福小镇）进行重构，实现健康管理智能体模拟系统。**核心特点**：
- ✅ **完全复用**现有的小镇地图和可视化系统（frontend + replay.py）
- ✅ 通过修改 Agent 配置实现三个健康管理场景
- ✅ 实现混合事件驱动的时间引擎（19:00-02:00，45天）
- ✅ 实现策略演化系统（Level 0-3 干预策略）
- ✅ 使用 SiliconFlow API（Qwen2.5-72B + BAAI/bge-m3 embedding）

## 实施状态（所有Phase已完成）

### Phase 1: 配置 SiliconFlow API ✅

**文件**: [data/config_health.json](generative_agents/data/config_health.json)

```json
{
  "agent": {
    "think": {
      "llm": {
        "provider": "openai",
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "base_url": "https://api.siliconflow.cn/v1"
      }
    },
    "associate": {
      "embedding": {
        "provider": "openai",
        "model": "BAAI/bge-m3"
      }
    }
  }
}
```

### Phase 2: 扩展 Timer 类 ✅

**文件**: [modules/utils/timer.py](generative_agents/modules/utils/timer.py)

**新增方法**：
- `jump_to(target_time)`: 直接跳跃到目标时间
- `set_time_of_day(hour, minute, second)`: 设置当天的特定时间

### Phase 3: 创建核心模块 ✅

#### 1. Intention 模块
**文件**: [modules/intention.py](generative_agents/modules/intention.py)

```python
class Intention:
    def __init__(self, activity, duration, compliance_threshold, inner_monologue):
        # activity: "玩手机"、"吃零食"等
        # compliance_threshold: 1=容易屈服, 2=中等, 3=困难
```

#### 2. Strategy 模块
**文件**: [modules/strategy.py](generative_agents/modules/strategy.py)

```python
class Strategy:
    LEVEL_0_OBSERVE = 0    # 观察
    LEVEL_1_PERSUADE = 1   # 劝说
    LEVEL_2_REMOVE = 2     # 移除物品
    LEVEL_3_LOCK = 3       # 锁定空间
```

#### 3. Scorer 模块
**文件**: [modules/scorer.py](generative_agents/modules/scorer.py)

基于医学标准（ADA 2025, 中国糖尿病防治指南 2024）实现三种评分方法：
- `calculate_weight_loss_health_score()`: 减肥场景评分
- `calculate_phone_addiction_health_score()`: 手机成瘾场景评分
- `calculate_diabetes_health_score()`: 糖尿病场景评分

#### 4. HealthAgentMixin 模块
**文件**: [modules/agent_health.py](generative_agents/modules/agent_health.py)

**核心方法**：
- `_init_health_management(config)`: 初始化健康管理属性
- `generate_intention()`: Target 生成行为意图
- `evaluate_strategy()`: Manager 评估策略
- `execute_intervention()`: Manager 执行干预
- `react_to_persuasion()`: Target 对劝说的反应
- `daily_reflection()`: Manager 每日反思

### Phase 4: 评分系统符合医学标准 ✅

**文件**: [modules/scorer.py](generative_agents/modules/scorer.py)

三个场景的评分标准：

| 场景 | 评分维度 | 分值 |
|------|----------|------|
| 减肥 | 夜间进食（3分）+ 进食时间（3分）+ 食物种类（2分）+ 偷吃行为（2分） | 满分10分 |
| 手机成瘾 | 手机使用时长（4分）+ 睡眠时间（3分）+ 卧室手机（3分） | 满分10分 |
| 糖尿病 | 手机使用（3分）+ 进食时间（3分）+ 食物种类（2分）+ 偷吃（2分） | 满分10分 |

### Phase 5: 分析并完全复用现有地图 ✅

**关键文件**: [MAP_REUSE_PLAN.md](MAP_REUSE_PLAN.md)

**地图复用策略**：
- 使用现有 village 地图，无需修改 maze.json
- 通过语义映射将现有位置赋予健康管理场景含义
- 使用 `Maze.lock_area()` 实现物理锁定

**语义映射示例**：
| 原始位置 | 健康场景映射 |
|----------|-------------|
| 玫瑰酒吧:酒吧:厨房水槽 | 厨房（可锁定） |
| 霍布斯咖啡馆:咖啡馆:烹饪区 | 厨房（可锁定） |
| 莫雷诺家族的房子:公共休息室 | 零食区 |

### Phase 6: 配置三个场景 ✅

**配置文件**: [data/semantic_mapping.json](generative_agents/data/semantic_mapping.json)

**场景配置加载器**: [modules/scenario_config.py](generative_agents/modules/scenario_config.py)

#### 场景 A: 减肥（汤姆 & 简）
- Target: 汤姆（肥胖、自律低）
- Manager: 简（妻子）
- 住所: 莫雷诺家族的房子

#### 场景 B: 手机成瘾（亚当 & 山姆）
- Target: 亚当（手机成瘾、自律低）
- Manager: 山姆
- 住所: 亚当的家

#### 场景 C: 糖尿病（克劳斯 & 玛丽亚）
- Target: 克劳斯（糖尿病、自律低）
- Manager: 玛丽亚
- 住所: 奥克山学院宿舍

### Phase 7: 集成到 Agent 类 ✅

**修改的文件**:

1. [modules/agent.py](generative_agents/modules/agent.py)
   - Agent 类继承 HealthAgentMixin
   - 在 `__init__` 中调用 `_init_health_management()`

2. [modules/prompt/scratch.py](generative_agents/modules/prompt/scratch.py)
   - 新增 5 个健康管理 Prompt 方法：
     - `prompt_health_generate_intention()`
     - `prompt_health_evaluate_strategy()`
     - `prompt_health_generate_persuasion()`
     - `prompt_health_react_persuasion()`
     - `prompt_health_daily_reflection()`

3. [data/prompts/](generative_agents/data/prompts/) 新增文件：
   - `health_generate_intention.txt`
   - `health_evaluate_strategy.txt`
   - `health_generate_persuasion.txt`
   - `health_react_persuasion.txt`
   - `health_daily_reflection.txt`

### Phase 8: 实现主循环 ✅

#### 主模拟脚本
**文件**: [start_health_simulation.py](generative_agents/start_health_simulation.py)

```python
class HealthSimulation:
    def run_monitoring_period(self, day):
        """运行一晚的监控周期 (19:00 - 02:00)"""
        # 每30分钟检查一次
        for minute in range(0, 420, 30):
            # 1. Target 生成意图
            intention = self.target_agent.generate_intention()

            # 2. Manager 评估策略
            strategy = self.manager_agent.evaluate_strategy(intention, self.target_agent)

            # 3. 执行干预
            if strategy.level > 0:
                self.manager_agent.execute_intervention(strategy, self.target_agent)
```

#### 可视化模块
**文件**: [visualize_health.py](generative_agents/visualize_health.py)

提供 Web 界面查看模拟结果：
- 场景列表页面
- 健康分趋势图
- 干预策略分布图
- 时间线视图

## 使用指南

### 运行模拟

```bash
cd generative_agents

# 运行减肥场景（45天）
python start_health_simulation.py --scenario weight-loss --days 45

# 运行手机成瘾场景
python start_health_simulation.py --scenario phone-addiction --days 45

# 运行糖尿病场景
python start_health_simulation.py --scenario diabetes --days 45
```

### 查看结果

```bash
# 启动健康数据可视化服务
python visualize_health.py
# 访问 http://127.0.0.1:5001

# 使用原有回放系统（地图可视化）
python replay.py
# 访问 http://127.0.0.1:5000/?name=health-weight-loss&step=0
```

### 输出文件

运行模拟后，结果保存在 `results/health/{scenario_name}/`:

```
results/health/weight-loss/
├── simulation.log          # 模拟日志
├── day_01.json            # 第1天详细记录
├── day_02.json
├── ...
├── day_45.json
├── final_report.json      # 最终报告（JSON）
└── report.md              # 最终报告（Markdown）
```

## 架构总结

```
generative_agents/
├── modules/
│   ├── agent.py              # Agent 类（集成 HealthAgentMixin）
│   ├── agent_health.py       # HealthAgentMixin（健康管理扩展）
│   ├── intention.py          # 意图系统
│   ├── strategy.py           # 策略系统
│   ├── scorer.py             # 评分系统
│   ├── scenario_config.py    # 场景配置加载器
│   ├── maze.py               # Maze 类（添加 lock_area/unlock_area）
│   └── prompt/
│       └── scratch.py        # Prompt 管理（添加健康管理 Prompts）
├── data/
│   ├── config_health.json    # SiliconFlow API 配置
│   ├── semantic_mapping.json # 语义映射配置
│   └── prompts/
│       ├── health_generate_intention.txt
│       ├── health_evaluate_strategy.txt
│       ├── health_generate_persuasion.txt
│       ├── health_react_persuasion.txt
│       └── health_daily_reflection.txt
├── frontend/
│   └── static/assets/village/agents/
│       ├── 汤姆/agent.json   # 添加 monitor 配置
│       ├── 简/agent.json
│       ├── 亚当/agent.json
│       ├── 山姆/agent.json
│       ├── 克劳斯/agent.json
│       └── 玛丽亚/agent.json
├── start_health_simulation.py  # 健康模拟入口
└── visualize_health.py         # 健康数据可视化
```

## 关键设计决策

### 1. Mixin 模式
- 保持向后兼容（原有模拟仍可运行）
- 健康管理功能独立封装
- 易于测试和维护

### 2. 100% 地图复用
- 无需修改 maze.json
- 通过语义映射赋予新含义
- 使用 Tile.collision 实现物理锁定

### 3. 物理锁定机制
- `Maze.lock_area()` 设置 collision=True
- 寻路系统自动避开锁定区域
- 保存原始状态用于解锁

### 4. 混合事件驱动
- 减少 80% 无效循环
- 基于意图触发事件
- 支持延迟干预

## 参考文档

- [MAP_REUSE_PLAN.md](MAP_REUSE_PLAN.md) - 地图复用详细计划
- [SCENARIO_CONFIG_SUMMARY.md](SCENARIO_CONFIG_SUMMARY.md) - 场景配置总结
- [CLAUDE.md](CLAUDE.md) - 代码库架构文档
