"""
剧本生成逻辑模块：
  - generate_outline()   根据用户选材生成整体大纲（Part 1）
  - generate_episodes()  根据大纲生成各集提示词（Part 2）
"""
from __future__ import annotations

from llm_client import LLMClient, LLMError  # noqa: F401 (re-export LLMError)

# ------------------------------------------------------------------
# Prompt 模板
# ------------------------------------------------------------------

_OUTLINE_SYSTEM = (
    "你是一位专业的短视频剧本策划师，擅长创作适合短视频平台的连续剧剧本大纲。"
    "请用中文回答，格式清晰，内容精炼。"
)

_OUTLINE_USER_TMPL = """\
请根据以下选材，为一部共 {episode_count} 集的短视频连续剧创作完整的故事大纲。

【选材信息】
- 主角类型：{protagonist_type}
- 故事风格：{style}
- 主角具体形象：{character_type}
- 核心剧情：{plot}

【要求】
1. 输出整体故事大纲，包含：背景设定、主要人物介绍、核心冲突、故事走向、结局方向。
2. 大纲需支撑 {episode_count} 集的剧情展开，节奏紧凑，每集都有看点。
3. 语言生动，适合短视频受众。

请直接输出大纲内容，不需要额外说明。"""

_EPISODE_SYSTEM = (
    "你是一位专业的短视频剧本提示词工程师，擅长将故事大纲拆解为适合 AI 视频生成软件（小云雀）的提示词。"
    "每集提示词应简洁、画面感强、包含场景、角色动作和情绪，适合直接输入视频生成工具。"
    "请用中文回答。"
)

_EPISODE_USER_TMPL = """\
以下是一部共 {episode_count} 集短视频连续剧的故事大纲：

{outline}

请根据上述大纲，为每一集生成适合「小云雀」AI 视频生成软件使用的提示词。

【格式要求】
- 每集单独列出，格式为：
  第X集：[提示词内容]
- 提示词包含：场景描述、主角动作、情绪氛围、关键道具或视觉元素。
- 每集提示词长度：100～200 字。
- 共输出 {episode_count} 集，从第 1 集到第 {episode_count} 集。

请直接输出所有集的提示词，不需要额外说明。"""


# ------------------------------------------------------------------
# 公共函数
# ------------------------------------------------------------------

def build_outline_messages(
    protagonist_type: str,
    style: str,
    character_type: str,
    plot: str,
    episode_count: int,
) -> list[dict]:
    """构建生成大纲所需的消息列表（可用于流式或非流式调用）。"""
    user_content = _OUTLINE_USER_TMPL.format(
        protagonist_type=protagonist_type,
        style=style,
        character_type=character_type,
        plot=plot,
        episode_count=episode_count,
    )
    return [
        {"role": "system", "content": _OUTLINE_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def build_episode_messages(outline: str, episode_count: int) -> list[dict]:
    """构建生成各集提示词所需的消息列表。"""
    user_content = _EPISODE_USER_TMPL.format(
        outline=outline,
        episode_count=episode_count,
    )
    return [
        {"role": "system", "content": _EPISODE_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def generate_outline(client: LLMClient, protagonist_type: str, style: str,
                     character_type: str, plot: str, episode_count: int) -> str:
    """调用 LLM 生成故事大纲（非流式）。"""
    messages = build_outline_messages(
        protagonist_type, style, character_type, plot, episode_count
    )
    return client.chat(messages)


def generate_episodes(client: LLMClient, outline: str, episode_count: int) -> str:
    """调用 LLM 根据大纲生成各集提示词（非流式）。"""
    messages = build_episode_messages(outline, episode_count)
    return client.chat(messages)
