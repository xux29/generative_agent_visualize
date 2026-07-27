#!/bin/bash
source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || true
conda activate generative_agents_cn

python start_health_simulation.py --scenario diabetes --initial-health 90 --discipline high --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 90 --discipline medium --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 90 --discipline low --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline high --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline medium --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 75 --discipline low --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 60 --discipline high --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 60 --discipline medium --days 90 --batch &
python start_health_simulation.py --scenario diabetes --initial-health 60 --discipline low --days 90 --batch &

wait
