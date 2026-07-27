@echo off
cd /d E:\data\pythoncode\GenerativeAgentsCN\generative_agents
echo Starting 9 experiments with nonlinear scoring and batch mode...
call conda run -n generative_agents_cn python start_health_simulation.py --scenario diabetes --days 90 --run-all --batch --scoring nonlinear --parallel 11
echo Done!