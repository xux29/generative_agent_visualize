# 健康模拟可视化方案（回放模式）

## 问题诊断

经过代码分析，发现健康版（`start_health_simulation.py`）**无法正确可视化的根本原因**：

| 问题 | 原因 | 代码位置 |
|------|------|----------|
| Agent 坐标全是 [0,0] | 夜间循环中**从未调用 `agent.move()`** | `simulate_one_night()` |
| checkpoint 无移动数据 | `save_realtime_checkpoint()` 保存的坐标不变 | 第 791-793 行 |
| 无法计算路径 | 没有源坐标和目标坐标的变化 | - |
| **⚠️ Step 编号被覆盖** | `step = 0` 每晚重置，导致后续天数覆盖之前的 checkpoint | 第 478 行 |

### Step 覆盖问题详解

**现象**：5 天模拟后只有 14 个 step 文件，且时间顺序混乱：
- step_0000-0007: Day 4-5（最后写入，覆盖了之前的）
- step_0008-0010: Day 3
- step_0011-0013: Day 1（最早写入）

**根本原因**（第 478 行）：
```python
step = 0  # 每晚都重置为 0！
```

每天模拟开始时 `step` 重置，导致 `step_0000.json` 被重复覆盖。

## 方案概述

创建**独立的健康版回放系统**，不修改原有的 `compress.py` 和 `replay.py`：

| 新增文件 | 功能 |
|----------|------|
| `compress_health.py` | 处理健康版日志，生成 `movement_health.json` |
| `replay_health.py` | 健康版回放服务（端口 5002） |
| `frontend/templates/index_health.html` | 健康版前端，显示健康数据+干预时间线 |

同时需要修改 `start_health_simulation.py` 使 Agent 坐标能正确更新。

---

## 修改文件列表

| 文件 | 操作 | 说明 |
|------|------|------|
| `start_health_simulation.py` | 修改 | 添加 Agent 移动逻辑 + 修复坐标保存 |
| `compress_health.py` | **新建** | 健康版数据压缩脚本 |
| `replay_health.py` | **新建** | 健康版回放服务 |
| `frontend/templates/index_health.html` | **新建** | 健康版前端模板 |

---

## 详细实现

### 1. 修改 `start_health_simulation.py`

#### 1.1 修复 Step 计数器覆盖问题（优先级：高）

**位置**：`simulate_days()` 函数（第 21-109 行）和 `simulate_one_night()` 函数

**修改方案**：将 `step` 变量从 `simulate_one_night()` 提升到 `simulate_days()`，作为参数传递并返回。

**修改 `simulate_days()`**：
```python
def simulate_days(game: Game, scenario_name: str, num_days: int = 45, sim_name: str = None):
    # ... 现有代码 ...

    # 全局步数计数器
    global_step = 0

    # 天数循环
    for day in range(1, num_days + 1):
        # ... 现有代码 ...

        # 模拟一个夜晚，传入并更新 step 计数器
        global_step = simulate_one_night(game, day, scenario_name, realtime_checkpoint_dir, global_step)

        # ... 现有代码 ...
```

**修改 `simulate_one_night()` 函数签名**：
```python
def simulate_one_night(game: Game, day: int, scenario_name: str,
                       realtime_checkpoint_dir: Path = None,
                       start_step: int = 0) -> int:
    """
    返回值: 模拟结束后的步数
    """
    # ...
    step = start_step  # 使用传入的起始步数，而非重置为 0
    # ...
    return step  # 返回最终步数
```

#### 1.2 添加 Agent 移动逻辑

**位置**：`simulate_one_night()` 函数

**新增函数**：
```python
# 在 Phase 4 (完成意图) 之前添加 Agent 移动逻辑
def update_agent_positions(game, intentions):
    """根据意图/行为更新 Agent 位置"""
    for name, agent in game.agents.items():
        intention = intentions.get(name)
        if intention:
            # 根据意图活动找到对应地点
            address = agent.spatial.find_address(intention.activity, as_list=True)
        else:
            # 无意图时使用当前计划
            plan, _ = agent.schedule.current_plan()
            address = agent.spatial.find_address(plan["describe"], as_list=True)

        if address:
            tiles = agent.maze.get_address_tiles(address)
            if tiles:
                target_coord = random.choice(list(tiles))
                if agent.coord != target_coord:
                    agent.move(target_coord)
```

**修改 `save_realtime_checkpoint()`**：

```python
# 确保读取正确的坐标
coord = agent.coord if agent.coord else [0, 0]  # 而非 agent.scratch.curr_tile
```

**修改 `execute_intervention()`**：

```python
def execute_intervention(manager, strategy, target, game):
    # Manager 移动到 Target 位置（体现具身性）
    if manager.coord != target.coord:
        path = manager.maze.find_path(manager.coord, target.coord)
        if path:
            manager.move(target.coord)

    # ... 原有干预逻辑 ...
```

---

### 2. 新建 `compress_health.py`

**功能**：读取健康版 checkpoint，生成 `movement_health.json`

**数据格式**：

```json
{
  "start_datetime": "2024-02-13T19:00:00",
  "stride": 10,
  "scene": "home",
  "persona_init_pos": {"妈妈": [17, 14], "女儿": [19, 16]},
  "all_movement": {
    "0": {
      "妈妈": {
        "movement": [17, 14],
        "location": "家，爸爸妈妈的卧室",
        "action": "观察女儿",
        "health_data": null
      },
      "女儿": {
        "movement": [19, 16],
        "location": "家，子女的卧室",
        "action": "玩手机",
        "health_data": {
          "mood": "normal",
          "phone_duration": 30,
          "phone_available": true
        }
      }
    },
    "interventions": {
      "20240213-22:30": {
        "manager": "妈妈",
        "target": "女儿",
        "strategy_level": 2,
        "action": "remove_phone",
        "reason": "深夜仍在玩手机"
      }
    },
    "daily_summary": {
      "day_1": {
        "女儿": {"health_score": 5, "satisfaction_score": 7},
        "妈妈": {"interventions_count": 2}
      }
    }
  }
}
```

---

### 3. 新建 `replay_health.py`

**功能**：Flask 服务，端口 5002

**路由**：
- `GET /` → 渲染 `index_health.html`
- `GET /api/movement` → 返回 `movement_health.json` 数据

---

### 4. 新建 `frontend/templates/index_health.html`

**扩展内容**（相比原版 `index.html`）：

1. **健康数据面板**：
   - 被监管者：心情状态、手机使用时长、厨房可达性、健康分
   - 监管者：今日干预次数

2. **干预时间线**：
   - 左侧时间轴显示干预事件
   - 点击可跳转到对应时间点

3. **每日汇总**：
   - 底部显示每日健康分和满意度趋势图

**UI 布局示意**：

```
┌─────────────────────────────────────────────────────────────┐
│  [地图区域 - Phaser 游戏画面]                                │
├─────────────────────────────────────────────────────────────┤
│  [Agent 列表] 妈妈 | 女儿 | 爸爸                            │
├───────────────────────┬─────────────────────────────────────┤
│  干预时间线           │  当前 Agent 详情                    │
│  ├ 22:30 收走手机     │  女儿                               │
│  ├ 23:00 劝说         │  心情：😐 正常                       │
│  └ 23:45 锁厨房       │  手机时长：45分钟                    │
│                       │  健康分：+5                          │
├───────────────────────┴─────────────────────────────────────┤
│  [每日健康分趋势图]  Day1: +5  Day2: +10  Day3: -5  ...     │
└─────────────────────────────────────────────────────────────┘
```

---

## 数据流

```
start_health_simulation.py (模拟)
    ↓ 每步保存
results/checkpoints/{name}/step_XXXX.json (含正确坐标)
results/daily_saves/{name}/day_XX.json (每日详细数据)
    ↓
compress_health.py (数据压缩)
    ├→ 读取所有 step_XXXX.json
    ├→ 读取 day_XX.json (健康分、满意度)
    ├→ 计算路径 (Maze.find_path)
    └→ 生成 movement_health.json
results/compressed/{name}/movement_health.json
    ↓
replay_health.py (回放服务，端口 5002)
    ↓
index_health.html (前端渲染)
    ├→ Phaser 渲染 Agent 移动
    ├→ 显示健康数据面板
    ├→ 显示干预时间线
    └→ 显示每日趋势图
```

---

## 使用方式

```bash
# 1. 运行健康模拟（会生成 checkpoint）
python start_health_simulation.py --scene home --days 5 --name my-health-sim

# 2. 压缩数据（生成 movement_health.json）
python compress_health.py --name my-health-sim

# 3. 启动回放服务
python replay_health.py

# 4. 浏览器访问
http://127.0.0.1:5002/?name=my-health-sim
```

---

## 验证方法

1. **检查 Step 时间顺序**（修复后必须验证）：
   ```bash
   for f in results/checkpoints/{name}/step_*.json; do
     echo "=== $f ==="; jq '{step: .step, time: .time}' "$f"
   done
   ```
   - 确认 step 编号递增时，time 也递增
   - 5 天模拟应产生约 30-50 个 step 文件（而非被覆盖后的 14 个）

2. **检查坐标更新**：
   - 查看 `results/checkpoints/{name}/step_0001.json` 和 `step_0010.json`
   - 确认不同 step 的 `coord` 值有变化（不全是 `[0, 0]`）

3. **检查压缩数据**：
   - 查看 `results/compressed/{name}/movement_health.json`
   - 确认 `all_movement` 中有移动路径

4. **前端验证**：
   - 访问回放页面，观察 Agent 在地图上移动
   - 确认健康数据面板正确显示
   - 确认干预时间线可点击跳转

---

## 文件位置汇总

| 文件 | 路径 |
|------|------|
| 模拟脚本 | `generative_agents/start_health_simulation.py` |
| 压缩脚本 | `generative_agents/compress_health.py`（新建） |
| 回放服务 | `generative_agents/replay_health.py`（新建） |
| 前端模板 | `generative_agents/frontend/templates/index_health.html`（新建） |
| checkpoint | `generative_agents/results/checkpoints/{name}/` |
| 每日数据 | `generative_agents/results/daily_saves/{name}/` |
| 压缩数据 | `generative_agents/results/compressed/{name}/` |
