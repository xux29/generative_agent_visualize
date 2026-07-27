#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Launch 9 diabetes experiments in batches of 3"""
import os
import subprocess
import json
import time

os.chdir('e:/data/pythoncode/GenerativeAgentsCN/generative_agents')

PYTHON = 'D:/software/anaconda/envs/generative_agents_cn/python.exe'

with open('data/config_health.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
api_keys = config['agent']['think']['llm'].get('api_keys', [config['agent']['think']['llm']['api_key']])

EXPERIMENTS = [
    (90, 'low'), (90, 'medium'), (90, 'high'),
    (75, 'low'), (75, 'medium'), (75, 'high'),
    (60, 'low'), (60, 'medium'), (60, 'high'),
]

def launch_batch(batch):
    processes = []
    for i, (init_health, discipline) in enumerate(batch, 1):
        name = f'init{init_health}_{discipline}_20260507'

        temp_config_path = f'data/config_health_temp_{i}.json'
        with open('data/config_health.json', 'r', encoding='utf-8') as f:
            temp_config = json.load(f)
        temp_config['agent']['think']['llm']['api_key'] = api_keys[(i-1) % len(api_keys)]
        with open(temp_config_path, 'w', encoding='utf-8') as f:
            json.dump(temp_config, f, indent=2, ensure_ascii=False)

        cmd = [
            PYTHON,
            'start_health_simulation.py',
            '--scenario', 'diabetes',
            '--days', '90',
            '--initial-health', str(init_health),
            '--discipline', discipline,
            '--scoring', 'nonlinear',
            '--batch',
            '--config', temp_config_path,
        ]

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        p = subprocess.Popen(cmd, startupinfo=startupinfo)
        print(f'  Launched {name} (PID={p.pid})')
        processes.append((name, p))
    return processes

def wait_for_completion(processes, check_interval=60):
    """Wait for all processes to complete"""
    print('  Waiting for completion...')
    while True:
        all_done = True
        for name, p in processes:
            if p.poll() is None:
                all_done = False
                break
        if all_done:
            break
        time.sleep(check_interval)
        # Check progress
        base = 'e:/data/pythoncode/GenerativeAgentsCN/generative_agents/results/health/diabetes'
        for name, _ in processes:
            state = os.path.join(base, name, 'simulation_state.json')
            if os.path.exists(state):
                with open(state, encoding='utf-8') as f:
                    d = json.load(f)
                print(f'    {name}: day {d.get("current_day", "?")}/90')
        print('  --')
    print('  All batch complete!')

# Run in batches of 3
for batch_idx in range(3):
    start = batch_idx * 3
    end = start + 3
    batch = EXPERIMENTS[start:end]

    print(f'\n=== BATCH {batch_idx + 1}/3 ===')
    print(f'Running: {[f"init{i}_{d}" for i,d in batch]}')

    processes = launch_batch(batch)
    wait_for_completion(processes)

    print(f'\nBatch {batch_idx + 1} complete!\n')

print('\n=== ALL 9 EXPERIMENTS COMPLETE ===')
print('Running analyze_health...')

# Run analyze
cmd = [PYTHON, 'analyze_health.py', '--scenario', 'diabetes']
subprocess.run(cmd)