# 糖尿病场景实验 - 初始分60，自律程度低/中/高 (batch模式并行)
import subprocess
import sys
import os
import time
import io

# 修复 Windows UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 配置
SCENARIO = "diabetes"
DAYS = 90
SCORING = "nonlinear"
PARALLEL = 3  # 并行数

# 只运行初始分60的3个实验
EXPERIMENTS = [
    (60, "low"),
    (60, "medium"),
    (60, "high"),
]

os.chdir(r"E:/data/pythoncode/GenerativeAgentsCN/generative_agents")

print("=" * 70)
print("糖尿病场景 - 初始分60 自律程度对比")
print(f"  场景: {SCENARIO}")
print(f"  天数: {DAYS}")
print(f"  评分: {SCORING}")
print(f"  并行: {PARALLEL}")
print("=" * 70)
print()

# 读取API keys
import json
config_path = "data/config_health.json"
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)
api_keys = config["agent"]["think"]["llm"].get("api_keys", [config["agent"]["think"]["llm"]["api_key"]])
print(f"可用API keys: {len(api_keys)} 个\n")

processes = []

# 启动所有子进程
for i, (initial_health, discipline) in enumerate(EXPERIMENTS, 1):
    api_key = api_keys[(i - 1) % len(api_keys)]

    cmd = [
        sys.executable,
        "start_health_simulation.py",
        "--scenario", SCENARIO,
        "--days", str(DAYS),
        "--initial-health", str(initial_health),
        "--discipline", discipline,
        "--scoring", SCORING,
        "--batch",
    ]

    # 创建临时配置文件（分配不同API key）
    temp_config_path = f"data/config_health_temp_init60_{discipline}.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        temp_config = json.load(f)
    temp_config["agent"]["think"]["llm"]["api_key"] = api_key

    with open(temp_config_path, 'w', encoding='utf-8') as f:
        json.dump(temp_config, f, indent=2, ensure_ascii=False)

    print(f"[{i}/3] 启动实验: init{initial_health}_{discipline}")
    print(f"    命令: {' '.join(cmd)}")

    # 启动进程
    p = subprocess.Popen(
        cmd + ["--config", temp_config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    processes.append({
        "idx": i,
        "initial_health": initial_health,
        "discipline": discipline,
        "process": p,
        "start_time": time.time()
    })
    print(f"    PID: {p.pid}")

print()
print("-" * 70)
print("所有进程已启动，等待完成...\n")

# 等待所有进程完成
for p_info in processes:
    p = p_info["process"]
    experiment_name = f"init{p_info['initial_health']}_{p_info['discipline']}"

    # 实时输出
    while True:
        line = p.stdout.readline()
        if not line and p.poll() is not None:
            break
        if line:
            print(f"[{experiment_name}] {line.rstrip()}")

    returncode = p.wait()
    elapsed = time.time() - p_info["start_time"]

    if returncode == 0:
        print(f"✓ 实验 {experiment_name} 完成 (耗时 {elapsed/60:.1f}分钟)")
    else:
        print(f"✗ 实验 {experiment_name} 失败 (返回码: {returncode}, 耗时 {elapsed/60:.1f}分钟)")

print()
print("=" * 70)
print("所有实验完成！")
print("=" * 70)

# 自动运行 analyze_health 生成 CSV
print("\n正在运行 analyze_health 生成 CSV 文件...\n")
analyze_cmd = [
    sys.executable,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "generative_agents", "analyze_health.py"),
    "--scenario", "diabetes",
]
result = subprocess.run(analyze_cmd, capture_output=False)
print("\nanalyze_health 完成！")