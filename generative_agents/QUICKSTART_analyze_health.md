# 快速入门：健康模拟统计分析

## 5分钟快速开始

### 第1步：列出所有可用的模拟运行
```bash
python analyze_health.py --list
```

### 第2步：分析你感兴趣的场景
```bash
# 分析体重减轻场景的最新运行
python analyze_health.py --scenario weight-loss

# 或分析糖尿病管理
python analyze_health.py --scenario diabetes

# 同时分析多个场景
python analyze_health.py --scenario diabetes weight-loss phone-addiction
```

### 第3步：查看生成的 CSV 文件
```bash
# 详细指标 (每天一行，90天的数据)
results/csv/health_analysis_{scenario}_{run}_{timestamp}.csv

# 综合摘要报告
results/csv/health_analysis_summary_{timestamp}.csv
```

## 输出 CSV 中的关键列

| 列名 | 含义 | 范围 |
|------|------|------|
| `day` | 第几天 | 1-90 |
| `health_score` | 累积健康分 | 0-100 |
| `health_change` | 每日变化 | 任意 |
| `emotion_score` | 情绪分 | 0-10 |
| `satisfaction` | 满意度 | 任意 |
| `intervention_count` | 干预次数 | ≥0 |
| `max_intervention_level` | 最高干预级别 | 0-3 |
| `intervention_success_rate` | 干预成功率 | 0-100% |
| `violation_count` | 违规次数 | ≥0 |
| `strategy_phase` | 策略阶段 | honeymoon/plateau/... |
| `turnaround_count` | 折返次数 | ≥0 |

## 常见用途

### 用途1：观察健康分曲线
在 Excel/Pandas 中绘制 `day` vs `health_score` 图表，查看：
- 初期衰减速度
- 干预后的恢复
- 长期趋势

### 用途2：评估干预效果
对比：
- `intervention_success_rate` - 干预有多有效
- `avg_intervention_level` - 需要多强的干预
- `violation_count` vs `intervention_count` - 干预次数少不少

### 用途3：分析行为模式
查看：
- `snacking_count` - 吃零食多少次
- `phone_duration_minutes` - 玩手机多久
- `turnaround_count` - 试图进入禁区多少次

### 用途4：对比不同配置
用综合摘要报告 (`health_analysis_summary_*.csv`) 对比：
- 不同初始健康分 (60/75/90) 的效果
- 不同自律程度 (high/medium/low) 的行为
- 不同场景 (diabetes/weight-loss/phone-addiction) 的管理难度

## 命令示例

```bash
# 例1: 分析所有糖尿病运行并对比
python analyze_health.py --scenario diabetes
# 结果: 18个详细CSV + 1个汇总CSV

# 例2: 分析特定运行
python analyze_health.py --scenario weight-loss --run init75_medium_20260320_120241
# 结果: 1个详细CSV + 1个汇总CSV

# 例3: 批量分析所有可用场景
python analyze_health.py --scenario diabetes weight-loss phone-addiction
# 结果: 19个详细CSV + 1个汇总CSV

# 例4: 使用自定义输出目录
python analyze_health.py --scenario weight-loss --output-dir my_analysis
# 结果: my_analysis/health_analysis_*.csv
```

## 文件位置

```
生成的 CSV 文件:
  results/csv/health_analysis_*.csv

模拟原始数据:
  results/health/{scenario}/{run_name}/complete_results.json
```

## 下一步

详细文档请阅读 [README_analyze_health.md](README_analyze_health.md)

支持的所有指标列表、高级用法、数据解释等。

---

**提示**: 用 Excel、Pandas、Tableau 等工具打开 CSV 文件进行进一步分析和可视化！
