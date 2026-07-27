@echo off
chcp 65001 >nul
cd /d E:\data\pythoncode\GenerativeAgentsCN\generative_agents
title Diabetes 初始分60 自律对比

echo ========================================
echo 糖尿病场景 - 初始分60 自律程度低/中/高
echo ========================================
echo.

echo 启动3个实验: init60_low, init60_medium, init60_high
echo.

call conda run -n generative_agents_cn python start_health_simulation.py --scenario diabetes --days 45 --run-all --batch --scoring nonlinear --parallel 3

echo.
echo ========================================
echo 实验完成！
echo ========================================
pause