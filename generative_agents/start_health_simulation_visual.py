"""Health Management Simulation with Visual Position Updates

扩展基础 HealthSimulation 类，支持实时位置更新和寻路系统。
Agent 会根据意图和干预在地图上移动。

独立的健康模拟 Pipeline（不影响原有的 start.py / compress.py / replay.py）：
    start_health_simulation_visual.py  -> 运行模拟，生成 checkpoints
    compress_health.py                 -> 压缩数据，生成 movement.json
    replay_health.py                   -> 可视化服务器（端口 5001）

Usage:
    # 1. 运行模拟
    python start_health_simulation_visual.py --scenario phone-addiction --days 45

    # 2. 恢复中断的模拟
    python start_health_simulation_visual.py --scenario phone-addiction --resume

    # 3. 压缩数据
    python compress_health.py --list                    # 查看可用运行
    python compress_health.py --scenario phone-addiction  # 压缩最新运行

    # 4. 可视化
    python replay_health.py
    # Open: http://127.0.0.1:5001/

Data Structure:
    results/health/{scenario}/{experiment}_{timestamp}/
        ├── checkpoints/          # Checkpoint files for replay
        ├── simulation.log        # Simulation log
        └── simulation_state.json # Resume state

    results/compressed/health-{scenario}-{run_name}/
        ├── movement.json         # Movement data with health info
        └── simulation.md         # Timeline report
"""

import os
import sys
import copy
import json
import random
import argparse
import datetime
from pathlib import Path

# Add parent directory to path for proper imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv, find_dotenv
    from start_health_simulation import HealthSimulation
    from modules.game import get_game
    from modules import utils
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure the conda environment is activated:")
    print("  conda activate generative_agents_cn")
    sys.exit(1)


class HealthSimulationVisual(HealthSimulation):
    """Visual version of Health Simulation with position updates and pathfinding"""

    def __init__(self, *args, **kwargs):
        """Initialize the visual health simulation"""
        super().__init__(*args, **kwargs)
        self.logger.info("Visual mode enabled - agents will move on the map")

    def _move_agent_to_location(self, agent, location_keyword):
        """Use pathfinding to move agent to target location

        Args:
            agent: The agent to move
            location_keyword: Keyword for target location (e.g., "厨房", "kitchen")
        """
        # Map keywords to semantic location types
        location_map = {
            "厨房": "kitchen",
            "kitchen": "kitchen",
            "卧室": "bedroom",
            "bedroom": "bedroom",
            "床": "bedroom",
            "bed": "bedroom",
            "客厅": "living_room",
            "living": "living_room",
            "沙发": "living_room",
            "sofa": "living_room",
            "电视": "living_room",
            "tv": "living_room",
            "冰箱": "kitchen",
            "fridge": "kitchen",
            "柜台": "counter",
            "counter": "counter",
            "卫生间": "bathroom",
            "bathroom": "bathroom",
            "厕所": "bathroom",
        }

        # Find semantic key from keyword
        semantic_key = None
        for keyword, key in location_map.items():
            if keyword in location_keyword.lower():
                semantic_key = key
                break

        if not semantic_key:
            self.logger.debug(f"No semantic location found for '{location_keyword}'")
            return

        # Get target addresses from scenario config
        target_addresses = self.scenario.get_location_addresses(semantic_key)
        if not target_addresses:
            self.logger.debug(f"No addresses found for location type '{semantic_key}'")
            return

        # Get target coordinate from first matching address
        target_address = target_addresses[0]
        target_tiles = self.game.maze.get_address_tiles(target_address)

        if not target_tiles:
            self.logger.debug(f"No tiles found for address {target_address}")
            return

        # Pick a random tile from available tiles
        target_coord = random.choice(list(target_tiles))

        # Only move if not already at target
        current_coord = list(agent.coord) if agent.coord else [0, 0]
        if current_coord == list(target_coord):
            self.logger.debug(f"{agent.name} already at {location_keyword}")
            return

        # Calculate path using A* pathfinding
        path = self.game.maze.find_path(current_coord, list(target_coord))

        if path and len(path) > 0:
            # Move agent to target
            agent.move(target_coord, path)

            # Update action event address
            if hasattr(agent, 'action') and hasattr(agent.action, 'event'):
                agent.action.event.address = target_address

            self.logger.debug(
                f"{agent.name} moved from {current_coord} to {target_coord} "
                f"({location_keyword}), path length: {len(path)}"
            )
        else:
            self.logger.debug(
                f"No path found for {agent.name} from {current_coord} to {target_coord}"
            )

    def _move_agent_toward(self, agent, target_agent):
        """Move manager agent toward target agent for intervention

        Args:
            agent: The manager agent to move
            target_agent: The target agent to approach
        """
        if not agent or not target_agent:
            return

        current_coord = list(agent.coord) if agent.coord else [0, 0]
        target_coord = list(target_agent.coord) if target_agent.coord else [0, 0]

        if current_coord == target_coord:
            self.logger.debug(f"{agent.name} already at {target_agent.name}'s location")
            return

        # Find path to target
        path = self.game.maze.find_path(current_coord, target_coord)

        if path and len(path) > 1:
            # Stop one tile before target to avoid overlap
            dest = path[-2] if len(path) > 1 else path[-1]
            agent.move(dest, path[:-1] if len(path) > 1 else path)

            self.logger.debug(
                f"{agent.name} moved toward {target_agent.name}, "
                f"from {current_coord} to {dest}"
            )
        elif path and len(path) == 1:
            # Already adjacent
            self.logger.debug(f"{agent.name} already adjacent to {target_agent.name}")
        else:
            self.logger.debug(
                f"No path found for {agent.name} to reach {target_agent.name}"
            )

    def _save_checkpoint(self, current_time, intention=None, strategy=None):
        """Save checkpoint with health data for visualization

        Extends parent method to include additional health visualization data.
        """
        # Build checkpoint data compatible with compress.py / replay.py
        checkpoint_data = copy.deepcopy(self.config)

        # Update agent states
        if "agents" not in checkpoint_data:
            checkpoint_data["agents"] = {}

        for name, agent in self.game.agents.items():
            if name not in checkpoint_data["agents"]:
                checkpoint_data["agents"][name] = {}

            # Save agent state for replay
            agent_dict = agent.to_dict()
            checkpoint_data["agents"][name].update(agent_dict)
            checkpoint_data["agents"][name]["coord"] = list(agent.coord) if agent.coord else [0, 0]

            # Update action event to reflect current activity
            if name == self.target_name and intention:
                checkpoint_data["agents"][name]["action"]["event"]["describe"] = intention.activity
                checkpoint_data["agents"][name]["action"]["event"]["predicate"] = "正在"
                checkpoint_data["agents"][name]["action"]["event"]["object"] = intention.activity
            elif name == self.manager_name and strategy and strategy.level > 0:
                checkpoint_data["agents"][name]["action"]["event"]["describe"] = strategy.action
                checkpoint_data["agents"][name]["action"]["event"]["predicate"] = "正在执行"
                checkpoint_data["agents"][name]["action"]["event"]["object"] = strategy.action

            # Add health data for visualization
            if name == self.target_name:
                checkpoint_data["agents"][name]["health_data"] = {
                    "score": self.cumulative_health_scorer.current_score,
                    "zone": self.cumulative_health_scorer.get_health_status(),
                    "day": self.current_day,
                    "tide_phase": self.cumulative_health_scorer.get_tide_phase(),
                    "discipline": self.discipline_level,
                }

        # Add intervention data
        checkpoint_data["intervention"] = {
            "level": strategy.level if strategy else 0,
            "action": strategy.action if strategy else "",
            "reason": strategy.reason if strategy else "",
        }

        # Add cumulative health summary
        checkpoint_data["health_summary"] = self.cumulative_health_scorer.get_summary()

        # Add time and step info
        time_str = current_time.strftime("%Y%m%d-%H:%M")
        checkpoint_data["time"] = time_str
        checkpoint_data["step"] = self.step_counter
        checkpoint_data["stride"] = 30  # 30 minutes per checkpoint
        checkpoint_data["day"] = self.current_day

        # Save checkpoint file
        checkpoint_file = f"{self.checkpoints_folder}/simulate-{time_str.replace(':', '')}.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

        # Save health conversation to game.conversation for replay
        if intention and strategy:
            self._add_health_conversation(time_str, intention, strategy)

        # Save conversation data
        conversation_file = f"{self.checkpoints_folder}/conversation.json"
        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(self.game.conversation, f, ensure_ascii=False, indent=2)


def main():
    """Main entry point for visual health simulation"""
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(
        description="Run health simulation with visual position updates"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="phone-addiction",
        help="Scenario name (e.g., phone-addiction, weight-loss, diabetes)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=45,
        help="Number of days to simulate (default: 45)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use batch mode for faster simulation"
    )
    parser.add_argument(
        "--initial-health",
        type=int,
        default=75,
        choices=[60, 75, 90],
        help="Initial health score (60/75/90)"
    )
    parser.add_argument(
        "--discipline",
        type=str,
        default="medium",
        choices=["low", "medium", "high"],
        help="Self-discipline level"
    )
    parser.add_argument(
        "--verbose",
        type=str,
        default="info",
        choices=["debug", "info"],
        help="Logging level"
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Health Simulation (Visual Mode)")
    print(f"{'='*60}")
    print(f"Scenario: {args.scenario}")
    print(f"Days: {args.days}")
    print(f"Initial Health: {args.initial_health}")
    print(f"Discipline: {args.discipline}")
    print(f"Resume: {args.resume}")
    print(f"Batch Mode: {args.batch}")
    print(f"{'='*60}\n")

    # Create and run simulation
    sim = HealthSimulationVisual(
        scenario_name=args.scenario,
        days=args.days,
        verbose=args.verbose,
        initial_health=args.initial_health,
        discipline_level=args.discipline,
        resume_mode=args.resume,
    )

    sim.initialize()
    sim.run(resume=args.resume, batch_mode=args.batch)

    # Get the run name for output instructions
    run_name = sim.result_path.name  # e.g., init75_medium_20260130_162408

    print(f"\n{'='*60}")
    print(f"Simulation Complete!")
    print(f"{'='*60}")
    print(f"Results saved to: {sim.result_path}")
    print(f"\nTo visualize:")
    print(f"  1. List runs:  python compress_health.py --list")
    print(f"  2. Compress:   python compress_health.py --scenario {args.scenario} --run {run_name}")
    print(f"  3. Replay:     python replay_health.py")
    print(f"     Open: http://127.0.0.1:5001/?name=health-{args.scenario}-{run_name}")
    print(f"\nOr compress the latest run:")
    print(f"  python compress_health.py --scenario {args.scenario}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
