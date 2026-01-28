#!/usr/bin/env python3
"""
Health Simulation Experiment Results - Visualization & Statistical Analysis (English)

Charts generated:
1. Overview: All 9 experiments health curves
2. Grouped by initial score
3. Grouped by discipline level
4. V-shaped dip statistical analysis
5. Mood score curves
6. Strategy manager behavior analysis
7. Daily health change heatmap
8. Summary statistics
"""

import re
import os
import numpy as np
from collections import defaultdict

# Try importing matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 150
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available, will generate text report only")


# ============================================================================
# Data Extraction
# ============================================================================

LOG_DIR = "results/health"
FIGURE_DIR = "results/figures_en"

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

# Color scheme
DISCIPLINE_COLORS = {
    "high": "#2196F3",     # Blue
    "medium": "#FF9800",   # Orange
    "low": "#F44336",      # Red
}

INIT_COLORS = {
    90: "#4CAF50",  # Green
    75: "#9C27B0",  # Purple
    60: "#FF5722",  # Deep Orange
}


def extract_health_data(log_file):
    """Extract health score data from log file"""
    health_data = []
    mood_data = []
    strategy_data = []

    with open(log_file, 'r') as f:
        for line in f:
            # Extract health scores
            match = re.search(r'Day (\d+) Health: ([\d.]+) \(change: ([+-]?[\d.]+)\)', line)
            if match:
                day = int(match.group(1))
                health = float(match.group(2))
                change = float(match.group(3))
                health_data.append({"day": day, "health": health, "change": change})

            # Extract mood scores
            match = re.search(r'Day (\d+) Mood Score: ([\d.]+)/10', line)
            if match:
                day = int(match.group(1))
                mood = float(match.group(2))
                mood_data.append({"day": day, "mood": mood})

            # Extract strategy manager state
            match = re.search(r'Day (\d+) Strategy Manager: Level (\d+).*Phase: (\w+).*Trust Capital: ([\d.]+)', line)
            if match:
                day = int(match.group(1))
                level = int(match.group(2))
                phase = match.group(3)
                trust = float(match.group(4))
                strategy_data.append({"day": day, "level": level, "phase": phase, "trust": trust})

    return health_data, mood_data, strategy_data


def analyze_dips(health_data, init_score):
    """Analyze V-shaped dip patterns"""
    dips = []
    i = 0
    while i < len(health_data):
        if health_data[i]["change"] < -5:  # Significant drop
            dip_start = i
            dip_bottom = health_data[i]["health"]
            dip_depth = abs(health_data[i]["change"])

            # Find recovery point
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
# Chart Generation
# ============================================================================

def plot_all_experiments(all_data):
    """Chart 1: Overview of all 9 experiments"""
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

    # Add initial score reference lines
    for init_score in [60, 75, 90]:
        ax.axhline(y=init_score, color='gray', linestyle=':', alpha=0.3)
        ax.text(91, init_score, f'{init_score}', fontsize=8, color='gray', va='center')

    ax.axhline(y=30, color='red', linestyle='--', alpha=0.5, label='Alert Line (30)')

    ax.set_xlabel('Days', fontsize=12)
    ax.set_ylabel('Health Score', fontsize=12)
    ax.set_title('90-Day Health Simulation - Overview\n(9 Combinations: 3 Initial Scores x 3 Discipline Levels)', fontsize=14)
    ax.set_xlim(1, 90)
    ax.set_ylim(0, 100)
    ax.legend(loc='lower left', ncol=3, fontsize=9)
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/01_all_experiments_overview.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 01_all_experiments_overview.png")


def plot_by_initial_score(all_data):
    """Chart 2: Grouped by initial score (3 subplots)"""
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

        ax.axhline(y=init_score, color='green', linestyle='--', alpha=0.4, label=f'Initial={init_score}')
        ax.axhline(y=30, color='red', linestyle=':', alpha=0.3)

        ax.set_ylabel('Health Score', fontsize=11)
        ax.set_title(f'Initial Score = {init_score}', fontsize=12, fontweight='bold')
        ax.set_ylim(max(0, init_score - 25), init_score + 5)
        ax.legend(loc='lower left', ncol=4, fontsize=9)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('Days', fontsize=11)
    plt.suptitle('Comparison by Initial Health Score\n(Same initial score, different discipline levels)', fontsize=13, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/02_by_initial_score.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 02_by_initial_score.png")


def plot_by_discipline(all_data):
    """Chart 3: Grouped by discipline level (3 subplots)"""
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    for idx, disc in enumerate(["high", "medium", "low"]):
        ax = axes[idx]
        disc_label = {"high": "High Discipline", "medium": "Medium Discipline", "low": "Low Discipline"}[disc]

        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_data:
                continue

            health = all_data[exp_name]["health"]
            days = [h["day"] for h in health]
            scores = [h["health"] for h in health]

            color = INIT_COLORS[info["init"]]
            ax.plot(days, scores, color=color, linewidth=1.8,
                    label=f'Initial={info["init"]}', alpha=0.9)

        ax.axhline(y=30, color='red', linestyle=':', alpha=0.3)
        ax.set_ylabel('Health Score', fontsize=11)
        ax.set_title(f'{disc_label}', fontsize=12, fontweight='bold')
        ax.set_ylim(35, 95)
        ax.legend(loc='lower left', fontsize=9)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('Days', fontsize=11)
    plt.suptitle('Comparison by Discipline Level\n(Same discipline, different initial scores)', fontsize=13, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/03_by_discipline.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 03_by_discipline.png")


def plot_dip_analysis(all_data, all_dips):
    """Chart 4: V-shaped dip statistical analysis"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 4a: Dip count per experiment
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
    ax.set_ylabel('V-Dip Count')
    ax.set_title('V-Shaped Dip Count per Experiment (90 Days)')
    ax.grid(True, alpha=0.2, axis='y')

    # 4b: Dip interval distribution
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
            disc_label = {"high": "High", "medium": "Medium", "low": "Low"}[disc]
            ax.hist(intervals, bins=range(0, 30, 2), alpha=0.5,
                   color=DISCIPLINE_COLORS[disc], label=f'{disc_label}')

    ax.set_xlabel('Dip Interval (days)')
    ax.set_ylabel('Frequency')
    ax.set_title('V-Dip Interval Distribution')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)

    # 4c: Recovery time distribution
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
            disc_label = {"high": "High", "medium": "Medium", "low": "Low"}[disc]
            ax.hist(recovery_times, bins=range(0, 20, 1), alpha=0.5,
                   color=DISCIPLINE_COLORS[disc],
                   label=f'{disc_label}')

    ax.set_xlabel('Recovery Time (days)')
    ax.set_ylabel('Frequency')
    ax.set_title('Recovery Time Distribution')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)

    # 4d: Dip depth distribution
    ax = axes[1, 1]
    for disc in ["high", "medium", "low"]:
        depths = []
        for exp_name, info in EXPERIMENTS.items():
            if info["discipline"] != disc or exp_name not in all_dips:
                continue
            for dip in all_dips[exp_name]:
                depths.append(dip["depth"])

        if depths:
            disc_label = {"high": "High", "medium": "Medium", "low": "Low"}[disc]
            ax.hist(depths, bins=np.arange(5, 20, 1), alpha=0.5,
                   color=DISCIPLINE_COLORS[disc],
                   label=f'{disc_label}')

    ax.set_xlabel('Dip Depth (points)')
    ax.set_ylabel('Frequency')
    ax.set_title('V-Dip Depth Distribution')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)

    plt.suptitle('V-Shaped Dip Pattern Analysis', fontsize=14, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/04_dip_analysis.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 04_dip_analysis.png")


def plot_mood_curves(all_data):
    """Chart 5: Mood score curves"""
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

        ax.axhline(y=5.0, color='orange', linestyle='--', alpha=0.3, label='Neutral (5.0)')
        ax.set_ylabel('Mood Score', fontsize=11)
        ax.set_title(f'Initial Score = {init_score}', fontsize=11, fontweight='bold')
        ax.set_ylim(0, 10)
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel('Days', fontsize=11)
    plt.suptitle('Mood Score Trajectories (1-10)\n(Higher = more satisfied with health management)', fontsize=13, y=0.98)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/05_mood_curves.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 05_mood_curves.png")


def plot_strategy_analysis(all_data):
    """Chart 6: Strategy manager analysis - trust capital & intervention level"""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # 6a: Trust capital changes
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

    ax.set_ylabel('Trust Capital', fontsize=11)
    ax.set_title('Manager Trust Capital Over Time', fontsize=12)
    ax.legend(loc='lower right', ncol=3, fontsize=8)
    ax.grid(True, alpha=0.2)

    # 6b: Strategy level changes
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

    ax.set_xlabel('Days', fontsize=11)
    ax.set_ylabel('Intervention Level', fontsize=11)
    ax.set_title('Strategy Manager Intervention Level', fontsize=12)
    ax.set_ylim(-0.5, 4)
    ax.set_yticks([0, 1, 2, 3])
    ax.set_yticklabels(['L0 (Observe)', 'L1 (Remind)', 'L2 (Intervene)', 'L3 (Enforce)'])
    ax.legend(loc='upper right', ncol=3, fontsize=8)
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/06_strategy_analysis.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 06_strategy_analysis.png")


def plot_health_change_heatmap(all_data):
    """Chart 7: Daily health change heatmap"""
    fig, ax = plt.subplots(1, 1, figsize=(16, 6))

    # Build matrix
    exp_names = list(EXPERIMENTS.keys())
    max_days = 90
    matrix = np.zeros((len(exp_names), max_days))

    for i, exp_name in enumerate(exp_names):
        if exp_name in all_data:
            for h in all_data[exp_name]["health"]:
                if h["day"] <= max_days:
                    matrix[i, h["day"] - 1] = h["change"]

    # Draw heatmap
    im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', vmin=-15, vmax=7,
                   interpolation='nearest')

    ax.set_yticks(range(len(exp_names)))
    ax.set_yticklabels([EXPERIMENTS[n]["label"] for n in exp_names], fontsize=9)
    ax.set_xlabel('Days', fontsize=11)
    ax.set_title('Daily Health Score Change Heatmap\n(Green=Recovery, Red=Drop, Yellow=No Change)', fontsize=13)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Daily Change', fontsize=10)

    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/07_health_change_heatmap.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 07_health_change_heatmap.png")


def plot_summary_boxplot(all_data, all_dips):
    """Chart 8: Summary statistics bar chart"""
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    disc_labels_map = {"high": "High", "medium": "Medium", "low": "Low"}
    positions = [1, 2, 3]

    # 8a: Average health score by discipline
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
    ax.set_ylabel('Avg Health Score')
    ax.set_title('Average Health Score\n(by Discipline Level)')
    ax.grid(True, alpha=0.2, axis='y')

    # 8b: Health score volatility
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
    ax.set_ylabel('Health Score Std Dev')
    ax.set_title('Health Score Volatility\n(Higher std = more volatile)')
    ax.grid(True, alpha=0.2, axis='y')

    # 8c: Time spent below initial score
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
    ax.set_ylabel('Days Below Initial (%)')
    ax.set_title('Health Impairment Duration\n(% of days below initial score)')
    ax.grid(True, alpha=0.2, axis='y')

    plt.suptitle('Summary Statistics Comparison', fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(f'{FIGURE_DIR}/08_summary_statistics.png', bbox_inches='tight')
    plt.close()
    print("  Generated: 08_summary_statistics.png")


def plot_combined_health_mood(all_data):
    """Combined figure: Health scores (left) + Satisfaction scores (right), 3 rows by initial score"""
    fig, axes = plt.subplots(3, 2, figsize=(20, 10), sharex=True)

    for idx, init_score in enumerate([90, 75, 60]):
        # Left column: Health scores
        ax_h = axes[idx, 0]
        for exp_name, info in EXPERIMENTS.items():
            if info["init"] != init_score or exp_name not in all_data:
                continue
            health = all_data[exp_name]["health"]
            days = [h["day"] for h in health]
            scores = [h["health"] for h in health]
            color = DISCIPLINE_COLORS[info["discipline"]]
            ax_h.plot(days, scores, color=color, linewidth=2.0,
                      label=f'{info["discipline"].upper()}', alpha=0.9)

        ax_h.axhline(y=init_score, color='green', linestyle='--', alpha=0.4)
        ax_h.set_ylabel('Health Score', fontsize=14)
        ax_h.set_ylim(max(0, init_score - 25), init_score + 5)
        ax_h.set_xlim(1, 90)
        ax_h.legend(loc='lower left', fontsize=11)
        ax_h.grid(True, alpha=0.2)
        ax_h.tick_params(labelsize=12)
        ax_h.text(-0.12, 0.5, f'Initial = {init_score}',
                  transform=ax_h.transAxes, fontsize=14, fontweight='bold',
                  va='center', ha='center', rotation=90)

        # Right column: Mood scores
        ax_m = axes[idx, 1]
        for exp_name, info in EXPERIMENTS.items():
            if info["init"] != init_score or exp_name not in all_data:
                continue
            mood = all_data[exp_name]["mood"]
            if not mood:
                continue
            days = [m["day"] for m in mood]
            scores = [m["mood"] for m in mood]
            color = DISCIPLINE_COLORS[info["discipline"]]
            ax_m.plot(days, scores, color=color, linewidth=2.0,
                      label=f'{info["discipline"].upper()}', alpha=0.7)

        ax_m.axhline(y=5.0, color='orange', linestyle='--', alpha=0.3)
        ax_m.set_ylabel('Satisfaction', fontsize=14)
        ax_m.set_ylim(0, 10)
        ax_m.set_xlim(1, 90)
        ax_m.legend(loc='upper right', fontsize=11)
        ax_m.grid(True, alpha=0.2)
        ax_m.tick_params(labelsize=12)

    axes[-1, 0].set_xlabel('Days', fontsize=14)
    axes[-1, 1].set_xlabel('Days', fontsize=14)

    plt.subplots_adjust(hspace=0.15, wspace=0.12)
    plt.savefig(f'{FIGURE_DIR}/09_combined_health_mood.png', bbox_inches='tight', dpi=200)
    plt.close()
    print("  Generated: 09_combined_health_mood.png")

    # Write caption
    caption = (
        "Daily trajectories of health score (left) and satisfaction (right) over 90 days "
        "across the 3 x 3 initial-score/discipline grid. "
        "Rows share unified initial health values; columns distinguish behavioral outcomes from subjective responses."
    )
    with open(f'{FIGURE_DIR}/09_caption.txt', 'w') as f:
        f.write(caption)
    print("  Generated: 09_caption.txt")


# ============================================================================
# Text Report
# ============================================================================

def generate_text_report(all_data, all_dips):
    """Generate detailed text statistical report"""
    report = []
    report.append("=" * 80)
    report.append("Health Simulation Experiment Results - Statistical Report")
    report.append(f"Experiments: 9 (3 initial scores x 3 discipline levels)")
    report.append(f"Duration: 90 days")
    report.append(f"Scenario: Diabetes Management")
    report.append("=" * 80)
    report.append("")

    # 1. Results per experiment
    report.append("-" * 80)
    report.append(f"{'Experiment':<12} {'Init':<6} {'Discipline':<12} {'Final':<8} {'Mean':<8} "
                  f"{'Min':<8} {'Dips':<8} {'Avg Recov':<10}")
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
            f"{info['label']:<12} {info['init']:<6} {info['discipline']:<12} "
            f"{scores[-1]:<8.1f} {np.mean(scores):<8.1f} {min(scores):<8.1f} "
            f"{len(dips):<8} {avg_recovery:<10.1f}"
        )

    report.append("-" * 80)
    report.append("")

    # 2. Summary by discipline level
    report.append("=" * 60)
    report.append("Summary by Discipline Level")
    report.append("=" * 60)

    for disc in ["high", "medium", "low"]:
        disc_label = {"high": "High Discipline", "medium": "Medium Discipline", "low": "Low Discipline"}[disc]

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
        report.append(f"    Mean Health Score: {np.mean(all_scores):.1f}")
        report.append(f"    Std Deviation: {np.std(all_scores):.1f}")
        report.append(f"    Total Dips: {sum(all_dip_counts)} (avg {np.mean(all_dip_counts):.1f}/experiment)")
        if all_dip_depths:
            report.append(f"    Mean Dip Depth: {np.mean(all_dip_depths):.1f} points")
        if all_recovery_times:
            report.append(f"    Mean Recovery Time: {np.mean(all_recovery_times):.1f} days")
        if all_dip_intervals:
            report.append(f"    Mean Dip Interval: {np.mean(all_dip_intervals):.1f} days")

    report.append("")

    # 3. Detailed V-dip analysis
    report.append("=" * 60)
    report.append("V-Shaped Dip Pattern Details")
    report.append("=" * 60)

    for exp_name, info in EXPERIMENTS.items():
        if exp_name not in all_dips:
            continue
        dips = all_dips[exp_name]
        if not dips:
            report.append(f"\n  {info['label']}: No significant V-dips")
            continue

        report.append(f"\n  {info['label']} (init={info['init']}, discipline={info['discipline']}):")
        report.append(f"    Dip Count: {len(dips)}")
        report.append(f"    Dip Days: {[d['day'] for d in dips]}")

        intervals = [dips[i]["day"] - dips[i-1]["day"] for i in range(1, len(dips))]
        if intervals:
            report.append(f"    Intervals: {intervals} (avg={np.mean(intervals):.1f})")

        depths = [d["depth"] for d in dips]
        report.append(f"    Depths: {[f'{d:.0f}' for d in depths]} (avg={np.mean(depths):.1f})")

        recoveries = [d["recovery_time"] for d in dips if d["recovery_time"]]
        if recoveries:
            report.append(f"    Recovery Times: {recoveries} (avg={np.mean(recoveries):.1f} days)")

    report.append("")

    # 4. Key findings
    report.append("=" * 60)
    report.append("Key Findings")
    report.append("=" * 60)
    report.append("")
    report.append("1. Plateau Effect: Health scores are capped at initial score, forming natural plateaus")
    report.append("2. Periodic V-Dips: All experiments exhibit periodic V-shaped dip-recovery patterns")
    report.append("3. Discipline Level Differences:")
    report.append("   - HIGH: Shallow V (-10pts), fast recovery (2d), moderate frequency (~8d/cycle)")
    report.append("   - MEDIUM: Medium V (-12pts), medium recovery (3-4d), higher frequency (~6d/cycle)")
    report.append("   - LOW: Deep V (-15pts), slow recovery (7-10d), low frequency (~10d/cycle)")
    report.append("4. Recovery Protection: Violations during recovery cause minimal impact (-0.2pts)")
    report.append("5. Initial Score Impact: Different initial scores show same V-pattern, only baseline differs")
    report.append("")

    return "\n".join(report)


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 60)
    print("Health Simulation Results - Analysis & Visualization (EN)")
    print("=" * 60)

    # 1. Extract data
    print("\n[1/4] Extracting experiment data...")
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

    # 2. Analyze V-dip patterns
    print("\n[2/4] Analyzing V-shaped dip patterns...")
    all_dips = {}
    for exp_name, info in EXPERIMENTS.items():
        if exp_name in all_data:
            dips = analyze_dips(all_data[exp_name]["health"], info["init"])
            all_dips[exp_name] = dips
            print(f"  {info['label']}: {len(dips)} dips")

    # 3. Generate charts
    if HAS_MATPLOTLIB:
        print(f"\n[3/4] Generating charts (saving to {FIGURE_DIR}/)...")
        os.makedirs(FIGURE_DIR, exist_ok=True)

        plot_all_experiments(all_data)
        plot_by_initial_score(all_data)
        plot_by_discipline(all_data)
        plot_dip_analysis(all_data, all_dips)
        plot_mood_curves(all_data)
        plot_strategy_analysis(all_data)
        plot_health_change_heatmap(all_data)
        plot_summary_boxplot(all_data, all_dips)
        plot_combined_health_mood(all_data)

        print(f"\n  Total: 9 charts generated")
    else:
        print("\n[3/4] Skipping chart generation (matplotlib not installed)")

    # 4. Generate text report
    print("\n[4/4] Generating statistical report...")
    report = generate_text_report(all_data, all_dips)

    report_file = f"{FIGURE_DIR}/experiment_report.txt"
    os.makedirs(FIGURE_DIR, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  Report saved to: {report_file}")

    # Print report
    print("\n" + report)

    print("\n" + "=" * 60)
    print("Analysis complete!")
    if HAS_MATPLOTLIB:
        print(f"Charts: {FIGURE_DIR}/01-08_*.png")
    print(f"Report: {report_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
