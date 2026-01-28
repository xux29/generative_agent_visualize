"""generative_agents.intention

意图系统：Target Agent 的行为意图表示
"""

import datetime
from modules import utils


class Intention:
    """表示 Agent 的行为意图"""

    def __init__(self, activity, duration, compliance_threshold=2, inner_monologue="", time_str=""):
        """
        初始化意图

        Args:
            activity: 活动名称，如"玩手机"、"吃零食"
            duration: 持续时间（分钟）
            compliance_threshold: 屈服阈值（1=容易屈服，2=中等，3=很难屈服）
            inner_monologue: 内心独白
            time_str: 时间字符串（批量模式下使用，如"21:00"）
        """
        self.activity = activity
        self.duration = duration
        self.compliance_threshold = compliance_threshold
        self.inner_monologue = inner_monologue
        self.time_str = time_str  # 批量模式下的时间标记

        # 计算结束时间
        current_time = utils.get_timer().get_date()
        self.start_time = current_time
        self.end_time = current_time + datetime.timedelta(minutes=duration)

        # 状态标记
        self.is_locked = False  # 是否被锁定（不可修改）
        self.is_interrupted = False  # 是否被干预打断

    def lock(self):
        """锁定意图，防止并发修改"""
        self.is_locked = True

    def interrupt(self):
        """打断意图"""
        self.is_interrupted = True

    def is_completed(self):
        """检查意图是否已完成"""
        current_time = utils.get_timer().get_date()
        return current_time >= self.end_time or self.is_interrupted

    def remaining_time(self):
        """剩余时间（分钟）"""
        if self.is_completed():
            return 0
        current_time = utils.get_timer().get_date()
        delta = self.end_time - current_time
        return int(delta.total_seconds() / 60)

    def to_dict(self):
        """转换为字典"""
        return {
            "activity": self.activity,
            "duration": self.duration,
            "compliance_threshold": self.compliance_threshold,
            "inner_monologue": self.inner_monologue,
            "start_time": self.start_time.strftime("%H:%M"),
            "end_time": self.end_time.strftime("%H:%M"),
            "is_locked": self.is_locked,
            "is_interrupted": self.is_interrupted
        }

    def __str__(self):
        return f"Intention('{self.activity}', {self.duration}min, threshold={self.compliance_threshold})"
