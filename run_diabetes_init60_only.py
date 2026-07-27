# 运行糖尿病场景：初始分60，自律程度低/中/高
import subprocess
import sys
import os

# 切换到generative_agents目录
os.chdir(r"E:\data\pythoncode\GenerativeAgentsCN\generative_agents")

# 3个实验: 初始分=60, 自律程度=[low, medium, high]
experiments = [
    (60, "low"),
    (60, "medium"),
    (60, "high"),
]

print("=" * 70)
print("糖尿病场景实验 - 初始分60 vs 自律程度对比")
print("=" * 70)
print()

results = []

for i, (initial_health, discipline) in enumerate(experiments, 1):
    print(f"\n[{i}/3] 启动实验: init{initial_health}_{discipline}")
    print("-" * 50)

    cmd = [
        sys.executable,
        "start_health_simulation.py",
        "--scenario", "diabetes",
        "--initial-health", str(initial_health),
        "--discipline", discipline,
        "--days", "45",
        "--batch",
        "--scoring", "nonlinear",
    ]

    result = subprocess.run(cmd)
    results.append({
        "initial_health": initial_health,
        "discipline": discipline,
        "returncode": result.returncode
    })

    if result.returncode == 0:
        print(f"✓ 实验 init{initial_health}_{discipline} 完成")
    else:
        print(f"✗ 实验 init{initial_health}_{discipline} 失败 (返回码: {result.returncode})")

print("\n" + "=" * 70)
print("汇总:")
print("=" * 70)
for r in results:
    status = "✓ 成功" if r["returncode"] == 0 else "✗ 失败"
    print(f"  init{r['initial_health']}_{r['discipline']}: {status}")

sys.exit(0 if all(r["returncode"] == 0 for r in results) else 1)