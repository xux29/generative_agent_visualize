"""Health Simulation Data Compression for Visualization

独立的健康模拟数据压缩脚本，不影响原有的 compress.py。

Usage:
    # List all available scenarios and runs
    python compress_health.py --list

    # Compress the latest run of a scenario
    python compress_health.py --scenario phone-addiction

    # Compress a specific run
    python compress_health.py --scenario phone-addiction --run init75_medium_20260130_162408

    # Replay with health visualization (使用独立的 replay_health.py)
    python replay_health.py
    # Open: http://127.0.0.1:5001/?name=health-phone-addiction-init75_medium_20260130_162408

Output Structure:
    results/compressed/health-{scenario}-{run_name}/
        ├── movement.json    # Movement data with health visualization fields
        └── simulation.md    # Timeline markdown report

Pipeline (独立于原有流程):
    start_health_simulation_visual.py  -> results/health/{scenario}/{run}/
    compress_health.py                 -> results/compressed/health-{scenario}-{run}/
    replay_health.py                   -> http://127.0.0.1:5001/
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Add parent directory to path for proper imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from modules.maze import Maze
    from compress import (
        frames_per_step,
        file_markdown,
        file_movement,
        get_stride,
        get_maze_path,
        get_location,
        insert_frame0,
        generate_report
    )
except ImportError as e:
    print(f"Warning: Import error - {e}")
    print("Please ensure the conda environment is activated:")
    print("  conda activate generative_agents_cn")
    sys.exit(1)


def _format_profile(profile, role_type):
    """Format profile information for display in agent details.

    Args:
        profile: Profile dict from semantic_mapping.json
        role_type: "target" or "manager"

    Returns:
        Formatted string for display
    """
    if not profile:
        return ""

    parts = []

    # Name and basic info
    name = profile.get("name", "")
    age = profile.get("age", "")
    gender = profile.get("gender", "")

    if name:
        basic_info = name
        if age:
            basic_info += f"，{age}岁"
        if gender:
            basic_info += f"，{gender}"
        parts.append(basic_info)

    # Personality
    personality = profile.get("personality", "")
    if personality:
        parts.append(f"性格：{personality}")

    # Background
    background = profile.get("background", "")
    if background:
        parts.append(f"背景：{background}")

    # Health condition (for target)
    health_condition = profile.get("health_condition", "")
    if health_condition:
        parts.append(f"健康状况：{health_condition}")

    # Role-specific info
    if role_type == "target":
        motivation = profile.get("motivation", "")
        if motivation:
            parts.append(f"动机：{motivation}")
    elif role_type == "manager":
        intervention_approach = profile.get("intervention_approach", "")
        if intervention_approach:
            parts.append(f"干预方式：{intervention_approach}")

    return "。".join(parts) if parts else ""


def generate_movement_health(checkpoints_folder, compressed_folder, compressed_file, scenario=None):
    """Generate movement.json with health data for visualization

    Extends the standard generate_movement to include:
    - health_score: Current cumulative health score
    - health_zone: Health status zone (SAFE, NORMAL, WARNING, DANGER, EMERGENCY)
    - day: Current simulation day
    - intervention_level: Current intervention level (0-3)
    - intervention_action: Current intervention action text
    - tide_phase: Current tide phase from nonlinear scorer
    """
    movement_file = os.path.join(compressed_folder, compressed_file)

    # Load semantic mapping for profile information
    semantic_mapping = {}
    semantic_mapping_path = os.path.join(os.path.dirname(__file__), "data", "semantic_mapping.json")
    if os.path.exists(semantic_mapping_path):
        with open(semantic_mapping_path, "r", encoding="utf-8") as f:
            semantic_mapping = json.load(f)

    conversation_file = "conversation.json"
    conversation = {}
    if os.path.exists(os.path.join(checkpoints_folder, conversation_file)):
        with open(os.path.join(checkpoints_folder, conversation_file), "r", encoding="utf-8") as f:
            conversation = json.load(f)

    files = sorted(os.listdir(checkpoints_folder))
    json_files = []
    for file_name in files:
        if file_name.endswith(".json") and file_name != conversation_file:
            json_files.append(os.path.join(checkpoints_folder, file_name))

    if not json_files:
        print(f"No checkpoint files found in {checkpoints_folder}")
        return None

    persona_init_pos = {}
    all_movement = {}
    all_movement["description"] = {}
    all_movement["conversation"] = {}

    stride = get_stride(json_files)
    sec_per_step = stride

    # Get maze path (supports different maps)
    maze_rel_path = get_maze_path(json_files)
    map_folder = maze_rel_path.split("/")[0] if "/" in maze_rel_path else "village"

    result = {
        "start_datetime": "",
        "stride": stride,
        "sec_per_step": sec_per_step,
        "persona_init_pos": persona_init_pos,
        "all_movement": all_movement,
        "map_folder": map_folder,
        "is_health_simulation": True,  # Flag for health template
    }

    last_location = {}

    # Load maze for pathfinding
    json_path = f"frontend/static/assets/{maze_rel_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
        maze = Maze(json_data, None)

    # Track health data for visualization
    current_day = 0
    current_health_score = 75.0  # Default initial
    current_health_zone = "NORMAL"
    current_intervention_level = 0
    current_intervention_action = ""
    current_tide_phase = "normal"

    total_files = len(json_files)
    for file_idx, file_name in enumerate(json_files):
        print(f"  Processing checkpoint {file_idx + 1}/{total_files}: {os.path.basename(file_name)}")
        with open(file_name, "r", encoding="utf-8") as f:
            json_data = json.load(f)
            step = json_data["step"]
            agents = json_data["agents"]

            # Extract health data from checkpoint
            if "day" in json_data:
                current_day = json_data["day"]

            if "health_summary" in json_data:
                health_summary = json_data["health_summary"]
                current_health_score = health_summary.get("current_score", current_health_score)
                current_health_zone = health_summary.get("health_status", current_health_zone)
                current_tide_phase = health_summary.get("tide_phase", current_tide_phase)

            if "intervention" in json_data:
                intervention = json_data["intervention"]
                current_intervention_level = intervention.get("level", 0)
                current_intervention_action = intervention.get("action", "")

            # Save start datetime
            if len(result["start_datetime"]) < 1:
                t = datetime.strptime(json_data["time"], "%Y%m%d-%H:%M")
                result["start_datetime"] = t.isoformat()

            for agent_name, agent_data in agents.items():
                # Insert frame 0
                if step == 1:
                    insert_frame0(persona_init_pos, all_movement, agent_name, map_folder)

                    # Fill description from semantic_mapping profile
                    if scenario and scenario in semantic_mapping:
                        scenario_config = semantic_mapping[scenario]
                        target_agent = scenario_config.get("target_agent", "")
                        manager_agent = scenario_config.get("manager_agent", "")

                        if agent_name == target_agent:
                            profile = scenario_config.get("target_profile", {})
                            all_movement["description"][agent_name] = {
                                "currently": _format_profile(profile, "target")
                            }
                        elif agent_name == manager_agent:
                            profile = scenario_config.get("manager_profile", {})
                            all_movement["description"][agent_name] = {
                                "currently": _format_profile(profile, "manager")
                            }

                # Get source coordinate
                if agent_name in last_location:
                    source_coord = last_location[agent_name]["movement"]
                elif "0" in all_movement and agent_name in all_movement["0"]:
                    source_coord = all_movement["0"][agent_name]["movement"]
                else:
                    # Fallback: use target coord as source
                    source_coord = agent_data["coord"]

                target_coord = agent_data["coord"]

                # Ensure coords are tuples for find_path
                if isinstance(source_coord, list):
                    source_coord = tuple(source_coord)
                if isinstance(target_coord, list):
                    target_coord = tuple(target_coord)

                location = get_location(agent_data["action"]["event"]["address"])

                if location is None:
                    if agent_name in last_location:
                        location = last_location[agent_name]["location"]
                    elif "0" in all_movement and agent_name in all_movement["0"]:
                        location = all_movement["0"][agent_name]["location"]
                    else:
                        location = "未知位置"
                    path = [source_coord]
                elif source_coord == target_coord:
                    # No movement needed
                    path = [source_coord]
                else:
                    print(f"    {agent_name}: finding path from {source_coord} to {target_coord}...")
                    try:
                        path = maze.find_path(source_coord, target_coord)
                        print(f"    {agent_name}: path found, length={len(path)}")
                    except Exception as e:
                        print(f"    {agent_name}: find_path error: {e}, using direct path")
                        path = [source_coord, target_coord]

                had_conversation = False
                step_conversation = ""
                persons_in_conversation = []
                step_time = json_data["time"]

                if step_time in conversation:
                    for chats in conversation[step_time]:
                        for persons, chat in chats.items():
                            persons_in_conversation.append(persons.split(" @ ")[0].split(" -> "))
                            step_conversation += f"\n地点：{persons.split(' @ ')[1]}\n\n"
                            for c in chat:
                                agent = c[0]
                                text = c[1]
                                step_conversation += f"{agent}：{text}\n"

                # Get health data for this agent
                agent_health_data = agent_data.get("health_data", {})

                # 检查是否有折返信息
                turnaround = agent_data.get("turnaround")

                if turnaround:
                    # 有折返：生成三段移动
                    blocked_location = turnaround.get("blocked_location", "kitchen_door")
                    redirect_location = turnaround.get("redirect_location", "living_room")
                    block_reason = turnaround.get("block_reason", "被阻止")
                    redirect_activity = turnaround.get("redirect_activity", "看电视")

                    # 获取被阻位置坐标（从semantic_locations获取）
                    blocked_coord = turnaround.get("blocked_at")
                    if not blocked_coord:
                        # 尝试从地图获取
                        blocked_coord = target_coord  # fallback

                    redirect_coord = turnaround.get("redirect_to")
                    if not redirect_coord:
                        redirect_coord = source_coord  # fallback到起始位置

                    # 确保坐标是元组
                    if isinstance(blocked_coord, list):
                        blocked_coord = tuple(blocked_coord)
                    if isinstance(redirect_coord, list):
                        redirect_coord = tuple(redirect_coord)

                    # 生成三段路径
                    try:
                        path1 = maze.find_path(source_coord, blocked_coord) if source_coord != blocked_coord else [source_coord]
                        path2 = maze.find_path(blocked_coord, redirect_coord) if blocked_coord != redirect_coord else [blocked_coord]
                    except Exception as e:
                        print(f"    {agent_name}: turnaround path error: {e}, using direct path")
                        path1 = [source_coord, blocked_coord]
                        path2 = [blocked_coord, redirect_coord]

                    # 帧分配：前往25帧 + 被阻5帧 + 折返30帧
                    frames_going = 25
                    frames_blocked = 5
                    frames_returning = frames_per_step - frames_going - frames_blocked

                    for i in range(frames_per_step):
                        if i < frames_going:
                            # 前往阶段
                            if len(path1) > 0:
                                movement = list(path1[0])
                                if len(path1) > 1:
                                    path1 = path1[1:]
                            else:
                                movement = list(blocked_coord)
                            action = f"前往 {location}"
                            current_location = location
                        elif i < frames_going + frames_blocked:
                            # 被阻阶段
                            movement = list(blocked_coord)
                            action = f"🚫 {block_reason}"
                            current_location = blocked_location
                        else:
                            # 折返阶段
                            if len(path2) > 0:
                                movement = list(path2[0])
                                if len(path2) > 1:
                                    path2 = path2[1:]
                            else:
                                movement = list(redirect_coord)
                            action = f"↩️ {redirect_activity}"
                            current_location = redirect_location

                        if agent_name not in last_location:
                            last_location[agent_name] = {}
                        last_location[agent_name]["movement"] = movement
                        last_location[agent_name]["location"] = current_location

                        step_key = "%d" % ((step - 1) * frames_per_step + 1 + i)
                        if step_key not in all_movement:
                            all_movement[step_key] = {}

                        movement_data = {
                            "location": current_location,
                            "movement": movement,
                            "action": action,
                            "health_score": current_health_score,
                            "health_zone": current_health_zone,
                            "day": current_day,
                            "tide_phase": current_tide_phase,
                            "intervention_level": current_intervention_level,
                            "intervention_action": current_intervention_action,
                            "is_turnaround": True,
                            "turnaround_phase": "going" if i < frames_going else ("blocked" if i < frames_going + frames_blocked else "returning")
                        }
                        all_movement[step_key][agent_name] = movement_data

                else:
                    # 正常处理（无折返）
                    for i in range(frames_per_step):
                        moving = len(path) > 1
                        if len(path) > 0:
                            movement = list(path[0])
                            path = path[1:]
                            if agent_name not in last_location:
                                last_location[agent_name] = {}
                            last_location[agent_name]["movement"] = movement
                            last_location[agent_name]["location"] = location
                        else:
                            movement = None

                        if moving:
                            action = f"前往 {location}"
                        elif movement is not None:
                            action = agent_data["action"]["event"]["describe"]
                            if len(action) < 1:
                                action = f'{agent_data["action"]["event"]["predicate"]}{agent_data["action"]["event"]["object"]}'

                            for persons in persons_in_conversation:
                                if agent_name in persons:
                                    had_conversation = True
                                    break

                            if "睡觉" in action:
                                action = "😴 " + action
                            elif had_conversation:
                                action = "💬 " + action

                        step_key = "%d" % ((step - 1) * frames_per_step + 1 + i)
                        if step_key not in all_movement:
                            all_movement[step_key] = {}

                        if movement is not None:
                            movement_data = {
                                "location": location,
                                "movement": movement,
                                "action": action,
                            }

                            # Add health data for all agents (but especially for target)
                            if agent_health_data:
                                movement_data["health_score"] = agent_health_data.get("score", current_health_score)
                                movement_data["health_zone"] = agent_health_data.get("zone", current_health_zone)
                                movement_data["day"] = agent_health_data.get("day", current_day)
                                movement_data["tide_phase"] = agent_health_data.get("tide_phase", current_tide_phase)
                            else:
                                # Use checkpoint-level health data
                                movement_data["health_score"] = current_health_score
                                movement_data["health_zone"] = current_health_zone
                                movement_data["day"] = current_day
                                movement_data["tide_phase"] = current_tide_phase

                            # Add intervention data
                            movement_data["intervention_level"] = current_intervention_level
                            movement_data["intervention_action"] = current_intervention_action

                            all_movement[step_key][agent_name] = movement_data

                all_movement["conversation"][step_time] = step_conversation

    # Save data
    with open(movement_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"Health movement data saved to {movement_file}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compress health simulation data for visualization"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="",
        help="Scenario name (e.g., phone-addiction)"
    )
    parser.add_argument(
        "--run",
        type=str,
        default="latest",
        help="Run identifier (default: latest, or specific like init75_medium_20260130_162408)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenarios and runs"
    )

    args = parser.parse_args()

    health_root = Path("results/health")

    # List mode: show available scenarios and runs
    if args.list:
        if not health_root.exists():
            print("No health simulation results found.")
            sys.exit(0)

        print("Available health simulations:\n")
        for scenario_dir in sorted(health_root.iterdir()):
            if not scenario_dir.is_dir():
                continue
            print(f"Scenario: {scenario_dir.name}")
            runs = sorted([
                d for d in scenario_dir.iterdir()
                if d.is_dir() and not d.name.endswith("_latest")
            ], key=lambda x: x.stat().st_mtime, reverse=True)
            for run in runs:
                # Check if this is the latest
                is_latest = (scenario_dir / f"{run.name.rsplit('_', 1)[0]}_latest").resolve() == run
                latest_mark = " (latest)" if is_latest else ""
                checkpoint_count = len(list((run / "checkpoints").glob("simulate-*.json"))) if (run / "checkpoints").exists() else 0
                print(f"  - {run.name}{latest_mark} [{checkpoint_count} checkpoints]")
            print()
        sys.exit(0)

    # Normal mode: compress a specific run
    scenario = args.scenario
    if len(scenario) < 1:
        scenario = input("Please enter a scenario name: ")

    # Find the health simulation results
    # Structure: results/health/{scenario}/{experiment}_{timestamp}/checkpoints
    health_base = health_root / scenario

    if not health_base.exists():
        print(f"Health simulation results not found: {health_base}")
        print("\nAvailable scenarios:")
        if health_root.exists():
            for d in health_root.iterdir():
                if d.is_dir():
                    print(f"  - {d.name}")
        print("\nUse --list to see all available runs.")
        sys.exit(1)

    # Find the run directory
    if args.run == "latest":
        # Find directories ending with _latest (symlinks)
        latest_dirs = list(health_base.glob("*_latest"))
        if latest_dirs:
            run_dir = latest_dirs[0]
            if run_dir.is_symlink():
                run_dir = run_dir.resolve()
            run_name = run_dir.name
        else:
            # Find most recent run by modification time
            runs = sorted(
                [d for d in health_base.iterdir() if d.is_dir() and not d.name.endswith("_latest")],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if runs:
                run_dir = runs[0]
                run_name = run_dir.name
            else:
                print(f"No runs found in {health_base}")
                print("Use --list to see available runs.")
                sys.exit(1)
    else:
        run_dir = health_base / args.run
        run_name = args.run
        if not run_dir.exists():
            print(f"Run directory not found: {run_dir}")
            print("\nAvailable runs:")
            for d in health_base.iterdir():
                if d.is_dir() and not d.name.endswith("_latest"):
                    print(f"  - {d.name}")
            sys.exit(1)

    checkpoints_folder = run_dir / "checkpoints"
    if not checkpoints_folder.exists():
        print(f"Checkpoints folder not found: {checkpoints_folder}")
        sys.exit(1)

    # Output to compressed folder with scenario AND run identifier
    # Format: health-{scenario}-{run_name}
    output_name = f"health-{scenario}-{run_name}"
    compressed_folder = Path("results/compressed") / output_name
    compressed_folder.mkdir(parents=True, exist_ok=True)

    print(f"Compressing health simulation:")
    print(f"  Scenario: {scenario}")
    print(f"  Run: {run_name}")
    print(f"  Checkpoints: {checkpoints_folder}")
    print(f"  Output: {compressed_folder}")

    # Generate health movement data
    generate_movement_health(str(checkpoints_folder), str(compressed_folder), file_movement, scenario)

    # Generate markdown report (uses standard function)
    generate_report(str(checkpoints_folder), str(compressed_folder), file_markdown)

    print(f"\nCompression completed!")
    print(f"\nTo visualize:")
    print(f"  python replay_health.py")
    print(f"  Open: http://127.0.0.1:5001/?name={output_name}")


if __name__ == "__main__":
    main()
