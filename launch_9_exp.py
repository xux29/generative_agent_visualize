#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Launch 9 diabetes experiments in parallel"""
import os, subprocess, sys, json, time

EXPERIMENTS = [
    (90, 'low'), (90, 'medium'), (90, 'high'),
    (75, 'low'), (75, 'medium'), (75, 'high'),
    (60, 'low'), (60, 'medium'), (60, 'high'),
]

os.chdir('e:/data/pythoncode/GenerativeAgentsCN/generative_agents')

with open('data/config_health.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
api_keys = config['agent']['think']['llm'].get('api_keys', [config['agent']['think']['llm']['api_key']])

for i, (init_health, discipline) in enumerate(EXPERIMENTS, 1):
    name = f'init{init_health}_{discipline}_20260506'

    temp_config_path = f'data/config_health_temp_{i}.json'
    with open('data/config_health.json', 'r', encoding='utf-8') as f:
        temp_config = json.load(f)
    temp_config['agent']['think']['llm']['api_key'] = api_keys[(i-1) % len(api_keys)]
    with open(temp_config_path, 'w', encoding='utf-8') as f:
        json.dump(temp_config, f, indent=2, ensure_ascii=False)

    cmd = [sys.executable, 'start_health_simulation.py',
           '--scenario', 'diabetes', '--days', '90',
           '--initial-health', str(init_health), '--discipline', discipline,
           '--scoring', 'nonlinear', '--batch', '--name', name,
           '--config', temp_config_path]

    subprocess.Popen(cmd)
    print(f'[{i}/9] {name}')
    time.sleep(1)

print('All launched')