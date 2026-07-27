@echo off
cd /d E:\data\pythoncode\GenerativeAgentsCN\generative_agents
call conda run -n generative_agents_cn python start_health_simulation.py --scenario diabetes --days 45 --run-all --batch --scoring nonlinear --parallel 11