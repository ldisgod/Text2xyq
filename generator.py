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


def build_episode_narrative_messages(
    slots: dict,
    outline: str,
    custom_templates: dict | None = None,
) -> list[dict]:
    """构建单集剧情框架生成所需的 messages 列表。"""
    ctx = templates.build_context(slots)
    ctx["outline"] = outline
    system = templates.render("episode_system", ctx, custom_templates)
    user = templates.render("episode_user", ctx, custom_templates)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_shot_messages(
    slots: dict,
    narrative: dict[str, str],
    previous_shots: list[str],
    shot_num: int,
    is_last: bool,
    custom_templates: dict | None = None,
) -> list[dict]:
    """构建单个分镜生成所需的 messages 列表。

    narrative: parse_episode_narrative() 的返回值
    previous_shots: 已生成的分镜文本列表
    shot_num: 当前镜头序号（从 1 开始）
    is_last: 是否为本集最后一个镜头
    """
    ctx = templates.build_context(slots)
    ctx["episode_scene"] = narrative.get("scene", "")
    ctx["episode_narrative"] = narrative.get("narrative", "")
    ctx["shot_num"] = shot_num
    ctx["shot_label"] = templates.get_shot_label(shot_num)

    if previous_shots:
        ctx["previous_shots_section"] = (
            "已完成的分镜：\n" + "\n".join(previous_shots))
    else:
        ctx["previous_shots_section"] = ""

    ctx["shot_hint"] = (
        "这是本集最后一个镜头，请自然收束画面，为集末悬念做铺垫。"
        if is_last else ""
    )

    system = templates.render("shot_system", ctx, custom_templates)
    user = templates.render("shot_user", ctx, custom_templates)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
