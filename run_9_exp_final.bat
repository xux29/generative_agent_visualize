@echo off
chcp 65001 >nul
cd /d E:\data\pythoncode\GenerativeAgentsCN\generative_agents

:: 激活conda环境
call D:\software\anaconda\Scripts\activate.bat generative_agents_cn

echo Environment activated
echo.

:: 配置
set SCENARIO=diabetes
set DAYS=90
set SCORING=nonlinear
set TIMESTAMP=20260506

:: 读取API keys
for /f "delims=" %%i in ('python -c "import json; c=json.load(open('data/config_health.json', encoding='utf-8')); keys=c['agent']['think']['llm'].get('api_keys', [c['agent']['think']['llm']['api_key']]); print(' '.join(keys))"') do set API_KEYS=%%i

echo Using API keys: %API_KEYS%
echo.

:: 9个实验
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 90 --discipline low --scoring %SCORING% --batch --name init90_low_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 90 --discipline medium --scoring %SCORING% --batch --name init90_medium_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 90 --discipline high --scoring %SCORING% --batch --name init90_high_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 75 --discipline low --scoring %SCORING% --batch --name init75_low_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 75 --discipline medium --scoring %SCORING% --batch --name init75_medium_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 75 --discipline high --scoring %SCORING% --batch --name init75_high_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 60 --discipline low --scoring %SCORING% --batch --name init60_low_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 60 --discipline medium --scoring %SCORING% --batch --name init60_medium_%TIMESTAMP%"
start cmd /c "python start_health_simulation.py --scenario %SCENARIO% --days %DAYS% --initial-health 60 --discipline high --scoring %SCORING% --batch --name init60_high_%TIMESTAMP%"

echo All 9 experiments started!
echo Check progress: python -c "import os; print([n for n in os.listdir('results/health/diabetes') if '20260506' in n])"
pause