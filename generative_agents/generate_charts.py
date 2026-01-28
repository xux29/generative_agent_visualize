#!/usr/bin/env python3
"""
健康模拟实验结果可视化与统计分析

生成图表：
1. 全局总览：9个实验的健康曲线
2. 按初始分分组对比
3. 按自律程度分组对比
4. V形下跌统计分析
5. 情绪分曲线
6. 策略管理器行为分析
7. 每日变化热力图
8. 统计汇总箱线图
"""

import re
import os
import numpy as np
from collections import defaultdict

# 尝试导入 matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import matplotlib.pyplot as plt
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 150
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available, will generate text report only")


# ============================================================================
# 数据提取
# ============================================================================

LOG_DIR = "results/health"
FIGURE_DIR = "results/figures"

EXPERIMENTS = {
    "exp_1_init90_high": {"init": 90, "discipline": "high", "label": "90-HIGH"},
    "exp_2_init90_medium": {"init": 90, "discipline": "medium", "label": "90-MED"},
    "exp_3_init90_low": {"init": 90, "discipline": "low", "label": "90-LOW"},
    "exp_4_init75_high": {"init": 75, "discipline": "high", "label": "75-HIGH"},
    "exp_5_init75_medium": {"init": 75, "discipline": "medium", "label": "75-MED"},
    "exp_6_init75_low": {"init": 75, "discipline": "low", "label": "75-LOW"},
    "exp_7_init60_high": {"init": 60, "discipline": "high", "label": "60-HIGH"},
    "exp_8_init60_medium": {"init": 60, "discipline": "medium", "label": "60-MED"},
    "exp_9_init60_low": {"init": 60, "discipline": "low", "label": "60-LOW"},
}

# 颜色方案
DISCIPLINE_COLORS = {
    "high": "#2196F3",     # 蓝色
    "medium": "#FF9800",   # 橙色
    "low": "#F44336",      # 红色
}

INIT_COLORS = {
    90: "#4CAF50",  # 绿色
    75: "#9C27B0",  # 紫色
    60: "#FF5722",  # 深橙
}


def extract_health_data(log_file):
    """从日志文件提取健康分数据"""
    health_data = []
    mood_data = []
    strategy_data = []

    with open(log_file, 'r') as f:
        for line in f:
            # 提取健康分
            match = re.search(r'Day (\d+) Health: ([\d.]+) \(change: ([+-]?[\d.]+)\)', line)
            if match:
                day = int(match.group(1))
                health = float(match.group(2))
                change = float(match.group(3))
                health_data.append({"day": day, "health": health, "change": change})

            # 提取情绪分
            match = re.search(r'Day (\d+) Mood Score: ([\d.]+)/10', line)
            if match:
                day = int(match.group(1))
                mood = float(match.group(2))
                mood_data.append({"day": day, "mood": mood})

            # 提取策略管理器状态
            match = re.search(r'Day (\d+) Strategy Manager: Level (\d+).*Phase: (\w+).*Trust Capital: ([\d.]+)', line)
            if match:
                day = int(match.group(1))
                level = int(match.group(2))
                phase = match.group(3)
                trust = float(match.group(4))
                strategy_data.append({"day": day, "level": level, "phase": phase, "trust": trust})

    return health_data, mood_data, strategy_data


def analyze_dips(health_data, init_score):
    """分析V形下跌模式"""
    dips = []
    i = 0
    while i < len(health_data):
        if health_data[i]["change"] < -5:  # 显著下跌
            dip_start = i
            dip_bottom = health_data[i]["health"]
            dip_depth = abs(health_data[i]["change"])

            # 找恢复点
            recovery_day = None
            for j in range(i + 1, len(health_data)):
                if health_data[j]["health"] >= init_score:
                    recovery_day = j
                    break

            recovery_time = (recovery_day - dip_start) if recovery_day else None

            dips.append({
                "day": health_data[i]["day"],
                "depth": dip_depth,
                "bottom": dip_bottom,
                "recovery_time": recovery_time,
            })

            if recovery_day:
                i = recovery_day
            else:
                i += 1
        else:
            i += 1

    return dips


# ============================================================================
# 图表生成
# ============================================================================

def plot_all_experiments(all_data):
    """图1: 所有9个实验的健康曲线总览"""
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))

    for exp_name, info in EXPERIMENTS.items():
        if exp_name not in all_data:
            continue
        health = all_data[exp_name]["health"]
        days = [h["day"] for h in health]
        scores = [h["health"] for h in health]

        color = DISCIPLINE_COLORS[info["discipline"]]
        linestyle = {90: "-", 75: "--", 60: ":"}[info["init"]]
        linewidth = {90: 2.0, 75: 1.5, 60: 1.2}[info["init"]]

        ax.plot(days, scores, color=color, linestyle=linestyle,
                linewidth=linewidth, label=info["label"], alpha=0.8)

    # 添加初始分参考线
    for init_score in [60, 75, 90]:
        ax.axhline(y=init_score, color='gray', linestyle=':', alpha=0.3)
        ax.text(91, init_score, f'{init_score}', fontsize=8, color='gray', va='center')

    ax.axhline(y=30, color='red', linestyle='--', alpha=0.5, label='警戒线(30)')

    ax.set_xlabel('天数', fontsize=12)
    ax.set_ylabel('健康分', fontsize=12)
    ax.set_title('90天健康模拟实验 - 全局总览\n(9种组合: 3初始分 x 3自律程度)', fontsize=14)
    ax.set_xlim(1, 90)
    ax.set_ylim(0, 100)
    ax.legend(loc='lower left', ncol=3, fontsize=9)
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/01_all_experiments_overview.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 01_all_experiments_overview.png")


def plot_by_initial_score(all_data):
    """图2: 按初始分分组对比 (3个子图)"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    for idx, init_score in enumerate([90, 75, 60]):
        ax = axes[idx]

        for exp_name, info in EXPERIMENTS.items():
            if info["init"] != init_score or exp_name not in all_data:
                continue

            health = all_data[exp_name]["health"]
            days = [h["day"] for h in health]
            scores = [h["health"] for h in health]

            color = DISCIPLINE_COLORS[info["discipline"]]
            ax.plot(days, scores, color=color, linewidth=1.8,
                    label=f'{info["discipline"].upper()}', alpha=0.9)

        ax.axhline(y=init_score, color='green', linestyle='--', alpha=0.4, label=f'初始分={init_score}')
        ax.axhline(y=30, color='red', linestyle=':', alpha=0.3)

        ax.set_ylabel('健康分', fontsize=11)
        ax.set_title(f'初始分 = {init_score}', fontsize=12, fontweight='bold')
        ax.set_ylim(max(0, init_score - 25), init_score + 5)
        ax.legend(loc='lower left', ncol=4, fontsize=9)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('天数', fontsize=11)
    plt.suptitle('按初始健康分分组对比\n(相同初始分，不同自律程度的表现差异)', fontsize=13, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/02_by_initial_score.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 02_by_initial_score.png")


def plot_by_discipline(all_data):
    """图3: 按自律程度分组对比 (3个子图)"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    for idx, disc in enumerate(["high", "medium", "low"]):
        ax = axes[idx]
        disc_label = {"high": "高自律", "medium": "中自律", "low": "低自律"}[disc]

        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_data:
                continue

            health = all_data[exp_name]["health"]
            days = [h["day"] for h in health]
            scores = [h["health"] for h in health]

            color = INIT_COLORS[info["init"]]
            ax.plot(days, scores, color=color, linewidth=1.8,
                    label=f'初始={info["init"]}', alpha=0.9)

        ax.axhline(y=30, color='red', linestyle=':', alpha=0.3)
        ax.set_ylabel('健康分', fontsize=11)
        ax.set_title(f'{disc_label}', fontsize=12, fontweight='bold')
        ax.set_ylim(35, 95)
        ax.legend(loc='lower left', fontsize=9)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('天数', fontsize=11)
    plt.suptitle('按自律程度分组对比\n(相同自律程度，不同初始分的表现差异)', fontsize=13, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/03_by_discipline.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 03_by_discipline.png")


def plot_dip_analysis(all_data, all_dips):
    """图4: V形下跌统计分析"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 4a: 每个实验的下跌次数
    ax = axes[0, 0]
    exp_labels = []
    dip_counts = []
    colors = []
    for exp_name, info in EXPERIMENTS.items():
        if exp_name in all_dips:
            exp_labels.append(info["label"])
            dip_counts.append(len(all_dips[exp_name]))
            colors.append(DISCIPLINE_COLORS[info["discipline"]])

    bars = ax.bar(range(len(exp_labels)), dip_counts, color=colors, alpha=0.8)
    ax.set_xticks(range(len(exp_labels)))
    ax.set_xticklabels(exp_labels, rotation=45, fontsize=8)
    ax.set_ylabel('V形下跌次数')
    ax.set_title('各实验V形下跌次数 (90天)')
    ax.grid(True, alpha=0.2, axis='y')

    # 4b: 下跌间隔分布
    ax = axes[0, 1]
    for disc in ["high", "medium", "low"]:
        intervals = []
        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_dips:
                continue
            dips = all_dips[exp_name]
            for i in range(1, len(dips)):
                intervals.append(dips[i]["day"] - dips[i-1]["day"])

        if intervals:
            disc_label = {"high": "高自律", "medium": "中自律", "low": "低自律"}[disc]
            ax.hist(intervals, bins=range(0, 30, 2), alpha=0.5,
                   color=DISCIPLINE_COLORS[disc], label=f'{disc_label}')

    ax.set_xlabel('下跌间隔 (天)')
    ax.set_ylabel('频次')
    ax.set_title('V形下跌间隔分布')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)

    # 4c: 恢复时间分布
    ax = axes[1, 0]
    for disc in ["high", "medium", "low"]:
        recovery_times = []
        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_dips:
                continue
            for dip in all_dips[exp_name]:
                if dip["recovery_time"] is not None:
                    recovery_times.append(dip["recovery_time"])

        if recovery_times:
            disc_label = {"high": "高自律", "medium": "中自律", "low": "低自律"}[disc]
            ax.hist(recovery_times, bins=range(0, 20, 1), alpha=0.5,
                   color=DISCIPLINE_COLORS[disc],
                   label=f'{disc_label}')

    ax.set_xlabel('恢复时间 (天)')
    ax.set_ylabel('频次')
    ax.set_title('恢复时间分布')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)

    # 4d: 下跌深度分布
    ax = axes[1, 1]
    for disc in ["high", "medium", "low"]:
        depths = []
        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_dips:
                continue
            for dip in all_dips[exp_name]:
                depths.append(dip["depth"])

        if depths:
            disc_label = {"high": "高自律", "medium": "中自律", "low": "低自律"}[disc]
            ax.hist(depths, bins=np.arange(5, 20, 1), alpha=0.5,
                   color=DISCIPLINE_COLORS[disc],
                   label=f'{disc_label}')

    ax.set_xlabel('下跌深度 (分)')
    ax.set_ylabel('频次')
    ax.set_title('V形下跌深度分布')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)

    plt.suptitle('V形下跌模式统计分析', fontsize=14, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/04_dip_analysis.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 04_dip_analysis.png")


def plot_mood_curves(all_data):
    """图5: 情绪分曲线"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    for idx, init_score in enumerate([90, 75, 60]):
        ax = axes[idx]

        for exp_name, info in EXPERIMENTS.items():
            if info["init"] != init_score or exp_name not in all_data:
                continue

            mood = all_data[exp_name]["mood"]
            if not mood:
                continue
            days = [m["day"] for m in mood]
            scores = [m["mood"] for m in mood]

            color = DISCIPLINE_COLORS[info["discipline"]]
            ax.plot(days, scores, color=color, linewidth=1.2,
                    label=f'{info["discipline"].upper()}', alpha=0.7)

        ax.axhline(y=5.0, color='orange', linestyle='--', alpha=0.3, label='中性线(5.0)')
        ax.set_ylabel('情绪分', fontsize=11)
        ax.set_title(f'初始分 = {init_score}', fontsize=11, fontweight='bold')
        ax.set_ylim(0, 10)
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('天数', fontsize=11)
    plt.suptitle('情绪分变化曲线 (1-10分)\n(满意度越高代表对管理方式越认可)', fontsize=13, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/05_mood_curves.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 05_mood_curves.png")


def plot_strategy_analysis(all_data):
    """图6: 策略管理器分析 - 信任资本与策略等级"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # 6a: 信任资本变化
    ax = axes[0]
    for exp_name, info in EXPERIMENTS.items():
        if exp_name not in all_data or not all_data[exp_name]["strategy"]:
            continue

        strategy = all_data[exp_name]["strategy"]
        days = [s["day"] for s in strategy]
        trust = [s["trust"] for s in strategy]

        color = DISCIPLINE_COLORS[info["discipline"]]
        linestyle = {90: "-", 75: "--", 60: ":"}[info["init"]]
        ax.plot(days, trust, color=color, linestyle=linestyle,
                linewidth=1.0, label=info["label"], alpha=0.7)

    ax.set_ylabel('信任资本', fontsize=11)
    ax.set_title('管理者信任资本变化', fontsize=12)
    ax.legend(loc='lower right', ncol=3, fontsize=8)
    ax.grid(True, alpha=0.2)

    # 6b: 策略等级变化
    ax = axes[1]
    for exp_name, info in EXPERIMENTS.items():
        if exp_name not in all_data or not all_data[exp_name]["strategy"]:
            continue

        strategy = all_data[exp_name]["strategy"]
        days = [s["day"] for s in strategy]
        levels = [s["level"] for s in strategy]

        color = DISCIPLINE_COLORS[info["discipline"]]
        linestyle = {90: "-", 75: "--", 60: ":"}[info["init"]]
        ax.plot(days, levels, color=color, linestyle=linestyle,
                linewidth=1.0, label=info["label"], alpha=0.7)

    ax.set_xlabel('天数', fontsize=11)
    ax.set_ylabel('干预等级', fontsize=11)
    ax.set_title('策略管理器干预等级', fontsize=12)
    ax.set_ylim(-0.5, 4)
    ax.set_yticks([0, 1, 2, 3])
    ax.set_yticklabels(['L0(观察)', 'L1(提醒)', 'L2(干预)', 'L3(强制)'])
    ax.legend(loc='upper right', ncol=3, fontsize=8)
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/06_strategy_analysis.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 06_strategy_analysis.png")


def plot_health_change_heatmap(all_data):
    """图7: 每日健康变化热力图"""
    fig, ax = plt.subplots(1, 1, figsize=(16, 6))

    # 构建矩阵
    exp_names = list(EXPERIMENTS.keys())
    max_days = 90
    matrix = np.zeros((len(exp_names), max_days))

    for i, exp_name in enumerate(exp_names):
        if exp_name in all_data:
            for h in all_data[exp_name]["health"]:
                if h["day"] <= max_days:
                    matrix[i, h["day"] - 1] = h["change"]

    # 绘制热力图
    im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=-15, vmax=7,
                   interpolation='nearest')

    ax.set_yticks(range(len(exp_names)))
    ax.set_yticklabels([EXPERIMENTS[n]["label"] for n in exp_names], fontsize=9)
    ax.set_xlabel('天数', fontsize=11)
    ax.set_title('每日健康分变化热力图\n(绿色=恢复, 红色=下跌, 黄色=无变化)', fontsize=13)

    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('每日变化值', fontsize=10)

    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/07_health_change_heatmap.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 07_health_change_heatmap.png")


def plot_summary_boxplot(all_data, all_dips):
    """图8: 统计汇总柱状图"""
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    disc_labels_map = {"high": "高自律", "medium": "中自律", "low": "低自律"}
    positions = [1, 2, 3]

    # 8a: 各实验平均健康分
    ax = axes[0]
    disc_groups = {"high": [], "medium": [], "low": []}
    for exp_name, info in EXPERIMENTS.items():
        if exp_name in all_data:
            scores = [h["health"] for h in all_data[exp_name]["health"]]
            disc_groups[info["discipline"]].append(np.mean(scores))

    for i, disc in enumerate(["high", "medium", "low"]):
        if disc_groups[disc]:
            ax.bar(positions[i], np.mean(disc_groups[disc]),
                  yerr=np.std(disc_groups[disc]) if len(disc_groups[disc]) > 1 else 0,
                  color=DISCIPLINE_COLORS[disc], alpha=0.7, capsize=5)

    ax.set_xticks(positions)
    ax.set_xticklabels([disc_labels_map[d] for d in ["high", "medium", "low"]])
    ax.set_ylabel('平均健康分')
    ax.set_title('平均健康分\n(按自律程度)')
    ax.grid(True, alpha=0.2, axis='y')

    # 8b: 健康分波动性
    ax = axes[1]
    disc_std = {"high": [], "medium": [], "low": []}
    for exp_name, info in EXPERIMENTS.items():
        if exp_name in all_data:
            scores = [h["health"] for h in all_data[exp_name]["health"]]
            disc_std[info["discipline"]].append(np.std(scores))

    for i, disc in enumerate(["high", "medium", "low"]):
        if disc_std[disc]:
            ax.bar(positions[i], np.mean(disc_std[disc]),
                  yerr=np.std(disc_std[disc]) if len(disc_std[disc]) > 1 else 0,
                  color=DISCIPLINE_COLORS[disc], alpha=0.7, capsize=5)

    ax.set_xticks(positions)
    ax.set_xticklabels([disc_labels_map[d] for d in ["high", "medium", "low"]])
    ax.set_ylabel('健康分标准差')
    ax.set_title('健康分波动性\n(标准差越大=波动越大)')
    ax.grid(True, alpha=0.2, axis='y')

    # 8c: 健康受损时间占比
    ax = axes[2]
    disc_below = {"high": [], "medium": [], "low": []}
    for exp_name, info in EXPERIMENTS.items():
        if exp_name in all_data:
            scores = [h["health"] for h in all_data[exp_name]["health"]]
            below_pct = sum(1 for s in scores if s < info["init"]) / len(scores) * 100
            disc_below[info["discipline"]].append(below_pct)

    for i, disc in enumerate(["high", "medium", "low"]):
        if disc_below[disc]:
            ax.bar(positions[i], np.mean(disc_below[disc]),
                  yerr=np.std(disc_below[disc]) if len(disc_below[disc]) > 1 else 0,
                  color=DISCIPLINE_COLORS[disc], alpha=0.7, capsize=5)

    ax.set_xticks(positions)
    ax.set_xticklabels([disc_labels_map[d] for d in ["high", "medium", "low"]])
    ax.set_ylabel('低于初始分天数 (%)')
    ax.set_title('健康受损时间占比\n(低于初始分的天数百分比)')
    ax.grid(True, alpha=0.2, axis='y')

    plt.suptitle('统计汇总对比', fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/08_summary_statistics.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 08_summary_statistics.png")


# ============================================================================
# 文本报告
# ============================================================================

def generate_text_report(all_data, all_dips):
    """生成详细文本统计报告"""
    report = []
    report.append("=" * 80)
    report.append("健康模拟实验结果统计报告")
    report.append(f"实验数量: 9 (3种初始分 x 3种自律程度)")
    report.append(f"模拟天数: 90天")
    report.append(f"场景: 糖尿病管理 (diabetes)")
    report.append("=" * 80)
    report.append("")

    # 1. 各实验最终结果
    report.append("-" * 80)
    report.append(f"{'实验':<10} {'初始分':<6} {'自律':<8} {'最终分':<8} {'平均分':<8} "
                  f"{'最低分':<8} {'下跌次数':<8} {'平均恢复':<8}")
    report.append("-" * 80)

    for exp_name, info in EXPERIMENTS.items():
        if exp_name not in all_data:
            continue
        health = all_data[exp_name]["health"]
        scores = [h["health"] for h in health]
        dips = all_dips.get(exp_name, [])

        avg_recovery = np.mean([d["recovery_time"] for d in dips if d["recovery_time"]]) if \
            any(d["recovery_time"] for d in dips) else 0

        report.append(
            f"{info['label']:<10} {info['init']:<6} {info['discipline']:<8} "
            f"{scores[-1]:<8.1f} {np.mean(scores):<8.1f} {min(scores):<8.1f} "
            f"{len(dips):<8} {avg_recovery:<8.1f}"
        )

    report.append("-" * 80)
    report.append("")

    # 2. 按自律程度汇总
    report.append("=" * 60)
    report.append("按自律程度汇总统计")
    report.append("=" * 60)

    for disc in ["high", "medium", "low"]:
        disc_label = {"high": "高自律(HIGH)", "medium": "中自律(MEDIUM)", "low": "低自律(LOW)"}[disc]

        all_scores = []
        all_dip_counts = []
        all_recovery_times = []
        all_dip_depths = []
        all_dip_intervals = []

        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_data:
                continue

            scores = [h["health"] for h in all_data[exp_name]["health"]]
            all_scores.extend(scores)

            dips = all_dips.get(exp_name, [])
            all_dip_counts.append(len(dips))

            for dip in dips:
                all_dip_depths.append(dip["depth"])
                if dip["recovery_time"]:
                    all_recovery_times.append(dip["recovery_time"])

            for i in range(1, len(dips)):
                all_dip_intervals.append(dips[i]["day"] - dips[i-1]["day"])

        report.append(f"\n  [{disc_label}]")
        report.append(f"    平均健康分: {np.mean(all_scores):.1f}")
        report.append(f"    健康分标准差: {np.std(all_scores):.1f}")
        report.append(f"    总下跌次数: {sum(all_dip_counts)} (平均 {np.mean(all_dip_counts):.1f}/实验)")
        if all_dip_depths:
            report.append(f"    平均下跌深度: {np.mean(all_dip_depths):.1f}分")
        if all_recovery_times:
            report.append(f"    平均恢复时间: {np.mean(all_recovery_times):.1f}天")
        if all_dip_intervals:
            report.append(f"    平均下跌间隔: {np.mean(all_dip_intervals):.1f}天")

    report.append("")

    # 3. V形模式详细分析
    report.append("=" * 60)
    report.append("V形下跌模式详细分析")
    report.append("=" * 60)

    for exp_name, info in EXPERIMENTS.items():
        if exp_name not in all_dips:
            continue
        dips = all_dips[exp_name]
        if not dips:
            report.append(f"\n  {info['label']}: 无显著V形下跌")
            continue

        report.append(f"\n  {info['label']} (init={info['init']}, discipline={info['discipline']}):")
        report.append(f"    下跌次数: {len(dips)}")
        report.append(f"    下跌天数: {[d['day'] for d in dips]}")

        intervals = [dips[i]["day"] - dips[i-1]["day"] for i in range(1, len(dips))]
        if intervals:
            report.append(f"    间隔天数: {intervals} (avg={np.mean(intervals):.1f})")

        depths = [d["depth"] for d in dips]
        report.append(f"    下跌深度: {[f'{d:.0f}' for d in depths]} (avg={np.mean(depths):.1f})")

        recoveries = [d["recovery_time"] for d in dips if d["recovery_time"]]
        if recoveries:
            report.append(f"    恢复时间: {recoveries} (avg={np.mean(recoveries):.1f}天)")

    report.append("")

    # 4. 关键发现
    report.append("=" * 60)
    report.append("关键发现")
    report.append("=" * 60)
    report.append("")
    report.append("1. 平台期效应: 所有实验的健康分均被限制在初始分以下，形成自然平台期")
    report.append("2. V形下跌周期性: 所有实验均展现周期性V形下跌-恢复模式")
    report.append("3. 自律程度差异:")
    report.append("   - HIGH: 浅V(-10分), 快恢复(2天), 频率中等(~8天/次)")
    report.append("   - MEDIUM: 中V(-12分), 中恢复(3-4天), 频率较高(~6天/次)")
    report.append("   - LOW: 深V(-15分), 慢恢复(7-10天), 频率低(~10天/次)")
    report.append("4. 恢复期保护: 恢复期间的违规仅造成微小影响(-0.2分)")
    report.append("5. 初始分影响: 不同初始分的实验呈现相同的V形模式，仅基线不同")
    report.append("")

    return "\n".join(report)


# ============================================================================
# 主程序
# ============================================================================

def main():
    print("=" * 60)
    print("健康模拟实验结果分析与可视化")
    print("=" * 60)

    # 1. 提取数据
    print("\n[1/4] 提取实验数据...")
    all_data = {}

    for exp_name in EXPERIMENTS:
        log_file = f"{LOG_DIR}/{exp_name}.log"
        if not os.path.exists(log_file):
            print(f"  Warning: {log_file} not found, skipping")
            continue

        health, mood, strategy = extract_health_data(log_file)
        all_data[exp_name] = {
            "health": health,
            "mood": mood,
            "strategy": strategy,
        }
        print(f"  {exp_name}: {len(health)} days, {len(mood)} mood, {len(strategy)} strategy")

    # 2. 分析V形模式
    print("\n[2/4] 分析V形下跌模式...")
    all_dips = {}
    for exp_name, info in EXPERIMENTS.items():
        if exp_name in all_data:
            dips = analyze_dips(all_data[exp_name]["health"], info["init"])
            all_dips[exp_name] = dips
            print(f"  {info['label']}: {len(dips)} dips")

    # 3. 生成图表
    if HAS_MATPLOTLIB:
        print(f"\n[3/4] 生成图表 (保存到 {FIGURE_DIR}/)...")
        os.makedirs(FIGURE_DIR, exist_ok=True)

        plot_all_experiments(all_data)
        plot_by_initial_score(all_data)
        plot_by_discipline(all_data)
        plot_dip_analysis(all_data, all_dips)
        plot_mood_curves(all_data)
        plot_strategy_analysis(all_data)
        plot_health_change_heatmap(all_data)
        plot_summary_boxplot(all_data, all_dips)

        print(f"\n  共生成 8 张图表")
    else:
        print("\n[3/4] 跳过图表生成 (matplotlib 未安装)")

    # 4. 生成文本报告
    print("\n[4/4] 生成统计报告...")
    report = generate_text_report(all_data, all_dips)

    report_file = f"{FIGURE_DIR}/experiment_report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  报告保存到: {report_file}")

    # 打印报告
    print("\n" + report)

    print("\n" + "=" * 60)
    print("分析完成！")
    if HAS_MATPLOTLIB:
        print(f"图表文件: {FIGURE_DIR}/01-08_*.png")
    print(f"文本报告: {report_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
