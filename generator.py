"""
剧本生成编排模块：协调模板渲染与 LLM 调用。
模板内容全部由 templates 模块管理，此处只负责组装消息列表。
"""
from __future__ import annotations

import templates
from llm_client import LLMClient, LLMError  # noqa: F401 (re-export LLMError)


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


def build_episode_messages(
    slots: dict,
    outline: str,
    custom_templates: dict | None = None,
) -> list[dict]:
    """构建各集提示词生成所需的 messages 列表。"""
    ctx = templates.build_context(slots)
    ctx["outline"] = outline
    system = templates.render("episode_system", ctx, custom_templates)
    user = templates.render("episode_user", ctx, custom_templates)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
