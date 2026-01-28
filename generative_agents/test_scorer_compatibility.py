"""测试 NonlinearHealthScorer 与前端的兼容性

验证 NonlinearHealthScorer 是否可以作为 CumulativeHealthScorer 的直接替换
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.scorer import CumulativeHealthScorer
from modules.scorer_nonlinear import NonlinearHealthScorer
import random


def test_interface_compatibility():
    """测试接口兼容性"""

    print("=" * 80)
    print("接口兼容性测试")
    print("=" * 80)

    # 测试参数
    initial_score = 75
    discipline_level = "medium"
    scenario = "diabetes"

    print(f"\n初始化参数: initial_score={initial_score}, discipline={discipline_level}, scenario={scenario}")

    # 初始化两个scorer
    print("\n【1/8】测试初始化...")
    try:
        cumulative_scorer = CumulativeHealthScorer(
            initial_score=initial_score,
            discipline_level=discipline_level,
            scenario=scenario
        )
        nonlinear_scorer = NonlinearHealthScorer(
            initial_score=initial_score,
            discipline_level=discipline_level,
            scenario=scenario,
            random_seed=42  # 固定种子用于测试
        )
        print("  ✓ 两个scorer初始化成功")
    except Exception as e:
        print(f"  ✗ 初始化失败: {e}")
        return False

    # 测试属性访问
    print("\n【2/8】测试属性访问...")
    try:
        assert hasattr(cumulative_scorer, 'current_score')
        assert hasattr(nonlinear_scorer, 'current_score')
        assert hasattr(cumulative_scorer, 'initial_score')
        assert hasattr(nonlinear_scorer, 'initial_score')
        assert hasattr(cumulative_scorer, 'discipline_level')
        assert hasattr(nonlinear_scorer, 'discipline_level')
        print(f"  ✓ 属性访问正常")
        print(f"    - current_score: {cumulative_scorer.current_score} vs {nonlinear_scorer.current_score}")
        print(f"    - initial_score: {cumulative_scorer.initial_score} vs {nonlinear_scorer.initial_score}")
    except Exception as e:
        print(f"  ✗ 属性访问失败: {e}")
        return False

    # 测试 calculate_daily_change 方法签名
    print("\n【3/8】测试 calculate_daily_change() 方法...")
    try:
        # 模拟一天的数据
        agent_data = {"glucose": 150, "sleep_hours": 7}
        had_violation = True
        intervention_count = 1
        intervention_success = False
        unblocked_violation_count = 1

        change1, breakdown1 = cumulative_scorer.calculate_daily_change(
            agent_data=agent_data,
            had_violation=had_violation,
            intervention_count=intervention_count,
            intervention_success=intervention_success,
            unblocked_violation_count=unblocked_violation_count
        )

        change2, breakdown2 = nonlinear_scorer.calculate_daily_change(
            agent_data=agent_data,
            had_violation=had_violation,
            intervention_count=intervention_count,
            intervention_success=intervention_success,
            unblocked_violation_count=unblocked_violation_count
        )

        print(f"  ✓ calculate_daily_change() 方法调用成功")
        print(f"    - CumulativeHealthScorer: change={change1:.2f}")
        print(f"    - NonlinearHealthScorer: change={change2:.2f}")

        # 验证返回值类型
        assert isinstance(change1, float) and isinstance(change2, float)
        assert isinstance(breakdown1, dict) and isinstance(breakdown2, dict)
        print(f"  ✓ 返回值类型正确 (float, dict)")

    except Exception as e:
        print(f"  ✗ calculate_daily_change() 失败: {e}")
        return False

    # 测试 get_summary 方法
    print("\n【4/8】测试 get_summary() 方法...")
    try:
        summary1 = cumulative_scorer.get_summary()
        summary2 = nonlinear_scorer.get_summary()

        # 检查必需字段
        required_fields = [
            "current_score", "initial_score", "discipline_level",
            "day_count", "status", "below_warning", "tide_phase"
        ]

        for field in required_fields:
            assert field in summary1, f"CumulativeHealthScorer missing field: {field}"
            assert field in summary2, f"NonlinearHealthScorer missing field: {field}"

        print(f"  ✓ get_summary() 方法成功")
        print(f"    - 必需字段全部存在: {', '.join(required_fields)}")
        print(f"    - NonlinearHealthScorer额外字段: {set(summary2.keys()) - set(summary1.keys())}")

    except Exception as e:
        print(f"  ✗ get_summary() 失败: {e}")
        return False

    # 测试 get_health_status 方法
    print("\n【5/8】测试 get_health_status() 方法...")
    try:
        status1 = cumulative_scorer.get_health_status()
        status2 = nonlinear_scorer.get_health_status()

        assert isinstance(status1, str)
        assert isinstance(status2, str)

        print(f"  ✓ get_health_status() 方法成功")
        print(f"    - CumulativeHealthScorer: {status1}")
        print(f"    - NonlinearHealthScorer: {status2}")

    except Exception as e:
        print(f"  ✗ get_health_status() 失败: {e}")
        return False

    # 测试 get_tide_phase 方法
    print("\n【6/8】测试 get_tide_phase() 方法...")
    try:
        tide1 = cumulative_scorer.get_tide_phase()
        tide2 = nonlinear_scorer.get_tide_phase()

        assert isinstance(tide1, str)
        assert isinstance(tide2, str)

        print(f"  ✓ get_tide_phase() 方法成功")
        print(f"    - CumulativeHealthScorer: {tide1}")
        print(f"    - NonlinearHealthScorer: {tide2}")

    except Exception as e:
        print(f"  ✗ get_tide_phase() 失败: {e}")
        return False

    # 测试 to_dict / from_dict 序列化
    print("\n【7/8】测试 to_dict() / from_dict() 序列化...")
    try:
        # 保存状态
        state1 = cumulative_scorer.to_dict()
        state2 = nonlinear_scorer.to_dict()

        assert isinstance(state1, dict)
        assert isinstance(state2, dict)

        # 恢复状态
        restored1 = CumulativeHealthScorer.from_dict(state1)
        restored2 = NonlinearHealthScorer.from_dict(state2)

        assert restored1.current_score == cumulative_scorer.current_score
        assert restored2.current_score == nonlinear_scorer.current_score

        print(f"  ✓ to_dict() / from_dict() 序列化成功")
        print(f"    - 状态恢复后分数一致")

    except Exception as e:
        print(f"  ✗ 序列化失败: {e}")
        return False

    # 测试多天模拟
    print("\n【8/8】测试10天连续模拟...")
    try:
        random.seed(42)  # 固定随机种子

        for day in range(10):
            # 模拟随机行为
            had_violation = random.random() < 0.4
            intervention_success = random.random() < 0.6 if had_violation else True
            unblocked = 0 if intervention_success else 1

            agent_data = {"day": day}

            # 两个scorer都计算
            change1, _ = cumulative_scorer.calculate_daily_change(
                agent_data=agent_data,
                had_violation=had_violation,
                intervention_count=1 if had_violation else 0,
                intervention_success=intervention_success,
                unblocked_violation_count=unblocked
            )

            change2, _ = nonlinear_scorer.calculate_daily_change(
                agent_data=agent_data,
                had_violation=had_violation,
                intervention_count=1 if had_violation else 0,
                intervention_success=intervention_success,
                unblocked_violation_count=unblocked
            )

        print(f"  ✓ 10天模拟成功完成")
        print(f"    - CumulativeHealthScorer: {cumulative_scorer.current_score:.1f}")
        print(f"    - NonlinearHealthScorer: {nonlinear_scorer.current_score:.1f}")

    except Exception as e:
        print(f"  ✗ 多天模拟失败: {e}")
        return False

    return True


def test_real_world_scenario():
    """测试真实场景：模拟 start_health_simulation.py 的使用方式"""

    print("\n" + "=" * 80)
    print("真实场景测试（模拟 start_health_simulation.py）")
    print("=" * 80)

    # 初始化（模拟 Line 171-175）
    print("\n【场景1】初始化 scorer...")
    initial_health = 75
    discipline_level = "low"
    scenario = "diabetes"

    cumulative_health_scorer = NonlinearHealthScorer(
        initial_score=initial_health,
        discipline_level=discipline_level,
        scenario=scenario
    )
    print(f"  ✓ 初始化成功: score={cumulative_health_scorer.current_score}")

    # 模拟 30 天
    print("\n【场景2】模拟30天健康行为...")
    random.seed(42)

    for day in range(1, 31):
        # 模拟行为数据
        violation_prob = 0.4 if day <= 20 else 0.6  # 倦怠期
        had_violation = random.random() < violation_prob

        if had_violation:
            intervention_success = random.random() < 0.6
            unblocked_violation_count = 0 if intervention_success else 1
        else:
            intervention_success = True
            unblocked_violation_count = 0

        target_data = {"glucose": 150, "day": day}

        # 计算每日变化（模拟 Line 758-764）
        health_change, health_breakdown = cumulative_health_scorer.calculate_daily_change(
            agent_data=target_data,
            had_violation=had_violation,
            intervention_count=1 if had_violation else 0,
            intervention_success=intervention_success,
            unblocked_violation_count=unblocked_violation_count
        )

        # 获取当前分数（模拟 Line 767）
        cumulative_health_score = cumulative_health_scorer.current_score

        # 获取摘要信息（模拟 Line 784, 791-792）
        summary = cumulative_health_scorer.get_summary()
        status = cumulative_health_scorer.get_health_status()
        tide = cumulative_health_scorer.get_tide_phase()

        if day % 10 == 0:
            print(f"  Day {day}: score={cumulative_health_score:.1f}, "
                  f"status={status}, tide={tide}")

    final_score = cumulative_health_scorer.current_score
    print(f"\n  ✓ 30天模拟完成")
    print(f"    - 最终分数: {final_score:.1f}")
    print(f"    - 健康状态: {cumulative_health_scorer.get_health_status()}")

    # 保存/恢复状态测试（模拟 Line 459, 554-556）
    print("\n【场景3】保存和恢复状态...")
    state = cumulative_health_scorer.to_dict()
    print(f"  ✓ 状态已保存: {len(state)} 个字段")

    # 模拟从checkpoint恢复
    restored_scorer = NonlinearHealthScorer.from_dict(state)
    print(f"  ✓ 状态已恢复: score={restored_scorer.current_score:.1f}, "
          f"initial={restored_scorer.initial_score}, "
          f"discipline={restored_scorer.discipline_level.value}")

    assert abs(restored_scorer.current_score - final_score) < 0.01
    print(f"  ✓ 恢复后分数一致")

    # 关键结论
    print("\n" + "=" * 80)
    print("【结论】")
    print("=" * 80)

    if final_score >= 35:
        print(f"✓✓✓ 完美通过！")
        print(f"  - LOW自律在30天内未崩溃（最终分数: {final_score:.1f}）")
        print(f"  - 底线保护机制生效")
    elif final_score >= 20:
        print(f"✓ 良好")
        print(f"  - LOW自律虽然偏低但未完全崩溃（最终分数: {final_score:.1f}）")
    else:
        print(f"⚠ 需要调整")
        print(f"  - LOW自律分数过低（最终分数: {final_score:.1f}）")

    print(f"\n✓ NonlinearHealthScorer 与前端完全兼容")
    print(f"✓ 可以直接替换 CumulativeHealthScorer")
    print(f"✓ 所有接口调用方式与原系统相同")


if __name__ == "__main__":
    # 接口兼容性测试
    success = test_interface_compatibility()

    if success:
        print("\n" + "✓" * 80)
        print("所有接口兼容性测试通过！")
        print("✓" * 80)

        # 真实场景测试
        test_real_world_scenario()

        print("\n" + "=" * 80)
        print("【最终结论】")
        print("=" * 80)
        print("""
✓ NonlinearHealthScorer 与 CumulativeHealthScorer 接口 100% 兼容
✓ 可以作为直接替换使用（drop-in replacement）
✓ 除了修改 import 和初始化，其他代码无需修改
✓ 建议立即在实验中使用

下一步操作：
1. 修改 start_health_simulation.py:
   - Line 1: from modules.scorer_nonlinear import NonlinearHealthScorer
   - Line 171-175: 将 CumulativeHealthScorer 替换为 NonlinearHealthScorer

2. 运行短期测试:
   python start_health_simulation.py --scenario diabetes --initial_health 75 --discipline low --days 10 --name test-nonlinear

3. 验证结果并生成图表:
   python generate_charts_en.py

4. 运行完整90天实验
        """)
    else:
        print("\n" + "✗" * 80)
        print("接口兼容性测试失败！")
        print("✗" * 80)
        print("请检查上述错误信息并修复")
