"""
任务数据模型：封装单个剧本生成任务的参数快照与运行状态。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPhase(Enum):
    IDLE = "idle"
    OUTLINE = "outline"
    PROFILE = "profile"
    EPISODES = "episodes"


@dataclass
class TaskState:
    """可变运行状态（工作线程写，主线程读）。"""
    status: TaskStatus = TaskStatus.PENDING
    phase: TaskPhase = TaskPhase.IDLE
    current_episode: int = 0
    total_episodes: int = 0
    drama_title: str = ""
    outline: str = ""
    character_profile: str = ""
    narrator_voice: str = ""
    parsed_profiles: dict[str, str] = field(default_factory=dict)
    episode_texts: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class Task:
    """一个完整的剧本生成任务。"""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    slots: dict = field(default_factory=dict)
    custom_templates: dict = field(default_factory=dict)
    model: str = ""
    summary: str = ""
    state: TaskState = field(default_factory=TaskState)

    @property
    def progress(self) -> float:
        """计算当前进度 0.0~1.0。"""
        s = self.state
        if s.status == TaskStatus.COMPLETED:
            return 1.0
        if s.status == TaskStatus.PENDING:
            return 0.0
        if s.phase == TaskPhase.OUTLINE:
            return 0.05
        if s.phase == TaskPhase.PROFILE:
            return 0.15
        if s.phase == TaskPhase.EPISODES:
            total = s.total_episodes or 1
            done = len(s.episode_texts)
            return 0.2 + 0.8 * (done / total)
        return 0.0


def build_task_summary(slots: dict) -> str:
    """从参数快照生成简短摘要，如 '猫·逆袭·重生复仇'。"""
    parts = []
    char_type = slots.get("character_type", "")
    if char_type:
        # 取第一个角色（可能有多个用「、」分隔）
        first = char_type.split("、")[0]
        parts.append(first)
    style = slots.get("style", "")
    if style:
        parts.append(style)
    plot = slots.get("plot", "")
    if plot:
        parts.append(plot)
    return "·".join(parts) if parts else "未命名任务"


def safe_filename(name: str) -> str:
    """将字符串转为安全的文件/目录名。"""
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    # 去除首尾空白和点
    name = name.strip().strip(".")
    return name or "未命名"
