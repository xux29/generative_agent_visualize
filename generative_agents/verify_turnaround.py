#!/usr/bin/env python3
"""验证折返机制和睡眠计划实现

Usage:
    python verify_turnaround.py [--run RUN_NAME]
"""

import os
import json
import argparse
from pathlib import Path


def verify_day_log(day_file: Path) -> dict:
    """验证单个 day_xx.json 文件"""
    results = {
        "file": day_file.name,
        "sleep_intentions": [],
        "turnaround_events": [],
        "location_issues": [],
        "manager_positions": 0,
        "agent_positions": 0,
        "passed": True,
        "issues": []
    }

    with open(day_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])

    # 1. 检查睡眠意图
    for event in events:
        if event.get("type") == "intention":
            time_str = event.get("time", "")
            content = event.get("content", "")
            target_loc = event.get("target_location")
            is_sleep = event.get("is_sleep_related", False)

            # 检查23:00后是否有睡眠相关意图
            hour = int(time_str.split(":")[0]) if time_str else 0
            if hour >= 23 or hour < 6:
                if "睡" in content or "休息" in content or is_sleep:
                    results["sleep_intentions"].append({
                        "time": time_str,
                        "content": content,
                        "is_sleep_related": is_sleep
                    })

            # 检查位置映射问题
            if "看电视" in content and target_loc == "kitchen":
                results["location_issues"].append({
                    "time": time_str,
                    "content": content,
                    "target_location": target_loc,
                    "issue": "看电视不应该在厨房"
                })
                results["passed"] = False
                results["issues"].append(f"[{time_str}] 位置映射错误: 看电视在厨房")

        # 2. 检查折返事件
        elif event.get("type") == "turnaround":
            results["turnaround_events"].append({
                "time": event.get("time"),
                "original_activity": event.get("original_activity"),
                "block_reason": event.get("block_reason"),
                "redirect_activity": event.get("redirect_activity")
            })

    # 3. 检查位置追踪
    results["agent_positions"] = len(data.get("agent_positions", []))
    results["manager_positions"] = len(data.get("manager_positions", []))

    # 4. 检查折返统计
    turnaround_summary = data.get("turnaround_summary", {})
    if turnaround_summary:
        results["turnaround_count"] = turnaround_summary.get("total_turnarounds", 0)

    return results


def main():
    parser = argparse.ArgumentParser(description="验证折返机制实现")
    parser.add_argument("--run", type=str, default="latest",
                        help="运行目录名 (默认: latest)")
    parser.add_argument("--scenario", type=str, default="weight-loss",
                        help="场景名称 (默认: weight-loss)")
    args = parser.parse_args()

    # 查找运行目录
    health_root = Path("results/health") / args.scenario

    if not health_root.exists():
        print(f"❌ 未找到场景目录: {health_root}")
        print("   请先运行: python start_health_simulation.py --scenario weight-loss --days 3 --batch")
        return

    if args.run == "latest":
        latest_link = list(health_root.glob("*_latest"))
        if latest_link:
            run_dir = latest_link[0].resolve() if latest_link[0].is_symlink() else latest_link[0]
        else:
            runs = sorted([d for d in health_root.iterdir() if d.is_dir() and not d.name.endswith("_latest")],
                         key=lambda x: x.stat().st_mtime, reverse=True)
            run_dir = runs[0] if runs else None
    else:
        run_dir = health_root / args.run

    if not run_dir or not run_dir.exists():
        print(f"❌ 未找到运行目录")
        return

    print(f"📂 验证目录: {run_dir}")
    print("=" * 60)

    # 查找所有 day_xx.json 文件
    day_files = sorted(run_dir.glob("day_*.json"))

    if not day_files:
        print("❌ 未找到 day_xx.json 文件")
        return

    total_sleep = 0
    total_turnarounds = 0
    total_location_issues = 0
    all_passed = True

    for day_file in day_files:
        results = verify_day_log(day_file)

        print(f"\n📅 {results['file']}")
        print(f"   睡眠意图数: {len(results['sleep_intentions'])}")
        print(f"   折返事件数: {len(results['turnaround_events'])}")
        print(f"   位置问题数: {len(results['location_issues'])}")
        print(f"   Agent位置记录: {results['agent_positions']}")
        print(f"   Manager位置记录: {results['manager_positions']}")

        if results['turnaround_events']:
            print(f"   折返详情:")
            for t in results['turnaround_events'][:3]:  # 最多显示3个
                print(f"      [{t['time']}] {t['original_activity']} -> 阻止({t['block_reason']}) -> {t['redirect_activity']}")

        if results['sleep_intentions']:
            print(f"   睡眠意图:")
            for s in results['sleep_intentions'][:2]:  # 最多显示2个
                print(f"      [{s['time']}] {s['content']}")

        if not results['passed']:
            print(f"   ⚠️ 问题: {', '.join(results['issues'])}")
            all_passed = False

        total_sleep += len(results['sleep_intentions'])
        total_turnarounds += len(results['turnaround_events'])
        total_location_issues += len(results['location_issues'])

    print("\n" + "=" * 60)
    print("📊 总结")
    print(f"   总睡眠意图: {total_sleep}")
    print(f"   总折返事件: {total_turnarounds}")
    print(f"   总位置问题: {total_location_issues}")

    if all_passed and total_location_issues == 0:
        print("\n✅ 验证通过!")
    else:
        print("\n⚠️ 存在问题，请检查上述详情")

    # 提示下一步
    print("\n💡 下一步:")
    print(f"   1. 压缩数据: python compress_health.py --scenario {args.scenario}")
    print(f"   2. 可视化: python replay_health.py")
    print(f"   3. 打开: http://127.0.0.1:5001/?name=health-{args.scenario}-{run_dir.name}")


if __name__ == "__main__":
    main()
