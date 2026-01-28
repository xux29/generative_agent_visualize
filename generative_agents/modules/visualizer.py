"""generative_agents.visualizer

论文图表可视化模块：生成健康管理模拟的各类分析图表

支持的图表类型：
1. 时序变化图（折线图）
2. 多维度雷达图
3. 因素贡献堆叠柱状图
4. 相关性散点图
5. 阶段箱线图
6. 干预效果热力图
7. 综合评估仪表盘
"""

import os
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.gridspec import GridSpec
    import matplotlib.font_manager as fm
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Visualization features disabled.")

try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False


class HealthVisualizer:
    """健康管理可视化类"""

    # 论文配色方案（适合学术出版）
    COLORS = {
        "health": "#2E86AB",        # 蓝色 - 健康分
        "satisfaction": "#A23B72",   # 紫红色 - 满意度
        "effectiveness": "#F18F01",  # 橙色 - 干预效果
        "composite": "#C73E1D",      # 红色 - 综合分
        "positive": "#28A745",       # 绿色 - 正向
        "negative": "#DC3545",       # 红色 - 负向
        "neutral": "#6C757D",        # 灰色 - 中性
        "phase_adjustment": "#FFE5B4",    # 浅橙 - 磨合期
        "phase_formation": "#B4E5FF",     # 浅蓝 - 习惯养成期
        "phase_fatigue": "#FFB4B4",       # 浅红 - 倦怠期
    }

    # 阶段颜色
    PHASE_COLORS = {
        "adjustment": "#FFE5B4",
        "formation": "#B4E5FF",
        "fatigue": "#FFB4B4",
    }

    PHASE_NAMES = {
        "adjustment": "磨合期",
        "formation": "习惯养成期",
        "fatigue": "倦怠期",
    }

    def __init__(self, output_dir: str = "results/figures", dpi: int = 300,
                 figsize: Tuple[int, int] = (10, 6), font_family: str = None):
        """
        初始化可视化器

        Args:
            output_dir: 图表输出目录
            dpi: 图像分辨率
            figsize: 默认图表尺寸
            font_family: 字体（支持中文）
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib is required for visualization")

        self.output_dir = output_dir
        self.dpi = dpi
        self.figsize = figsize

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

        # 设置中文字体
        self._setup_chinese_font(font_family)

        # 设置论文风格
        self._setup_paper_style()

    def _setup_chinese_font(self, font_family: str = None):
        """设置中文字体支持"""
        if font_family:
            plt.rcParams['font.family'] = font_family
            plt.rcParams['font.sans-serif'] = [font_family]
            plt.rcParams['axes.unicode_minus'] = False
            return

        # 尝试常见的中文字体（按优先级排序）
        chinese_fonts = [
            'Songti SC',            # macOS 宋体
            'STSong',               # macOS
            'PingFang SC',          # macOS
            'Heiti SC',             # macOS 黑体
            'Hiragino Sans GB',     # macOS
            'SimHei',               # Windows 黑体
            'SimSun',               # Windows 宋体
            'Microsoft YaHei',      # Windows 微软雅黑
            'WenQuanYi Micro Hei',  # Linux
            'Noto Sans CJK SC',     # Linux/通用
            'Noto Serif CJK SC',    # Linux/通用
            'Source Han Sans SC',   # Adobe 思源黑体
            'Arial Unicode MS',     # 通用
            'DejaVu Sans',          # 备选
        ]

        available_fonts = set(f.name for f in fm.fontManager.ttflist)

        selected_font = None
        for font in chinese_fonts:
            if font in available_fonts:
                selected_font = font
                break

        if selected_font:
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = [selected_font] + list(plt.rcParams['font.sans-serif'])
            print(f"Visualizer: Using font '{selected_font}' for Chinese support")
        else:
            # 如果找不到中文字体，打印警告
            print("Warning: No Chinese font found. Chinese characters may not display correctly.")
            print("Available fonts:", sorted(list(available_fonts))[:20], "...")

        # 解决负号显示问题
        plt.rcParams['axes.unicode_minus'] = False

    def _setup_paper_style(self):
        """设置论文级别的图表样式"""
        if HAS_SEABORN:
            sns.set_style("whitegrid")
            sns.set_context("paper", font_scale=1.2)

        plt.rcParams.update({
            'figure.facecolor': 'white',
            'axes.facecolor': 'white',
            'axes.edgecolor': '#333333',
            'axes.linewidth': 1.2,
            'axes.grid': True,
            'grid.alpha': 0.3,
            'grid.linestyle': '--',
            'xtick.direction': 'out',
            'ytick.direction': 'out',
            'xtick.major.size': 5,
            'ytick.major.size': 5,
            'legend.framealpha': 0.9,
            'legend.edgecolor': '#333333',
            'font.family': 'sans-serif',
            'font.sans-serif': ['Songti SC', 'Hiragino Sans GB', 'SimHei', 'DejaVu Sans'],
            'axes.unicode_minus': False,
        })

    def plot_dual_axis_timeline(
        self,
        days: List[int],
        health_scores: List[float],
        satisfaction_scores: List[float],
        title: str = "健康分与满意度变化趋势",
        show_phases: bool = True,
        show_trend: bool = True,
        save_name: str = "timeline_dual_axis.png"
    ) -> str:
        """
        绘制双轴时序折线图

        Args:
            days: 天数列表
            health_scores: 健康分列表
            satisfaction_scores: 满意度列表
            title: 图表标题
            show_phases: 是否显示阶段背景
            show_trend: 是否显示趋势线
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig, ax1 = plt.subplots(figsize=self.figsize)

        # 添加阶段背景
        if show_phases:
            self._add_phase_background(ax1, days)

        # 绘制健康分（左轴）
        line1 = ax1.plot(days, health_scores,
                         color=self.COLORS["health"],
                         linewidth=2.5,
                         marker='o',
                         markersize=4,
                         label='健康分')
        ax1.set_xlabel('天数', fontsize=12)
        ax1.set_ylabel('健康分', color=self.COLORS["health"], fontsize=12)
        ax1.tick_params(axis='y', labelcolor=self.COLORS["health"])
        ax1.set_ylim(0, 10.5)

        # 绘制满意度（右轴）
        ax2 = ax1.twinx()
        line2 = ax2.plot(days, satisfaction_scores,
                         color=self.COLORS["satisfaction"],
                         linewidth=2.5,
                         marker='s',
                         markersize=4,
                         label='满意度')
        ax2.set_ylabel('满意度', color=self.COLORS["satisfaction"], fontsize=12)
        ax2.tick_params(axis='y', labelcolor=self.COLORS["satisfaction"])
        ax2.set_ylim(0, 10.5)

        # 添加趋势线
        if show_trend and len(days) > 2:
            z1 = np.polyfit(days, health_scores, 1)
            p1 = np.poly1d(z1)
            ax1.plot(days, p1(days), '--', color=self.COLORS["health"], alpha=0.5, linewidth=1.5)

            z2 = np.polyfit(days, satisfaction_scores, 1)
            p2 = np.poly1d(z2)
            ax2.plot(days, p2(days), '--', color=self.COLORS["satisfaction"], alpha=0.5, linewidth=1.5)

        # 合并图例
        lines = line1 + line2
        labels = [l.get_label() for l in lines]

        # 添加阶段图例
        if show_phases:
            phase_patches = [
                mpatches.Patch(color=self.PHASE_COLORS["adjustment"], alpha=0.3, label='磨合期 (1-7天)'),
                mpatches.Patch(color=self.PHASE_COLORS["formation"], alpha=0.3, label='习惯养成期 (8-21天)'),
                mpatches.Patch(color=self.PHASE_COLORS["fatigue"], alpha=0.3, label='倦怠期 (22+天)'),
            ]
            ax1.legend(handles=lines + phase_patches, loc='upper left', fontsize=9)
        else:
            ax1.legend(lines, labels, loc='upper left', fontsize=10)

        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.tight_layout()

        # 保存
        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def _add_phase_background(self, ax, days: List[int]):
        """添加阶段背景色"""
        max_day = max(days)

        # 磨合期 (1-7)
        if max_day >= 1:
            ax.axvspan(0.5, min(7.5, max_day + 0.5),
                      alpha=0.2, color=self.PHASE_COLORS["adjustment"])

        # 习惯养成期 (8-21)
        if max_day >= 8:
            ax.axvspan(7.5, min(21.5, max_day + 0.5),
                      alpha=0.2, color=self.PHASE_COLORS["formation"])

        # 倦怠期 (22+)
        if max_day >= 22:
            ax.axvspan(21.5, max_day + 0.5,
                      alpha=0.2, color=self.PHASE_COLORS["fatigue"])

    def plot_radar_chart(
        self,
        scores: Dict[str, float],
        title: str = "多维度评分雷达图",
        max_score: float = 10,
        save_name: str = "radar_chart.png"
    ) -> str:
        """
        绘制多维度雷达图

        Args:
            scores: 各维度分数 {"健康分": 8, "满意度": 7, ...}
            title: 图表标题
            max_score: 最大分数
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        categories = list(scores.keys())
        values = list(scores.values())

        # 闭合雷达图
        values += values[:1]

        # 计算角度
        angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))

        # 绘制雷达图
        ax.plot(angles, values, 'o-', linewidth=2.5, color=self.COLORS["composite"])
        ax.fill(angles, values, alpha=0.25, color=self.COLORS["composite"])

        # 设置刻度
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=11)
        ax.set_ylim(0, max_score)

        # 添加网格刻度标签
        ax.set_yticks([2, 4, 6, 8, 10])
        ax.set_yticklabels(['2', '4', '6', '8', '10'], fontsize=9)

        # 在每个顶点添加数值
        for angle, value, cat in zip(angles[:-1], values[:-1], categories):
            ax.annotate(f'{value:.1f}',
                       xy=(angle, value),
                       xytext=(angle, value + 0.8),
                       ha='center', va='bottom',
                       fontsize=10, fontweight='bold',
                       color=self.COLORS["composite"])

        plt.title(title, fontsize=14, fontweight='bold', pad=20)

        # 保存
        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def plot_factor_contribution(
        self,
        days: List[int],
        factor_data: Dict[str, List[float]],
        title: str = "满意度影响因素分解",
        save_name: str = "factor_contribution.png"
    ) -> str:
        """
        绘制因素贡献堆叠柱状图

        Args:
            days: 天数列表
            factor_data: 各因素数据 {"干预频率": [...], "干预强度": [...], ...}
            title: 图表标题
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig, ax = plt.subplots(figsize=self.figsize)

        factor_colors = [
            '#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#28A745', '#6C757D'
        ]

        # 分离正负值
        factors = list(factor_data.keys())

        # 绘制正值堆叠
        bottom_pos = np.zeros(len(days))
        bottom_neg = np.zeros(len(days))

        for i, (factor, values) in enumerate(factor_data.items()):
            values = np.array(values)
            pos_values = np.maximum(values, 0)
            neg_values = np.minimum(values, 0)

            color = factor_colors[i % len(factor_colors)]

            if np.any(pos_values > 0):
                ax.bar(days, pos_values, bottom=bottom_pos,
                      label=f'{factor} (+)', color=color, alpha=0.8, width=0.8)
                bottom_pos += pos_values

            if np.any(neg_values < 0):
                ax.bar(days, neg_values, bottom=bottom_neg,
                      label=f'{factor} (-)', color=color, alpha=0.4, width=0.8,
                      hatch='///')
                bottom_neg += neg_values

        ax.axhline(y=0, color='black', linewidth=0.8)
        ax.set_xlabel('天数', fontsize=12)
        ax.set_ylabel('影响值', fontsize=12)
        ax.legend(loc='upper right', fontsize=9, ncol=2)

        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.tight_layout()

        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def plot_correlation_scatter(
        self,
        health_scores: List[float],
        satisfaction_scores: List[float],
        days: List[int] = None,
        title: str = "健康分与满意度相关性分析",
        save_name: str = "correlation_scatter.png"
    ) -> str:
        """
        绘制相关性散点图

        Args:
            health_scores: 健康分列表
            satisfaction_scores: 满意度列表
            days: 天数（用于颜色映射）
            title: 图表标题
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig, ax = plt.subplots(figsize=(8, 8))

        # 根据天数着色（如果提供）
        if days:
            scatter = ax.scatter(health_scores, satisfaction_scores,
                               c=days, cmap='viridis',
                               s=80, alpha=0.7, edgecolors='white', linewidths=1)
            cbar = plt.colorbar(scatter)
            cbar.set_label('天数', fontsize=11)
        else:
            ax.scatter(health_scores, satisfaction_scores,
                      color=self.COLORS["composite"], s=80, alpha=0.7,
                      edgecolors='white', linewidths=1)

        # 添加趋势线
        z = np.polyfit(health_scores, satisfaction_scores, 1)
        p = np.poly1d(z)
        x_line = np.linspace(min(health_scores), max(health_scores), 100)
        ax.plot(x_line, p(x_line), '--', color=self.COLORS["negative"],
               linewidth=2, alpha=0.7, label=f'趋势线 (y={z[0]:.2f}x+{z[1]:.2f})')

        # 计算相关系数
        correlation = np.corrcoef(health_scores, satisfaction_scores)[0, 1]
        ax.text(0.05, 0.95, f'相关系数 r = {correlation:.3f}',
               transform=ax.transAxes, fontsize=11,
               verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        ax.set_xlabel('健康分', fontsize=12)
        ax.set_ylabel('满意度', fontsize=12)
        ax.set_xlim(0, 10.5)
        ax.set_ylim(0, 10.5)
        ax.legend(loc='lower right', fontsize=10)

        # 添加参考线（理想状态）
        ax.plot([0, 10], [0, 10], ':', color='gray', alpha=0.5, label='理想平衡线')

        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.tight_layout()

        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def plot_phase_boxplot(
        self,
        phase_data: Dict[str, Dict[str, List[float]]],
        title: str = "各阶段评分分布对比",
        save_name: str = "phase_boxplot.png"
    ) -> str:
        """
        绘制阶段箱线图

        Args:
            phase_data: 各阶段数据
                {"adjustment": {"健康分": [...], "满意度": [...]}, ...}
            title: 图表标题
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig, axes = plt.subplots(1, 2, figsize=(12, 6))

        phases = list(phase_data.keys())
        phase_labels = [self.PHASE_NAMES.get(p, p) for p in phases]

        # 健康分箱线图
        health_data = [phase_data[p].get("健康分", []) for p in phases]
        bp1 = axes[0].boxplot(health_data, labels=phase_labels, patch_artist=True)
        for i, patch in enumerate(bp1['boxes']):
            patch.set_facecolor(self.PHASE_COLORS.get(phases[i], '#CCCCCC'))
            patch.set_alpha(0.7)
        axes[0].set_ylabel('健康分', fontsize=12)
        axes[0].set_ylim(0, 10.5)
        axes[0].set_title('健康分分布', fontsize=12)

        # 满意度箱线图
        satisfaction_data = [phase_data[p].get("满意度", []) for p in phases]
        bp2 = axes[1].boxplot(satisfaction_data, labels=phase_labels, patch_artist=True)
        for i, patch in enumerate(bp2['boxes']):
            patch.set_facecolor(self.PHASE_COLORS.get(phases[i], '#CCCCCC'))
            patch.set_alpha(0.7)
        axes[1].set_ylabel('满意度', fontsize=12)
        axes[1].set_ylim(0, 10.5)
        axes[1].set_title('满意度分布', fontsize=12)

        plt.suptitle(title, fontsize=14, fontweight='bold')
        plt.tight_layout()

        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def plot_intervention_heatmap(
        self,
        intervention_matrix: np.ndarray,
        row_labels: List[str],
        col_labels: List[str],
        title: str = "干预类型与效果热力图",
        save_name: str = "intervention_heatmap.png"
    ) -> str:
        """
        绘制干预效果热力图

        Args:
            intervention_matrix: 干预效果矩阵 (干预类型 x 结果维度)
            row_labels: 行标签（干预类型）
            col_labels: 列标签（结果维度）
            title: 图表标题
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig, ax = plt.subplots(figsize=(10, 8))

        if HAS_SEABORN:
            sns.heatmap(intervention_matrix,
                       annot=True, fmt='.2f',
                       xticklabels=col_labels,
                       yticklabels=row_labels,
                       cmap='RdYlGn',
                       center=0,
                       ax=ax,
                       cbar_kws={'label': '影响值'})
        else:
            im = ax.imshow(intervention_matrix, cmap='RdYlGn', aspect='auto')
            ax.set_xticks(range(len(col_labels)))
            ax.set_yticks(range(len(row_labels)))
            ax.set_xticklabels(col_labels)
            ax.set_yticklabels(row_labels)

            # 添加数值标注
            for i in range(len(row_labels)):
                for j in range(len(col_labels)):
                    ax.text(j, i, f'{intervention_matrix[i, j]:.2f}',
                           ha='center', va='center', fontsize=10)

            plt.colorbar(im, label='影响值')

        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.tight_layout()

        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def plot_comprehensive_dashboard(
        self,
        evaluation_data: Dict,
        title: str = "健康管理综合评估仪表盘",
        save_name: str = "dashboard.png"
    ) -> str:
        """
        绘制综合评估仪表盘

        Args:
            evaluation_data: 评估数据
                {
                    "days": [...],
                    "health_scores": [...],
                    "satisfaction_scores": [...],
                    "composite_scores": [...],
                    "current_phase": "formation",
                    "recommendations": [...]
                }
            title: 图表标题
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3)

        days = evaluation_data.get("days", [])
        health = evaluation_data.get("health_scores", [])
        satisfaction = evaluation_data.get("satisfaction_scores", [])
        composite = evaluation_data.get("composite_scores", [])

        # 1. 时序变化图（跨两列）
        ax1 = fig.add_subplot(gs[0, :2])
        if days and health and satisfaction:
            ax1.plot(days, health, '-o', color=self.COLORS["health"],
                    label='健康分', linewidth=2, markersize=4)
            ax1.plot(days, satisfaction, '-s', color=self.COLORS["satisfaction"],
                    label='满意度', linewidth=2, markersize=4)
            if composite:
                ax1.plot(days, composite, '-^', color=self.COLORS["composite"],
                        label='综合分', linewidth=2, markersize=4)
            ax1.set_xlabel('天数')
            ax1.set_ylabel('分数')
            ax1.set_ylim(0, 10.5)
            ax1.legend(loc='upper left')
            ax1.set_title('评分变化趋势', fontsize=12, fontweight='bold')
            self._add_phase_background(ax1, days)

        # 2. 当前状态雷达图
        ax2 = fig.add_subplot(gs[0, 2], projection='polar')
        if health and satisfaction and composite:
            current_scores = {
                '健康分': health[-1] if health else 0,
                '满意度': satisfaction[-1] if satisfaction else 0,
                '综合分': composite[-1] if composite else 0,
            }
            categories = list(current_scores.keys())
            values = list(current_scores.values()) + [list(current_scores.values())[0]]
            angles = [n / len(categories) * 2 * np.pi for n in range(len(categories))]
            angles += angles[:1]

            ax2.plot(angles, values, 'o-', linewidth=2, color=self.COLORS["composite"])
            ax2.fill(angles, values, alpha=0.25, color=self.COLORS["composite"])
            ax2.set_xticks(angles[:-1])
            ax2.set_xticklabels(categories, fontsize=10)
            ax2.set_ylim(0, 10)
            ax2.set_title('当前状态', fontsize=12, fontweight='bold', pad=15)

        # 3. 分数分布直方图
        ax3 = fig.add_subplot(gs[1, 0])
        if health:
            ax3.hist(health, bins=10, range=(0, 10),
                    color=self.COLORS["health"], alpha=0.7, edgecolor='white')
            ax3.axvline(np.mean(health), color='red', linestyle='--', label=f'均值: {np.mean(health):.1f}')
            ax3.set_xlabel('健康分')
            ax3.set_ylabel('频次')
            ax3.set_title('健康分分布', fontsize=11)
            ax3.legend(fontsize=9)

        # 4. 满意度分布
        ax4 = fig.add_subplot(gs[1, 1])
        if satisfaction:
            ax4.hist(satisfaction, bins=10, range=(0, 10),
                    color=self.COLORS["satisfaction"], alpha=0.7, edgecolor='white')
            ax4.axvline(np.mean(satisfaction), color='red', linestyle='--', label=f'均值: {np.mean(satisfaction):.1f}')
            ax4.set_xlabel('满意度')
            ax4.set_ylabel('频次')
            ax4.set_title('满意度分布', fontsize=11)
            ax4.legend(fontsize=9)

        # 5. 相关性散点图
        ax5 = fig.add_subplot(gs[1, 2])
        if health and satisfaction:
            ax5.scatter(health, satisfaction, c=days if days else 'blue',
                       cmap='viridis', alpha=0.7, s=50)
            z = np.polyfit(health, satisfaction, 1)
            p = np.poly1d(z)
            x_line = np.linspace(min(health), max(health), 100)
            ax5.plot(x_line, p(x_line), '--', color='red', alpha=0.7)
            corr = np.corrcoef(health, satisfaction)[0, 1]
            ax5.text(0.05, 0.95, f'r = {corr:.3f}', transform=ax5.transAxes,
                    fontsize=10, verticalalignment='top')
            ax5.set_xlabel('健康分')
            ax5.set_ylabel('满意度')
            ax5.set_title('健康-满意度相关性', fontsize=11)

        # 6. 统计摘要表格
        ax6 = fig.add_subplot(gs[2, :2])
        ax6.axis('off')

        if health and satisfaction:
            stats_data = [
                ['指标', '健康分', '满意度', '综合分'],
                ['当前值', f'{health[-1]:.1f}', f'{satisfaction[-1]:.1f}',
                 f'{composite[-1]:.1f}' if composite else '-'],
                ['平均值', f'{np.mean(health):.1f}', f'{np.mean(satisfaction):.1f}',
                 f'{np.mean(composite):.1f}' if composite else '-'],
                ['最大值', f'{max(health):.1f}', f'{max(satisfaction):.1f}',
                 f'{max(composite):.1f}' if composite else '-'],
                ['最小值', f'{min(health):.1f}', f'{min(satisfaction):.1f}',
                 f'{min(composite):.1f}' if composite else '-'],
                ['标准差', f'{np.std(health):.2f}', f'{np.std(satisfaction):.2f}',
                 f'{np.std(composite):.2f}' if composite else '-'],
            ]

            table = ax6.table(cellText=stats_data, loc='center', cellLoc='center',
                             colWidths=[0.2, 0.2, 0.2, 0.2])
            table.auto_set_font_size(False)
            table.set_fontsize(11)
            table.scale(1.2, 1.8)

            # 设置表头样式
            for j in range(4):
                table[(0, j)].set_facecolor('#4472C4')
                table[(0, j)].set_text_props(color='white', fontweight='bold')

            ax6.set_title('统计摘要', fontsize=12, fontweight='bold', pad=20)

        # 7. 建议区域
        ax7 = fig.add_subplot(gs[2, 2])
        ax7.axis('off')

        recommendations = evaluation_data.get("recommendations", [])
        if recommendations:
            rec_text = "改进建议:\n\n"
            for i, rec in enumerate(recommendations[:5], 1):
                if isinstance(rec, dict):
                    priority = rec.get("priority", "medium")
                    icon = "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
                    rec_text += f"{i}. {icon} {rec.get('message', '')}\n\n"
                else:
                    rec_text += f"{i}. {rec}\n\n"
            ax7.text(0.1, 0.9, rec_text, transform=ax7.transAxes,
                    fontsize=10, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.suptitle(title, fontsize=16, fontweight='bold', y=0.98)

        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def plot_area_chart(
        self,
        days: List[int],
        data: Dict[str, List[float]],
        title: str = "各维度得分变化面积图",
        save_name: str = "area_chart.png"
    ) -> str:
        """
        绘制堆叠面积图

        Args:
            days: 天数列表
            data: 各维度数据 {"健康分": [...], "满意度": [...], ...}
            title: 图表标题
            save_name: 保存文件名

        Returns:
            str: 保存的文件路径
        """
        fig, ax = plt.subplots(figsize=self.figsize)

        colors = [self.COLORS["health"], self.COLORS["satisfaction"],
                  self.COLORS["effectiveness"]]

        labels = list(data.keys())
        values = [data[k] for k in labels]

        ax.stackplot(days, values, labels=labels, colors=colors[:len(labels)], alpha=0.7)

        ax.set_xlabel('天数', fontsize=12)
        ax.set_ylabel('累积分数', fontsize=12)
        ax.legend(loc='upper left', fontsize=10)

        plt.title(title, fontsize=14, fontweight='bold', pad=15)
        plt.tight_layout()

        save_path = os.path.join(self.output_dir, save_name)
        plt.savefig(save_path, dpi=self.dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

        return save_path

    def generate_paper_figures(
        self,
        simulation_data: Dict,
        prefix: str = "fig"
    ) -> Dict[str, str]:
        """
        一键生成论文所需的所有图表

        Args:
            simulation_data: 模拟数据
                {
                    "days": [1, 2, 3, ...],
                    "health_scores": [...],
                    "satisfaction_scores": [...],
                    "composite_scores": [...],
                    "factor_contributions": {"干预频率": [...], ...},
                    "phase_data": {"adjustment": {...}, ...},
                    "intervention_matrix": np.array(...),
                    "recommendations": [...]
                }
            prefix: 文件名前缀

        Returns:
            Dict[str, str]: 图表名称到文件路径的映射
        """
        figures = {}

        days = simulation_data.get("days", [])
        health = simulation_data.get("health_scores", [])
        satisfaction = simulation_data.get("satisfaction_scores", [])
        composite = simulation_data.get("composite_scores", [])

        # 1. 双轴时序图
        if days and health and satisfaction:
            figures["timeline"] = self.plot_dual_axis_timeline(
                days, health, satisfaction,
                save_name=f"{prefix}_1_timeline.png"
            )

        # 2. 雷达图（最终状态）
        if health and satisfaction and composite:
            figures["radar"] = self.plot_radar_chart(
                {"健康分": health[-1], "满意度": satisfaction[-1],
                 "干预效果": composite[-1] if composite else 5},
                save_name=f"{prefix}_2_radar.png"
            )

        # 3. 因素贡献图
        factor_data = simulation_data.get("factor_contributions", {})
        if days and factor_data:
            figures["factors"] = self.plot_factor_contribution(
                days, factor_data,
                save_name=f"{prefix}_3_factors.png"
            )

        # 4. 相关性散点图
        if health and satisfaction:
            figures["correlation"] = self.plot_correlation_scatter(
                health, satisfaction, days,
                save_name=f"{prefix}_4_correlation.png"
            )

        # 5. 阶段箱线图
        phase_data = simulation_data.get("phase_data", {})
        if phase_data:
            figures["phases"] = self.plot_phase_boxplot(
                phase_data,
                save_name=f"{prefix}_5_phases.png"
            )

        # 6. 热力图
        intervention_matrix = simulation_data.get("intervention_matrix")
        if intervention_matrix is not None:
            row_labels = simulation_data.get("intervention_types",
                                             ["观察", "劝说", "移除物品", "锁定空间"])
            col_labels = simulation_data.get("result_dimensions",
                                             ["健康分变化", "满意度变化", "遵从率"])
            figures["heatmap"] = self.plot_intervention_heatmap(
                intervention_matrix, row_labels, col_labels,
                save_name=f"{prefix}_6_heatmap.png"
            )

        # 7. 综合仪表盘
        figures["dashboard"] = self.plot_comprehensive_dashboard(
            simulation_data,
            save_name=f"{prefix}_7_dashboard.png"
        )

        # 8. 面积图
        if days and health and satisfaction:
            figures["area"] = self.plot_area_chart(
                days, {"健康分": health, "满意度": satisfaction},
                save_name=f"{prefix}_8_area.png"
            )

        print(f"\n生成了 {len(figures)} 张论文图表:")
        for name, path in figures.items():
            print(f"  - {name}: {path}")

        return figures
