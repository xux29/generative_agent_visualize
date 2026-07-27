@echo off
chcp 65001 >nul
cd /d E:\data\pythoncode\GenerativeAgentsCN &&
title Diabetes 初始分60 自律对比 Batch

echo ========================================
echo 糖尿病场景 - 初始分60 自律程度对比
echo ========================================
echo.

call conda run -n generative_agents_cn python run_diabetes_init60_batch.py

echo.
echo ========================================
echo 完成！
echo ========================================
pause