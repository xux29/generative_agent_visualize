@echo off
chcp 65001 >nul
call conda activate generative_agents_cn
cd /d E:\data\pythoncode\GenerativeAgentsCN\generative_agents

python "E:\data\pythoncode\GenerativeAgentsCN\launch_9_exp.py"

echo Experiments launched in background.
pause