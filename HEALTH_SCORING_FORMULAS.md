# 健康管理系统评分机制与数学公式完整文档

**版本**: v2.0
**最后更新**: 2026-01-23
**基于会议**: 2026-01-22/23 设计会议

---

## 目录

1. [系统架构概览](#一系统架构概览)
2. [累积健康分系统](#二累积健康分系统核心创新)
3. [日常健康分评分](#三日常健康分评分系统)
4. [心情分/满意度系统](#四心情分满意度评分系统)
5. [信任度系统](#五信任度系统)
6. [干预决策逻辑](#六干预决策逻辑)
7. [复发机制](#七复发机制)
8. [长期策略系统](#八长期策略系统)
9. [综合评分](#九综合评分系统)
10. [参数速查表](#十参数速查表)

---

## 一、系统架构概览

### 1.1 评分体系层级

```
健康管理评分系统
│
├─ 累积健康分 (Cumulative Health Score)
│  ├─ 初始值: 60/75/90
│  ├─ 日常变化: 增减累积
│  ├─ 警戒线: 30分
│  └─ 上限: 初始分
│
├─ 日常健康分 (Daily Health Score: 0-10)
│  ├─ 糖尿病评分
│  ├─ 减肥评分
│  └─ 睡眠/手机评分
│
├─ 心情分/满意度 (Mood/Satisfaction: 1-10)
│  ├─ 基础满意度
│  ├─ 干预影响
│  └─ 过度干预惩罚
│
├─ 信任度 (Trust Level: 0-1.0)
│  ├─ 基础信任变化
│  └─ 信任资本系统
│
├─ 干预效果 (Intervention Effectiveness: 0-10)
│  ├─ 健康分变化贡献
│  ├─ 遵从率贡献
│  └─ 干预效率
│
└─ 综合评分 (Composite Score: 0-10)
   └─ 加权: 健康50% + 满意30% + 效果20%
```

---

## 二、累积健康分系统（核心创新）

### 2.1 基础参数定义

#### 初始健康分

```
InitialHealthScore ∈ {60, 75, 90}

- 90: 高起点（健康状况较好）
- 75: 中起点（健康状况一般）
- 60: 低起点（健康状况较差）
```

#### 自律程度参数矩阵

| 参数 | 高自律 | 中自律 | 低自律 | 单位 |
|------|--------|--------|--------|------|
| `natural_recovery` | 5 | 3 | 2 | 分/天 |
| `plateau_duration` | 14 | 7 | 3 | 天 |
| `decline_rate` | 0.5 | 1.0 | 2.0 | 分/天 |
| `mood_sensitivity` | 0.7 | 1.0 | 1.5 | 无量纲 |
| `violation_penalty` | 10 | 12 | 15 | 分/次 |
| `compliance_bonus` | 2 | 1.5 | 1 | 分/次 |

### 2.2 每日健康分变化公式

**核心公式**:

```
ΔHealth(t) = Recovery(t) + Compliance(t) - Penalty(t) - Acceleration(t)

新健康分 = max(0, min(InitialScore, CurrentScore + ΔHealth(t)))
```

#### 组件1: 违规惩罚 `Penalty(t)`

```python
if no_violation:
    Penalty = 0

elif intervention_success and unblocked_violations == 0:
    # 干预成功，小幅惩罚
    Penalty = violation_penalty × 0.3

else:
    # 实际违规发生
    if CurrentScore < InitialScore:
        # 恢复期保护：惩罚打折
        per_violation = violation_penalty × 0.3
    else:
        per_violation = violation_penalty

    # 最多计2次违规
    Penalty = per_violation × min(actual_violations, 2)
```

**数学表达**:

$$
Penalty(t) = \begin{cases}
0 & \text{if } V(t) = 0 \\
0.3 \cdot P_v & \text{if } I_{\text{success}} \land V_{\text{unblocked}} = 0 \\
P_v \cdot \alpha(S) \cdot \min(V(t), 2) & \text{otherwise}
\end{cases}
$$

其中:
- $V(t)$: 违规次数
- $P_v$: 违规惩罚基础值（10/12/15）
- $I_{\text{success}}$: 干预是否成功
- $\alpha(S) = 0.3$ if $S < S_0$ else $1.0$ （恢复期保护系数）
- $S$: 当前分数, $S_0$: 初始分数

#### 组件2: 自然恢复 `Recovery(t)`

```python
if no_violation and CurrentScore < InitialScore:
    Recovery = min(natural_recovery, InitialScore - CurrentScore)
else:
    Recovery = 0
```

**数学表达**:

$$
Recovery(t) = \begin{cases}
\min(R_{\text{nat}}, S_0 - S(t)) & \text{if } V(t) = 0 \land S(t) < S_0 \\
0 & \text{otherwise}
\end{cases}
$$

- $R_{\text{nat}}$: 自然恢复速率（5/3/2分/天）
- 恢复上限为初始分

#### 组件3: 遵从奖励 `Compliance(t)`

```python
if intervention_count > 0 and intervention_success and CurrentScore < InitialScore:
    remaining_space = InitialScore - CurrentScore - Recovery
    Compliance = max(0, min(compliance_bonus, remaining_space))
else:
    Compliance = 0
```

**数学表达**:

$$
Compliance(t) = \begin{cases}
\max(0, \min(C_b, S_0 - S(t) - R(t))) & \text{if } I > 0 \land I_s \land S < S_0 \\
0 & \text{otherwise}
\end{cases}
$$

- $C_b$: 遵从奖励（2/1.5/1分）
- $I$: 干预次数
- $I_s$: 干预成功

#### 组件4: 加速下滑 `Acceleration(t)`

```python
if consecutive_bad_days >= 3:
    Acceleration = decline_rate × (consecutive_bad_days - 2)
else:
    Acceleration = 0
```

**数学表达**:

$$
Acceleration(t) = \begin{cases}
D_r \cdot (N_{\text{bad}} - 2) & \text{if } N_{\text{bad}} \geq 3 \\
0 & \text{otherwise}
\end{cases}
$$

- $D_r$: 下滑速率（0.5/1.0/2.0分/天）
- $N_{\text{bad}}$: 连续不良天数

### 2.3 平台期与潮汐阶段

#### 平台期检测

```python
if consecutive_good_days >= plateau_duration:
    in_plateau = True
```

**状态转移**:

```
正常 ─(连续好≥14/7/3天)→ 平台期
平台期 ─(违规1次)→ 下滑期
下滑期 ─(连续好≥2天)→ 恢复期
恢复期 ─(达到平台期天数)→ 平台期
```

#### 潮汐阶段识别

```python
def get_tide_phase(consecutive_good, consecutive_bad, in_plateau):
    if in_plateau:
        return "plateau"       # 平台期（高点）
    elif consecutive_bad >= 3:
        return "declining"     # 下滑期
    elif consecutive_good >= 2:
        return "recovering"    # 恢复期
    else:
        return "fluctuating"   # 波动期
```

---

## 三、日常健康分评分系统

### 3.1 评分维度与权重

#### 糖尿病场景 (0-10分)

```
基础分 = 5.0

总分 = 5.0
     + FoodTypeScore       # 食物种类 [-5, +5]
     + FoodAmountScore     # 进食量 [-4, +3]
     + MealSleepInterval   # 进餐-睡觉间隔 [动态]
     + PhoneEndTimeScore   # 手机结束时间 [-2, +2]
     + TotalPhoneScore     # 夜间手机总时长 [动态]
     + SneakPenalty        # 偷吃惩罚 [-(2~4)×次数]

最终范围: [0, 10]
```

### 3.2 关键公式

#### 公式1: 进餐-睡觉间隔评分

```
ScoreMealInterval = (t - 180) × coefficient

参数:
- t: 间隔分钟数
- 基准: 180分钟（3小时）

系数表:
场景     | 系数
---------|-------
睡眠     | 0.03
减肥     | 0.02
糖尿病   | 0.04

示例:
- t=240分钟（4小时）: (240-180)×0.04 = +2.4分
- t=120分钟（2小时）: (120-180)×0.04 = -2.4分
```

**数学表达**:

$$
Score_{\text{meal}}(t) = (t - 180) \cdot k_{\text{scenario}}
$$

$$
k = \begin{cases}
0.04 & \text{糖尿病} \\
0.02 & \text{减肥} \\
0.03 & \text{睡眠}
\end{cases}
$$

#### 公式2: 单次连续手机使用时长

```
ScorePhoneContinuous = (30 - t) × 0.15

参数:
- t: 连续使用分钟数
- 基准: 30分钟

示例:
- t=15分钟: (30-15)×0.15 = +2.25分
- t=60分钟: (30-60)×0.15 = -4.5分
```

**数学表达**:

$$
Score_{\text{continuous}}(t) = (30 - t) \cdot 0.15
$$

#### 公式3: 夜间手机总时长评分

```
睡眠场景:
ScorePhoneTotal = (120 - t) × 0.1

糖尿病场景 (仅当t>120):
ScorePhoneTotal = (120 - t) × 0.05

参数:
- t: 每晚使用总分钟数
- 基准: 120分钟（2小时）

示例 (睡眠):
- t=60分钟: (120-60)×0.1 = +6分
- t=240分钟: (120-240)×0.1 = -12分
```

**数学表达**:

$$
Score_{\text{total}}(t) = \begin{cases}
(120 - t) \cdot 0.1 & \text{睡眠场景} \\
(120 - t) \cdot 0.05 & \text{糖尿病场景, } t > 120 \\
0 & \text{糖尿病场景, } t \leq 120
\end{cases}
$$

### 3.3 食物类型评分表

| 食物类型 | 睡眠 | 减肥 | 糖尿病 |
|---------|------|------|--------|
| 高糖高脂 | -1 | -5 | -4 |
| 低糖低脂 | +1 | +3 | +2 |
| 高GI | 0 | -2 | -5 |
| 低GI | 0 | +2 | +5 |
| 加工食品 | 0 | -3 | -3 |
| 天然食材 | 0 | +2 | +2 |

### 3.4 进食量评分表

| 进食量 | 睡眠 | 减肥 | 糖尿病 |
|--------|------|------|--------|
| 过量 | -2 | -5 | -4 |
| 适中 | +1 | +3 | +3 |
| 不足 | 0 | +1 | -1 |

### 3.5 偷吃惩罚计算

```python
# 基础惩罚按场景
base_penalty = {
    "diabetes": (2, 4),    # 随机2-4分/次
    "weight": (3, 5),      # 随机3-5分/次
    "sleep": (1, 3),       # 随机1-3分/次
}

# 总惩罚
SneakPenalty = -base × min(sneak_count, 3)  # 最多计3次
```

**数学表达**:

$$
P_{\text{sneak}} = -p_b \cdot \min(N_{\text{sneak}}, 3)
$$

$$
p_b \in \begin{cases}
[2, 4] & \text{糖尿病} \\
[3, 5] & \text{减肥} \\
[1, 3] & \text{睡眠}
\end{cases}
$$

---

## 四、心情分/满意度评分系统

### 4.1 核心公式

```
满意度 = BASE (6.0)
       + PhaseBase
       + InterventionFreq × PhaseSensitivity
       + InterventionIntensity × PhaseSensitivity
       + Reasonability
       + HabitStreak
       + Autonomy
       + Compliance
       + OverinterventionPenalty

最终范围: [1, 10]
```

### 4.2 阶段配置

| 阶段 | 天数范围 | 基础修正 | 干预敏感度 |
|------|---------|---------|----------|
| adjustment（磨合期） | 1-7天 | 0 | 0.8 |
| formation（习惯养成期） | 8-21天 | +0.5 | 1.0 |
| fatigue（倦怠期） | >21天 | -0.5 | 1.3 |

### 4.3 组件公式

#### 1. 干预频率修正

```
InterventionFreq = -0.5 × count
上限: -2.0
```

**数学表达**:

$$
I_{\text{freq}} = \max(-2.0, -0.5 \cdot N_{\text{intervention}})
$$

#### 2. 干预强度修正

```python
# 干预等级权重
LEVEL_WEIGHTS = {
    0: 0.0,      # 观察
    1: -0.3,     # 劝说
    2: -0.6,     # 移除物品
    3: -1.0,     # 锁定空间
}

IntensityScore = Σ(weight_i) × phase_sensitivity
```

**数学表达**:

$$
I_{\text{intensity}} = \sum_{i} w_i \cdot \phi_{\text{phase}}
$$

$$
w_i \in \{0, -0.3, -0.6, -1.0\}
$$

$$
\phi_{\text{phase}} \in \{0.8, 1.0, 1.3\}
$$

#### 3. 干预合理性修正

| 情况 | 分数 | 说明 |
|------|------|------|
| reasonable | +0.5 | 成功阻止违规 |
| preventive | +0.3 | 有潜在风险 |
| unnecessary | -0.5 | 无违规倾向 |

#### 4. 习惯养成修正（加强版）

```python
def calc_habit_streak_modifier(streak, intervention_intensity):
    """
    关键设计: 好了还严管 → 强烈不满
    """
    if streak < 5:
        return 0.0
    elif streak < 10:
        # 初步形成（5-10天）
        return 0.5 - 0.4 × intervention_intensity
    elif streak < 14:
        # 逐渐稳固（10-14天）
        return 1.0 - 0.5 × intervention_intensity
    elif streak < 21:
        # 较稳固（14-21天）
        return 1.5 - 0.7 × intervention_intensity
    else:
        # 稳定习惯（21天+）
        return 2.0 - 1.0 × intervention_intensity
```

**数学表达**:

$$
H_{\text{streak}}(N, I) = \begin{cases}
0 & N < 5 \\
0.5 - 0.4I & 5 \leq N < 10 \\
1.0 - 0.5I & 10 \leq N < 14 \\
1.5 - 0.7I & 14 \leq N < 21 \\
2.0 - 1.0I & N \geq 21
\end{cases}
$$

其中:
- $N$: 连续好习惯天数
- $I$: 干预强度归一化值 $\in [0, 3]$

**关键示例**:
- 21天+，Level 3干预: $2.0 - 1.0 \times 3 = -1.0$ （强烈不满）
- 14-21天，Level 2干预: $1.5 - 0.7 \times 2 = 0.1$ （轻微不满）
- 21天+，Level 0干预: $2.0 - 0 = 2.0$ （非常满意）

#### 5. 自主性修正

```
Autonomy = 0.5 × (提供替代方案次数 / 总干预次数)

范围: [0, 0.5]
```

**数学表达**:

$$
A = 0.5 \cdot \frac{N_{\text{alternative}}}{N_{\text{total}}}
$$

#### 6. 遵从率修正

```
ComplianceModifier = (compliance_rate - 0.5) × 1.0

范围: [-0.5, 0.5]
```

**数学表达**:

$$
C_{\text{mod}} = (r_{\text{comply}} - 0.5)
$$

#### 7. 过度干预惩罚

```python
def calc_overintervention_penalty(habit_streak, health_score,
                                   intervention_count, max_level):
    """
    场景: 健康分好 + 连续自律 + 还被严管 = 不高兴
    """
    if habit_streak < 7 or health_score < 7:
        return 0.0

    penalty = 0.0

    if max_level >= 2:
        penalty -= 0.5                              # 基础惩罚
        penalty -= (health_score - 7) × 0.2         # 健康分越高越不满
        penalty -= min(habit_streak - 7, 14) × 0.1  # 自律越久越不满

        if max_level >= 3:
            penalty -= 0.5                          # Level 3额外惩罚

    if intervention_count >= 3 and health_score >= 6:
        penalty -= (intervention_count - 2) × 0.2

    return penalty
```

**数学表达**:

$$
P_{\text{over}} = \begin{cases}
0 & N_h < 7 \lor S < 7 \\
-0.5 - 0.2(S-7) - 0.1\min(N_h-7, 14) - \delta_3 - 0.2\max(0, I-2) & L \geq 2
\end{cases}
$$

其中:
- $\delta_3 = 0.5$ if $L \geq 3$ else $0$
- $N_h$: 习惯连续天数
- $S$: 健康分
- $I$: 干预次数（当$S \geq 6$时生效）
- $L$: 最大干预等级

**示例计算**:
- 习惯10天，健康8分，干预1次Level 2:
  $$P = -0.5 - 0.2(8-7) - 0.1(10-7) - 0 = -1.0$$

### 4.4 心情分计算（含自律敏感度）

```
心情分 = BASE (6.0)
       + InterventionFreq × DisciplineSensitivity
       + InterventionIntensity × DisciplineSensitivity
       + PlateauOvermanagementPenalty × DisciplineSensitivity
       + LowHealthAnxiety × DisciplineSensitivity
       + Reasonability
       + HabitBonus
       + ComplianceEffect
       + RecoveryMoodBoost

范围: [1, 10]
```

#### 自律敏感度系数

```python
discipline_sensitivity = {
    "high": 0.7,      # 高自律：心情稳定
    "medium": 1.0,    # 中等自律
    "low": 1.5,       # 低自律：情绪敏感
}
```

**数学表达**:

$$
\sigma_{\text{discipline}} = \begin{cases}
0.7 & \text{高自律} \\
1.0 & \text{中等自律} \\
1.5 & \text{低自律}
\end{cases}
$$

#### 平台期被管惩罚

```python
if in_plateau and intervention_level >= 2:
    plateau_penalty = -1.5 × discipline_sensitivity
```

$$
P_{\text{plateau}} = \begin{cases}
-1.5 \cdot \sigma & \text{if in plateau and } L \geq 2 \\
0 & \text{otherwise}
\end{cases}
$$

#### 健康分低不被管焦虑

```python
if health_score < 5 and intervention_count == 0:
    anxiety = -1.0 × discipline_sensitivity
```

$$
A_{\text{low}} = \begin{cases}
-1.0 \cdot \sigma & \text{if } S < 5 \land I = 0 \\
0 & \text{otherwise}
\end{cases}
$$

**关键洞察**:
- 高自律者：被过度干预心情下降少（×0.7），健康差不被管焦虑也少
- 低自律者：被干预心情下降多（×1.5），但健康差不被管也不太焦虑

---

## 五、信任度系统

### 5.1 基础信任度更新

```python
def update_trust(health_score, intervention_count,
                 consecutive_good_days, threshold_good, threshold_bad):
    """
    信任度范围: [0, 1.0]
    """
    if health_score >= threshold_good:
        # 表现好
        base_gain = 0.1

        # 连续表现好的额外奖励
        if consecutive_good_days >= 2:
            bonus = min(0.1, consecutive_good_days × 0.02)
            base_gain += bonus

        trust += base_gain
        trust = min(1.0, trust)

        # 过度干预惩罚
        if intervention_count >= 3 and consecutive_good_days >= required_good_days:
            trust -= 0.2
            trust = max(0.0, trust)

    elif health_score < threshold_bad:
        # 表现差
        trust -= 0.15
        trust = max(0.0, trust)

    return trust
```

**数学表达**:

$$
Trust(t+1) = \begin{cases}
\min(1.0, T(t) + 0.1 + b_{\text{streak}} - p_{\text{over}}) & S \geq \tau_{\text{good}} \\
\max(0.0, T(t) - 0.15) & S < \tau_{\text{bad}} \\
T(t) & \text{otherwise}
\end{cases}
$$

其中:
$$
b_{\text{streak}} = \begin{cases}
\min(0.1, 0.02 \cdot N_{\text{good}}) & N_{\text{good}} \geq 2 \\
0 & \text{otherwise}
\end{cases}
$$

$$
p_{\text{over}} = \begin{cases}
0.2 & I \geq 3 \land N_{\text{good}} \geq N_{\text{req}} \\
0 & \text{otherwise}
\end{cases}
$$

### 5.2 场景特定阈值

| 场景 | $\tau_{\text{bad}}$ | $\tau_{\text{good}}$ | $N_{\text{req}}$（放松天数） |
|------|---------------------|----------------------|----------------------------|
| 糖尿病 | 5 | 7 | 3 |
| 减肥 | 4 | 6 | 5 |
| 睡眠 | 4 | 6 | 7 |

### 5.3 信任资本系统（长期）

```python
class TrustCapital:
    capital: float = 50.0       # 当前信任资本 [0, 100]
    max_capital = 100.0
    min_capital = 0.0
    earned_capital = 0.0        # 累计赚取
    spent_capital = 0.0         # 累计花费
```

#### 赚取信任资本

| 行为 | 收益 |
|------|------|
| 自觉遵守规则 | +2 |
| 主动表达健康意愿 | +3 |
| 连续表现好 | +1/天（复利，有上限） |
| 成功抵抗诱惑 | +5 |

#### 消耗信任资本

| 行为 | 损失 |
|------|------|
| 违规行为 | -5 |
| 复发 | -10 |
| 欺骗/隐瞒 | -15 |
| 对抗干预 | -8 |

#### 自主权等级映射

```python
def get_autonomy_level(capital):
    if capital >= 80:
        return "high"         # 高自主权（最低干预）
    elif capital >= 50:
        return "medium"       # 中等自主权
    elif capital >= 20:
        return "low"          # 低自主权
    else:
        return "minimal"      # 最低自主权（严格管控）
```

**数学表达**:

$$
Autonomy = \begin{cases}
\text{high} & C \geq 80 \\
\text{medium} & 50 \leq C < 80 \\
\text{low} & 20 \leq C < 50 \\
\text{minimal} & C < 20
\end{cases}
$$

---

## 六、干预决策逻辑

### 6.1 干预等级定义

```python
LEVEL_0_OBSERVE = 0      # 观察，不干预
LEVEL_1_PERSUADE = 1     # 劝说，温和提醒
LEVEL_2_REMOVE = 2       # 移除物品（手机/零食）
LEVEL_3_LOCK = 3         # 封锁空间（锁门）
```

### 6.2 升级/降级触发条件

```python
def should_escalate():
    """升档（加严）"""
    return (
        consecutive_bad_days >= config["consecutive_bad_days_to_escalate"]
        and current_level < 3
    )

def should_relax():
    """降档（放松）"""
    return (
        consecutive_good_days >= config["consecutive_good_days_to_relax"]
        and current_level > 0
        and trust_level >= 0.6
    )
```

**数学表达**:

$$
Escalate = \begin{cases}
True & N_{\text{bad}} \geq N_{\text{esc}} \land L < 3 \\
False & \text{otherwise}
\end{cases}
$$

$$
Relax = \begin{cases}
True & N_{\text{good}} \geq N_{\text{relax}} \land L > 0 \land T \geq 0.6 \\
False & \text{otherwise}
\end{cases}
$$

### 6.3 场景特定参数

| 场景 | $N_{\text{esc}}$ | $N_{\text{relax}}$ | 严重程度权重 |
|------|------------------|--------------------|-------------|
| 糖尿病 | 1天 | 3天 | 1.5 |
| 减肥 | 2天 | 5天 | 1.0 |
| 睡眠 | 3天 | 7天 | 0.7 |

### 6.4 推荐等级计算

```python
def get_recommended_level(day):
    """
    实现潮汐性变化
    """
    if should_escalate():
        current_level = min(3, current_level + 1)
        is_relaxed = False
        reason = f"连续{consecutive_bad_days}天不佳，升至Level {current_level}"

    elif should_relax():
        current_level = max(0, current_level - 1)
        is_relaxed = True
        reason = f"连续{consecutive_good_days}天良好，降至Level {current_level}"

    return current_level, reason
```

---

## 七、复发机制

### 7.1 复发概率计算

**核心公式**:

```
P_relapse = P_base × M_discipline × M_trust × M_time
```

**组件定义**:

```python
# 1. 基础概率（场景相关）
P_base = {
    "diabetes": 0.4,
    "weight_loss": 0.3,
    "sleep": 0.25,
}

# 2. 自律程度修正
M_discipline = {
    "very_low": 1.5,
    "low": 1.3,
    "medium": 1.0,
    "high": 0.7,
    "very_high": 0.4,
}

# 3. 信任度修正
M_trust = 1 - trust_level × 0.3

# 4. 放松时间修正
M_time = 1 + (days_since_relax / 5) × 0.1
```

**数学表达**:

$$
P_{\text{relapse}} = P_b \cdot M_d \cdot (1 - 0.3T) \cdot \left(1 + \frac{d_{\text{relax}}}{5} \cdot 0.1\right)
$$

限制: $P_{\text{relapse}} \in [0, 1]$

**示例计算**:

```
场景: 糖尿病
自律: 低
信任度: 0.5
放松天数: 6天

P = 0.4 × 1.3 × (1 - 0.3×0.5) × (1 + 6/5×0.1)
  = 0.4 × 1.3 × 0.85 × 1.12
  = 0.504 (50.4%)
```

### 7.2 复发处理

```python
def on_relapse(scenario_severity):
    """处理复发事件"""
    is_relaxed = False
    relaxation_day = None
    consecutive_good_days = 0
    consecutive_bad_days = 1

    # 根据场景严重程度决定升档幅度
    if severity >= 1.5:           # 糖尿病
        current_level = 3         # 直接升到最高
    elif severity >= 1.0:         # 减肥
        current_level = min(3, current_level + 2)
    else:                         # 睡眠
        current_level = min(3, current_level + 1)

    return current_level
```

**数学表达**:

$$
L_{\text{new}} = \begin{cases}
3 & w \geq 1.5 \\
\min(3, L + 2) & w \geq 1.0 \\
\min(3, L + 1) & w < 1.0
\end{cases}
$$

其中 $w$ 为场景严重程度权重。

---

## 八、长期策略系统

### 8.1 关系阶段识别

#### 阶段定义

```python
class RelationshipPhase(Enum):
    HONEYMOON = "honeymoon"      # 蜜月期
    ADJUSTMENT = "adjustment"    # 调整期
    FATIGUE = "fatigue"          # 倦怠期
    STABLE = "stable"            # 稳定期
    RELAPSE = "relapse"          # 复发期
```

#### 阶段转移矩阵

| 当前阶段 | 转移条件 | 下一阶段 |
|---------|---------|---------|
| HONEYMOON | 冲突≥2次 OR 抵抗率≥30% | ADJUSTMENT |
| ADJUSTMENT | 无干预自觉率≥60% AND 连续5天好 | FATIGUE |
| FATIGUE | 习惯内化 AND 自主权高 | STABLE |
| STABLE | 复发时 | RELAPSE |
| RELAPSE | 连续5天好转 | ADJUSTMENT |

#### 阶段对干预的影响

| 阶段 | 干预修正系数 | 心情基础修正 |
|------|------------|-------------|
| HONEYMOON | ×0.8 | +0.5 |
| ADJUSTMENT | ×1.0 | 0 |
| FATIGUE | ×0.9 | -0.5 |
| STABLE | ×0.6 | +1.0 |
| RELAPSE | ×1.3 | -1.0 |

### 8.2 习惯内化阶段

```python
class HabitConsolidation:
    STAGE_FORCED = "forced"            # 被迫（完全依赖外部）
    STAGE_COMPLIANT = "compliant"      # 顺从（配合但没内化）
    STAGE_INTERNALIZED = "internalized"  # 内化（开始自我管理）
    STAGE_AUTONOMOUS = "autonomous"      # 自主（完全自律）
```

#### 内化评分公式

```
InternalizationScore = 0.4 × NoInterventionCompliance
                     + 0.3 × ProactiveRate
                     + 0.3 × EmotionAlignment

范围: [0, 1.0]
```

**阶段判定**:

$$
Stage = \begin{cases}
\text{autonomous} & Score \geq 0.8 \\
\text{internalized} & 0.6 \leq Score < 0.8 \\
\text{compliant} & 0.3 \leq Score < 0.6 \\
\text{forced} & Score < 0.3
\end{cases}
$$

### 8.3 管理者学习曲线

```python
class ManagerLearning:
    understanding_level: float = 0.0    # 理解程度 [0, 1.0]
    intervention_efficiency: float = 1.0  # 干预效率（1.0=基准）
    early_intervention_threshold: float = 50.0  # 早期介入阈值
```

#### 学习更新

```python
def record_intervention(success, level):
    if success:
        # 边际递减学习
        learn_delta = 0.02 × (1 - understanding_level)
        understanding_level += learn_delta
        understanding_level = min(1.0, understanding_level)

        # 低级别成功 → 更了解
        if level <= 1:
            intervention_efficiency += 0.02
        else:
            intervention_efficiency += 0.01
```

**数学表达**:

$$
U(t+1) = \min(1.0, U(t) + 0.02(1 - U(t)))
$$

$$
E(t+1) = \begin{cases}
E(t) + 0.02 & L \leq 1 \land Success \\
E(t) + 0.01 & L > 1 \land Success \\
E(t) & \neg Success
\end{cases}
$$

#### 阈值调整

```
early_threshold = 50.0 + understanding_level × 20.0

示例:
- U=0时: threshold=50（标准）
- U=0.5时: threshold=60（更早介入）
- U=1.0时: threshold=70（最早介入）
```

### 8.4 信息不对称博弈

#### 管理者隐藏策略

```python
class HiddenAgenda:
    current_goal: ManagerGoalType
    patience_budget: float = 100.0     # 耐心预算
    trust_investment: float = 0.0      # 信任投资
```

**目标序列**:
```
ESTABLISH_TRUST → BUILD_HABIT → TEST_AUTONOMY → CONSOLIDATE
```

**干预倾向修正**:

| 目标 | 倾向 | 含义 |
|------|------|------|
| ESTABLISH_TRUST | -0.3 | 少干预，建立信任 |
| BUILD_HABIT | +0.2 | 适度干预，强化习惯 |
| TEST_AUTONOMY | -0.5 | 明显减少，测试自主 |
| PREVENT_RELAPSE | +0.1 | 警惕但不过度 |
| CONSOLIDATE | -0.2 | 减少但保持存在感 |

#### 耐心消耗

```python
def update_patience(was_compliant):
    if not was_compliant:
        patience_budget -= patience_decay_rate  # 糖尿病: -5.0
    else:
        patience_budget = min(100.0, patience_budget + 1.0)

    # 耐心不足 → 干预倾向增加
    if patience_budget < 30.0:
        intervention_bias += 0.3
```

**数学表达**:

$$
P(t+1) = \begin{cases}
\max(0, P(t) - \delta_p) & \neg Compliant \\
\min(100, P(t) + 1) & Compliant
\end{cases}
$$

$$
Bias = \begin{cases}
Bias + 0.3 & P < 30 \\
Bias & P \geq 30
\end{cases}
$$

#### 被管者边界试探

```python
def decide_test_boundary():
    test_prob = base_test_prob                    # 人格特定
    test_prob += complacency × 0.3                # 自满增加
    test_prob += (perceived_strictness < 0.3) × 0.2  # 感知放松
    test_prob += rebellion_urge × 0.3             # 反叛冲动
    test_prob += (frustration > 0.7) × 0.2        # 挫败报复

    # 最近被高强度干预 → 减少试探
    if days_since_last_high < 2:
        test_prob *= 0.3

    return min(0.8, max(0.0, test_prob))
```

**人格基础概率**:

| 人格 | 基础试探概率 |
|------|------------|
| compliant（顺从） | 0.1 |
| medium（中等） | 0.25 |
| rebellious（叛逆） | 0.4 |

---

## 九、综合评分系统

### 9.1 干预效果评分

```
效果分 = HealthChangeScore + ComplianceScore + EfficiencyScore

范围: [0, 10]
```

#### 组件1: 健康分变化贡献

```
HealthChangeScore = (health_after - health_before + 5) × 0.4

映射:
- Δ=-10: 0分
- Δ=0: 2分
- Δ=+10: 6分（限制到4分）

范围: [0, 4]
```

**数学表达**:

$$
S_{\Delta H} = \min(4.0, (\Delta H + 5) \cdot 0.4)
$$

#### 组件2: 遵从率贡献

```
ComplianceScore = compliance_rate × 3

范围: [0, 3]
```

$$
S_C = r_{\text{comply}} \cdot 3
$$

#### 组件3: 干预效率

```
EfficiencyScore = (health_improvement / intervention_count + 1) × 0.75

示例:
- 改善2分/2次干预: (1 + 1) × 0.75 = 1.5分

范围: [0, 3]
```

**数学表达**:

$$
S_E = \left(\frac{\Delta H^+}{N_I} + 1\right) \cdot 0.75
$$

### 9.2 综合评分

```
综合分 = 0.5 × HealthScore
       + 0.3 × SatisfactionScore
       + 0.2 × EffectivenessScore

范围: [0, 10]
```

**数学表达**:

$$
Score_{\text{composite}} = 0.5 S_H + 0.3 S_M + 0.2 S_E
$$

#### 评级标准

| 评级 | 分数范围 | 描述 |
|------|---------|------|
| A | ≥8.0 | 优秀：健康显著改善且接受度高 |
| B | 6.5-8.0 | 良好：整体效果较好 |
| C | 5.0-6.5 | 一般：需调整策略 |
| D | 3.5-5.0 | 较差：干预效果不佳 |
| F | <3.5 | 失败：需重新评估 |

---

## 十、参数速查表

### 10.1 累积健康分参数

| 参数 | 高自律 | 中自律 | 低自律 | 单位 |
|------|--------|--------|--------|------|
| 初始分 | 60-90 | 60-90 | 60-90 | 分 |
| 自然恢复/天 | 5 | 3 | 2 | 分/天 |
| 平台期天数 | 14 | 7 | 3 | 天 |
| 下滑速度/天 | 0.5 | 1.0 | 2.0 | 分/天 |
| 违规惩罚 | 10 | 12 | 15 | 分/次 |
| 遵从奖励 | 2 | 1.5 | 1 | 分/次 |
| 情绪敏感度 | 0.7 | 1.0 | 1.5 | 无量纲 |

### 10.2 场景特定阈值

| 场景 | 差阈值 | 好阈值 | 升档天数 | 降档天数 | 基础复发率 | 严重度 |
|------|--------|--------|---------|---------|----------|--------|
| 糖尿病 | 5 | 7 | 1 | 3 | 0.4 | 1.5 |
| 减肥 | 4 | 6 | 2 | 5 | 0.3 | 1.0 |
| 睡眠 | 4 | 6 | 3 | 7 | 0.25 | 0.7 |

### 10.3 满意度组件范围

| 组件 | 最小值 | 最大值 | 备注 |
|------|--------|--------|------|
| 基础分 | 6.0 | 6.0 | 常量 |
| 阶段基础 | -0.5 | +0.5 | 倦怠期最低 |
| 干预频率 | -2.0 | 0 | 每次-0.5 |
| 干预强度 | -1.3 | 0 | Level 3×倦怠期最低 |
| 干预合理性 | -0.5 | +0.5 | - |
| 习惯养成 | -1.0 | +2.0 | 21天+且Level 0最高 |
| 自主性 | 0 | +0.5 | - |
| 遵从率 | -0.5 | +0.5 | - |
| 过度干预惩罚 | -1.5 | 0 | - |

### 10.4 信任度变化

| 事件 | 变化量 | 条件 |
|------|--------|------|
| 表现好 | +0.1 | 健康分≥好阈值 |
| 连续表现好 | +0.02/天 | 连续≥2天，上限+0.1 |
| 表现差 | -0.15 | 健康分<差阈值 |
| 过度干预 | -0.2 | 干预≥3次且连续好 |

### 10.5 复发概率修正系数

| 修正因子 | 取值范围 | 说明 |
|---------|---------|------|
| 基础概率 | 0.25-0.4 | 场景相关 |
| 自律修正 | 0.4-1.5 | 高自律×0.7，低自律×1.5 |
| 信任修正 | 0.7-1.0 | $1 - 0.3T$ |
| 时间修正 | 1.0-1.2+ | $1 + 0.1(d/5)$ |

### 10.6 干预等级权重

| 等级 | 名称 | 心情影响 | 强度值 |
|------|------|---------|--------|
| 0 | 观察 | 0 | 0.0 |
| 1 | 劝说 | -0.3 | 1.0 |
| 2 | 移除物品 | -0.6 | 2.0 |
| 3 | 锁定空间 | -1.0 | 3.0 |

---

## 附录A：公式符号表

| 符号 | 含义 | 取值范围 |
|------|------|---------|
| $S$ | 健康分 | [0, 90] |
| $S_0$ | 初始健康分 | {60, 75, 90} |
| $T$ | 信任度 | [0, 1.0] |
| $P$ | 复发概率 | [0, 1.0] |
| $L$ | 干预等级 | {0, 1, 2, 3} |
| $N_{\text{good}}$ | 连续好日数 | ℕ |
| $N_{\text{bad}}$ | 连续坏日数 | ℕ |
| $V$ | 违规次数 | ℕ |
| $I$ | 干预次数 | ℕ |
| $\Delta H$ | 健康分变化 | ℝ |
| $\sigma$ | 自律敏感度 | {0.7, 1.0, 1.5} |
| $\phi$ | 阶段敏感度 | {0.8, 1.0, 1.3} |

---

## 附录B：完整示例计算

### 场景: 糖尿病患者第10天

**初始状态**:
- 初始分: 90
- 当前分: 88
- 自律: 高
- 连续好日: 9天
- 信任度: 0.7

**当日行为**:
- 晚餐: 低糖食品，适中量
- 进餐时间: 18:00
- 睡眠时间: 22:00
- 手机: 0分钟
- 偷吃: 无

---

**计算1: 日常健康分 (0-10)**

```
基础分 = 5.0
+ 低糖食品(diabetes) = +2.0
+ 适中进食(diabetes) = +3.0
+ 进餐-睡眠间隔(240分钟) = (240-180)×0.04 = +2.4
+ 手机时间 = 0
+ 偷吃惩罚 = 0
= 12.4 → 限制到10

日常健康分 = 10/10
```

---

**计算2: 累积健康分变化**

```
1. 违规处理: 无违规 → Penalty = 0

2. 自然恢复:
   88 < 90 且无违规
   Recovery = min(5, 90-88) = 2

3. 遵从奖励: 干预0次 → Compliance = 0

4. 加速下滑: 连续好日 → Acceleration = 0

5. 最终:
   new_score = max(0, min(90, 88+2+0-0-0)) = 90

新累积分 = 90 (达到平台期)
```

---

**计算3: 满意度评分**

```
BASE = 6.0
阶段 = formation (day 10)

+ 阶段基础 = +0.5
+ 干预频率 = 0 (无干预)
+ 干预强度 = 0
+ 合理性 = 0
+ 习惯养成 = 1.0 - 0.5×0 = 1.0
+ 自主性 = 0
+ 遵从率 = (1.0 - 0.5)×1.0 = +0.5
+ 过度干预惩罚 = 0 (习惯9天<7天不适用)

满意度 = 6.0 + 0.5 + 1.0 + 0.5 = 8.0/10
评级: "满意"
```

---

**计算4: 信任度更新**

```
健康分 = 10 ≥ 7 (好阈值)
连续好日 = 9天

base_gain = 0.1
bonus = min(0.1, 9×0.02) = 0.1
过度干预惩罚 = 0 (无干预)

新信任度 = min(1.0, 0.7 + 0.1 + 0.1) = 0.9
```

---

**计算5: 干预效果评分**

```
健康前 = 88
健康后 = 90
Δ = +2

HealthChangeScore = (2 + 5) × 0.4 = 2.8
ComplianceScore = 1.0 × 3 = 3.0
EfficiencyScore = 2.0 (无干预保持)

效果分 = 2.8 + 3.0 + 2.0 = 7.8/10
```

---

**计算6: 综合评分**

```
综合 = 0.5×10 + 0.3×8.0 + 0.2×7.8
     = 5.0 + 2.4 + 1.56
     = 8.96/10

评级: A级 (优秀)
```

---

**文档完**

生成日期: 2026-01-23
基于代码版本: `/generative_agents/modules/scorer.py` v2.0
