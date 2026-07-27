@echo off
cd /d e:\data\pythoncode\GenerativeAgentsCN\generative_agents
call conda activate generative_agents_cn
python -u start_health_simulation.py --scenario diabetes --initial-health 60 --discipline low --days 3 --batch
