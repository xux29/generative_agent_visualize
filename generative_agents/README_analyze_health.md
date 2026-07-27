# 健康模拟统计分析工具 (analyze_health.py)

## 概述

`analyze_health.py` 是一个专门为健康管理模拟系统设计的统计分析工具，用于从完整的模拟结果中**提取和分析各种关键指标**，并将其导出为 CSV 格式的数据文件。

## 主要功能

### 支持的指标

该工具能够提取并导出以下所有指标：

#### 1. 基本信息
- **日期** - 模拟的日期
- **天数** - 第几天

#### 2. 健康相关指标
- **健康分** - 累积健康分 (0-100)
- **健康分变化** - 每日健康分的变化值
- **健康分状态** - 当前健康状况 (紧急/危险/预警/正常/安全)

#### 3. 情绪与满意度
- **情绪分** - 管理者的情绪/满意度评分
- **满意度** - 被管理者的满意度评分  
- **心情** - 当前心情 (normal/happy/frustrated/resigned)

#### 4. 干预相关指标
- **干预次数** - 当天干预的总次数
- **最大干预级别** - 当天最高干预级别 (0=观察, 1=劝说, 2=环境干预, 3=锁定区域)
- **平均干预级别** - 干预级别的平均值
- **成功干预次数** - 成功的干预次数
- **干预成功率(%)** - 干预成功的百分比
- **干预类型** - 干预类型统计 (如 persuade:3, lock_kitchen:1)

#### 5. 不良行为记录
- **违规次数** - 当天的违规总次数
- **不良行为次数** - 不良行为的总次数
- **零食次数** - 吃零食的记录次数
- **手机使用时长(分钟)** - 睡前玩手机的时长

#### 6. 策略管理指标
- **策略级别** - 当前策略执行级别
- **策略阶段** - 当前所在的策略阶段 (honeymoon/plateau/escalation/recovery等)
- **信任资本** - 管理者与被管理者之间的信任资本
- **声誉分数** - 管理者的声誉评分
- **习惯阶段** - 习惯形成阶段 (awareness/formation/internalization)

#### 7. 事件统计
- **事件总数** - 当天记录的事件总数
- **折返次数** - 被管理者试图进入被禁区域但被阻止的次数
- **关键洞察** - AI反思产生的关键洞察

## 使用方法

### 基础用法

#### 1. 列出所有可用的场景和运行
```bash
python analyze_health.py --list
```

输出示例：
```
Available Scenarios and Runs:
  diabetes:
    • init90_high_20260321_134447 (2026-03-21 18:19:47)
    • init75_medium_20260320_120241 (2026-03-20 12:28:29)
    • ...

  weight-loss:
    • init75_medium_20260320_120241 (2026-03-20 12:28:29)
```

#### 2. 分析特定场景的最新运行
```bash
python analyze_health.py --scenario weight-loss
```

#### 3. 分析多个场景
```bash
python analyze_health.py --scenario diabetes weight-loss phone-addiction
```

#### 4. 分析特定的运行
```bash
python analyze_health.py --scenario weight-loss --run init75_medium_20260320_120241
```

### 高级选项

```bash
# 指定输入目录（默认: results/health）
python analyze_health.py --scenario weight-loss --results-dir results/health

# 指定输出目录（默认: results/csv）
python analyze_health.py --scenario weight-loss --output-dir results/csv
```

## 输出文件

### 每个运行的详细指标 CSV

**文件名格式**: `health_analysis_{scenario}_{run}_{timestamp}.csv`

包含每一天的详细指标，90行表示90天的模拟内容。

**示例** (前三行数据):
```
day,date,health_score,health_change,emotion_score,satisfaction,mood,...
1,2026-03-20,70.06,0,3.4,0,normal,...
2,2026-03-21,62.05,-8.01,1.8,0,normal,...
3,2026-03-22,57.4,-4.65,3.0,0,normal,...
```

### 综合摘要报告

**文件名**: `health_analysis_summary_{timestamp}.csv`

对所有分析的运行进行汇总，包含：
- scenario - 场景名称
- run - 运行名称
- days - 模拟天数
- initial_health - 初始健康分
- final_health - 最终健康分
- avg_health - 平均健康分
- health_trend - 健康趋势 (up/down/stable)
- total_interventions - 总干预次数
- avg_intervention_level - 平均干预级别
- total_violations - 总违规次数
- total_turnarounds - 总折返次数
- avg_satisfaction - 平均满意度

示例：
```
scenario,run,days,initial_health,final_health,avg_health,health_trend,...
diabetes,init90_high_20260321_134447,90,16.18,0,0.18,down,...
weight-loss,init75_medium_20260320_120241,45,70.06,0,16.02,down,...
```

## 数据来源

工具从以下位置读取数据：
- **输入**: `results/health/{scenario}/{run_name}/complete_results.json`
- **输出**: `results/csv/health_analysis_*.csv`

## 工作流示例

### 流程 1: 快速查看最新模拟结果

```bash
# 列出所有可用的运行
python analyze_health.py --list

# 分析糖尿病场景的最新运行
python analyze_health.py --scenario diabetes

# 打开生成的CSV文件查看
# results/csv/health_analysis_diabetes_init90_high_20260321_134447_*.csv
```

### 流程 2: 批量分析多个场景和指标对比

```bash
# 分析所有场景
python analyze_health.py --scenario diabetes weight-loss phone-addiction

# 查看综合摘要报告
# results/csv/health_analysis_summary_*.csv

# 用Excel或其他工具对比不同场景的表现
```

### 流程 3: 特定运行的深度分析

```bash
# 分析特定的运行
python analyze_health.py --scenario weight-loss --run init75_medium_20260320_120241

# 查看详细的日报告 CSV
# 包含 90 行数据，可用于：
# - 绘制健康分曲线图
# - 分析干预效果
# - 研究情绪变化规律
```

## 关键指标解释

### 健康分曲线
- 初始分数：初始健康状况 (60/75/90)
- 下降趋势：表示不良行为产生了负面影响
- 上升恢复：表示管理者的干预生效了

### 干预级别
```
0 = 观察 (Observe) - 无干预
1 = 劝说 (Persuade) - 语言劝导
2 = 环境干预 (Remove) - 移除诱惑物品
3 = 锁定区域 (Lock) - 锁定访问权限
```

### 策略阶段
- **honeymoon** (蜜月期) - 初期，秩序良好
- **plateau** (平台期) - 稳定期，行为已习惯化
- **escalation** (升级期) - 问题恶化，需要提升干预
- **recovery** (恢复期) - 干预后的恢复阶段

### 健康区间 (相对的健康状态)
- **安全** (90-100) - 非常好，生理缓冲充足
- **正常** (70-89) - 良好，基线状态
- **预警** (50-69) - 缓冲减少，敏感度上升
- **危险** (30-49) - 接近极限，微小违规可能崩溃
- **紧急** (0-29) - 严重受损，需要医疗干预

## 数据分析建议

### 1. 健康分变化分析
- 比较不同初始健康分的衰减速度
- 观察干预的效果大小
- 识别"V形下降"模式

### 2. 干预效率评估
- 干预成功率：成功率高表示策略有效
- 平均干预级别：较低表示管理者更有技能或被管理者更配合
- 干预次数与健康改善的相关性

### 3. 行为模式识别
- 折返次数：表示被禁区域的吸引力
- 违规频率：表示自制力
- 满意度变化：表示被管理者的接受度

### 4. 策略阶段分析
- 不同初始分的人进入各阶段的速度
- 不同自律程度的人的策略演进
- 信任资本的积累与消耗

## 技术细节

### 数据提取
- 从 `complete_results.json` 读取 `daily_data` 数组
- 对每一天的数据进行结构化处理
- 处理不同运行之间可能存在的数据格式差异

### 文件格式
- **输入**: JSON 格式的完整模拟结果
- **输出**: UTF-8 编码的 CSV 文件（带 BOM）

### 性能
- 每个运行的分析通常耗时 1-2 秒
- 批量分析 20+ 个运行耗时约 1-2 分钟

## 故障排除

### 问题: 找不到场景
```bash
# 解决: 先列出可用的场景
python analyze_health.py --list
```

### 问题: 某些指标值为 0
这是正常的，表示该天没有相应的事件或行为发生。例如：
- `intervention_count=0` 表示该天未进行干预
- `violation_count=0` 表示该天无违规行为

### 问题: CSV 文件为空
检查 `complete_results.json` 是否存在且包含 `daily_data` 字段。

## 扩展功能

未来可以添加的功能：
1. 生成 Excel 报告（包含图表）
2. 统计显著性检验
3. 时间序列预测
4. 相关性热力图
5. 自定义指标计算

## 相关工具

- `compress_health.py` - 压缩模拟数据用于回放
- `replay_health.py` - 可视化回放模拟过程
- `generate_charts.py` - 生成可视化图表
- `start_health_simulation.py` - 运行健康模拟

## 命令速查

```bash
# 列出所有可用的场景
python analyze_health.py --list

# 快速分析最新结果
python analyze_health.py --scenario weight-loss

# 分析所有场景
python analyze_health.py

# 分析特定运行
python analyze_health.py --scenario diabetes --run init90_high_20260321_134447

# 自定义输出目录
python analyze_health.py --scenario weight-loss --output-dir my_results/csv
```

## 数据示例

### 健康分下降的一天 (Day 2)
```
day,2026-03-21
health_score,62.05      # 从初始 70.06 下降到 62.05
health_change,-8.01     # 下降了 8.01 分
emotion_score,1.8       # 情绪也下降了
mood,normal             # 但心情保持正常

intervention_count,4    # 进行了 4 次干预
max_intervention_level,3  # 升到最高的锁定级别
intervention_success_rate,75.0  # 75% 的干预成功

violation_count,4       # 发生了 4 次违规
snacking_count,0        # 但未成功吃到零食（被干预了）
```

---

**最后更新**: 2026-03-23  
**版本**: 1.0
