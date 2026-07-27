@echo off
chcp 65001 >nul
cd /d E:\data\pythoncode\GenerativeAgentsCN
set PYTHONIOENCODING=utf-8
conda run -n generative_agents_cn python test_api_keys.py