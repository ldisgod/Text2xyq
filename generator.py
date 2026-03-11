"""
剧本生成编排模块：协调模板渲染与 LLM 调用。
"""
from __future__ import annotations

import templates
from llm_client import LLMClient, LLMError  # noqa: F401


def build_character_profile_messages(
    slots: dict,
    outline: str,
    custom_templates: dict | None = None,
) -> list[dict]:
    """构建角色视觉档案生成所需的 messages 列表。"""
    ctx = templates.build_context(slots)
    ctx["outline"] = outline
    system = templates.render("character_profile_system", ctx, custom_templates)
    user = templates.render("character_profile_user", ctx, custom_templates)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_outline_messages(
    slots: dict,
    custom_templates: dict | None = None,
) -> list[dict]:
    """构建大纲生成所需的 messages 列表。"""
    ctx = templates.build_context(slots)
    system = templates.render("outline_system", ctx, custom_templates)
    user = templates.render("outline_user", ctx, custom_templates)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_single_episode_messages(
    slots: dict,
    outline: str,
    attempt: int = 0,
    custom_templates: dict | None = None,
) -> list[dict]:
    """构建单集分镜脚本生成所需的 messages 列表，支持重试。

    attempt=0 为首次生成；attempt>0 时 slots 中应包含 previous_count 字段，
    用于生成字数不符时的重试提示。
    """
    ctx = templates.build_context(slots)
    ctx["outline"] = outline

    if attempt > 0:
        prev_count = slots.get("previous_count", 0)
        prev_dur = slots.get("previous_duration", 0)
        notes: list[str] = []
        if not (ctx["chars_min"] <= prev_count <= ctx["chars_max"]):
            notes.append(
                f"上次生成了 {prev_count} 字，不在要求范围内，"
                f"请严格控制在 {ctx['chars_min']}~{ctx['chars_max']} 字。")
        if prev_dur < 60:
            notes.append(
                f"上次分镜总时长仅 {prev_dur} 秒，不足 60 秒。"
                "请增加分镜数量或加长每镜时长，确保每镜≥5秒、总时长≥60秒。")
        ctx["retry_note"] = "注意：" + "".join(notes) if notes else ""

    system = templates.render("episode_system", ctx, custom_templates)
    user = templates.render("episode_user", ctx, custom_templates)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
