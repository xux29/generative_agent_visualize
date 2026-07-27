# Script to run 9 experiments with nonlinear scoring, batch mode, and parallel execution
import subprocess
import sys

# The command to run:
# python start_health_simulation.py --scenario diabetes --days 45 --run-all --batch --scoring nonlinear --parallel 11

cmd = [
    sys.executable,
    "start_health_simulation.py",
    "--scenario", "diabetes",
    "--days", "45",
    "--run-all",
    "--batch",
    "--scoring", "nonlinear",
    "--parallel", "11"
]

print("=" * 70)
print("Running 9 experiments with:")
print("  - Scenario: diabetes")
print("  - Days: 45")
print("  - Scoring: nonlinear")
print("  - Batch mode: enabled (~10x speedup)")
print("  - Parallel workers: 11")
print("=" * 70)
print()

result = subprocess.run(cmd, cwd="E:/data/pythoncode/GenerativeAgentsCN/generative_agents")

sys.exit(result.returncode)