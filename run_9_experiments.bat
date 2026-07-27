@echo off
chcp 65001 >nul
cd /d E:\data\pythoncode\GenerativeAgentsCN\generative_agents
title 9 Experiments - Diabetes Nonlinear

echo ========================================
echo 9个糖尿病场景实验 - 非线性评分系统
echo ========================================
echo.

call conda run -n generative_agents_cn python start_health_simulation.py --scenario diabetes --days 45 --run-all --batch --scoring nonlinear --parallel 9

echo.
echo ========================================
echo 所有实验完成！开始导出CSV...
echo ========================================

rem 导出CSV到可视化文件夹
mkdir "..\可视化" 2>nul

call conda run -n generative_agents_cn python -c "
import sys
sys.path.insert(0, '.')
import analyze_health
import glob

analyzer = analyze_health.HealthAnalyzer(
    results_dir='results/health',
    csv_dir='results/csv'
)

# 查找今天新完成的实验目录
import os
from datetime import datetime
today = datetime.now().strftime('%Y%m%d')

scenario_dir = 'results/health/diabetes'
for exp_dir in os.listdir(scenario_dir):
    if today in exp_dir and 'nonlinear' in exp_dir.lower():
        run_path = os.path.join(scenario_dir, exp_dir)
        results = analyzer.load_results(run_path)
        if results:
            metrics = analyzer.extract_metrics(results)
            if metrics:
                csv_path = analyzer.export_to_csv('diabetes', exp_dir, metrics, 'nonlinear')
                # 复制到可视化文件夹
                viz_path = f'../可视化/{os.path.basename(csv_path)}'
                import shutil
                shutil.copy(csv_path, viz_path)
                print(f'已导出: {viz_path}')
"

echo.
echo ========================================
echo 完成！
echo ========================================
pause
