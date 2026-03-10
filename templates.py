"""
提示词模板系统：槽位选项、默认模板、上下文构建与渲染。
"""
from __future__ import annotations

import re
import string

# ---------------------------------------------------------------------------
# 选项常量
# ---------------------------------------------------------------------------

PROTAGONIST_TYPES = ["宠物", "人物"]

STYLES = ["逆袭", "爽剧", "重生", "穿越", "甜宠", "复仇", "霸总", "古风", "都市"]

CHARACTER_TYPES_MAP = {
    "宠物": ["猫", "狗", "乌龟", "鹦鹉", "兔子", "仓鼠", "金鱼", "蜥蜴"],
    "人物": [
        "普通少女", "落魄少爷", "现代白领", "古代书生",
        "修仙弟子", "侦探", "厨师", "医生",
    ],
}

PLOTS = [
    "重生复仇", "争夺地位", "扮猪吃虎", "逆天改命",
    "赘婿逆袭", "豪门秘辛", "异世冒险", "校园成长",
    "职场风云", "神兽觉醒",
]

VISUAL_STYLES = ["写实", "动漫", "水墨", "赛博朋克", "复古胶片", "梦幻", "极简"]
ASPECT_RATIOS = ["9:16竖屏", "16:9横屏", "1:1方形"]
MOODS = ["自动", "温馨", "紧张", "搞笑", "悲伤", "热血", "治愈", "悬疑"]
NARRATION_STYLES = ["第三人称旁白", "第一人称独白", "对话为主", "纯画面无旁白"]
PACINGS = ["快节奏", "中等", "慢节奏"]
PLATFORMS = ["抖音", "快手", "小红书", "B站", "视频号"]
HOOK_STYLES = ["自动", "悬念提问", "震撼数据", "反转预告", "情感共鸣", "冲突开场"]
CLIFFHANGER_STYLES = ["自动", "悬念留白", "反转揭示", "情感高潮", "新危机出现"]
SHOT_DENSITIES = ["自动", "密集切换(2-3秒/镜)", "中等(4-5秒/镜)", "长镜头(6-8秒/镜)"]
DIALOGUE_RATIOS = ["旁白为主", "旁白+少量对话", "对话为主", "纯对话", "纯旁白"]

# 百炼可用模型
AVAILABLE_MODELS = [
    "qwen3-max",
    "qwen-max",
    "qwen-plus",
    "qwen-turbo",
    "qwen-long",
]

# 时长预设：标签 → 每集字数
DURATION_PRESETS = {
    "15秒": 45,
    "30秒": 90,
    "60秒": 180,
    "3分钟": 540,
}

# 换算系数：约 3 个中文字符 ≈ 1 秒视频（旁白语速）
CHARS_PER_SEC = 3

# ---------------------------------------------------------------------------
# 默认提示词模板（使用 ${ } 占位符，string.Template 语法）
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: dict[str, str] = {
    "outline_system": (
        "你是一位专业的短视频剧本策划师，擅长创作适合${target_platform}平台的短视频连续剧剧本大纲。\n"
        "\n"
        "## 创作风格要求\n"
        "- 画面风格：${visual_style}\n"
        "- 画面比例：${aspect_ratio}\n"
        "- 情绪基调：${mood}\n"
        "- 叙事方式：${narration_style}\n"
        "- 整体节奏：${pacing}\n"
        "\n"
        "请用中文回答，格式清晰，内容精炼。"
    ),

    "outline_user": (
        "请根据以下选材，为一部共 ${episode_count} 集的短视频连续剧创作完整的故事大纲。\n"
        "\n"
        "【选材信息】\n"
        "- 主角类型：${protagonist_type}\n"
        "- 故事风格：${style}\n"
        "- 主角具体形象：${character_type}\n"
        "- 核心剧情：${plot}\n"
        "${character_description_section}\n"
        "${custom_requirements_section}\n"
        "${forbidden_content_section}\n"
        "\n"
        "【要求】\n"
        "1. 输出整体故事大纲，包含：背景设定、主要人物介绍、核心冲突、故事走向、结局方向。\n"
        "2. 大纲需支撑 ${episode_count} 集的剧情展开，节奏紧凑，每集都有看点。\n"
        "3. 每集视频目标时长约 ${episode_duration_seconds} 秒，请据此控制每集信息密度。\n"
        "4. 语言生动，适合短视频受众。\n"
        "\n"
        "请直接输出大纲内容，不需要额外说明。"
    ),

    "episode_system": (
        "你是一位专业的短视频剧本提示词工程师，擅长将故事大纲拆解为适合 AI 视频生成软件（小云雀）的提示词。\n"
        "\n"
        "## 核心约束\n"
        "- 【字数控制·最重要】严格控制每集提示词正文在 ${chars_min} 到 ${chars_max} 字之间。"
        "这非常重要，因为字数直接决定生成视频的时长（约每 3 个中文字符对应 1 秒视频）。"
        "目标：${chars_per_episode} 字/集 ≈ ${episode_duration_seconds} 秒视频。\n"
        "- 画面风格：${visual_style}\n"
        "- 画面比例：${aspect_ratio}\n"
        "- 叙事方式：${narration_style}\n"
        "- 对话比例：${dialogue_ratio}\n"
        "${shot_density_section}\n"
        "${hook_style_section}\n"
        "${cliffhanger_style_section}\n"
        "\n"
        "每集提示词应简洁、画面感强，包含场景描写、角色动作和情绪，适合直接输入小云雀视频生成工具。\n"
        "请用中文回答。"
    ),

    "episode_user": (
        "以下是一部共 ${episode_count} 集短视频连续剧的故事大纲：\n"
        "\n"
        "${outline}\n"
        "\n"
        "请根据上述大纲，为每一集生成适合「小云雀」AI 视频生成软件使用的提示词。\n"
        "\n"
        "【格式要求】\n"
        "- 每集单独列出，格式为：\n"
        "  第X集：[提示词内容]\n"
        "- 提示词包含：场景描述、主角动作、情绪氛围、关键道具或视觉元素。\n"
        "- 【重要】每集提示词字数严格控制在 ${chars_min}～${chars_max} 字，目标 ${chars_per_episode} 字。\n"
        "- 共输出 ${episode_count} 集，从第 1 集到第 ${episode_count} 集。\n"
        "\n"
        "请直接输出所有集的提示词，不需要额外说明。"
    ),
}


# ---------------------------------------------------------------------------
# 上下文构建
# ---------------------------------------------------------------------------

def build_context(raw_slots: dict) -> dict:
    """从原始槽位值构建完整渲染上下文（计算派生值、生成条件段落）。"""
    ctx = dict(raw_slots)

    # ── 数值计算 ─────────────────────────────────────────────────
    chars = int(ctx.get("chars_per_episode", 300))
    episodes = int(ctx.get("episode_count", 20))

    ctx["chars_min"] = int(chars * 0.9)
    ctx["chars_max"] = int(chars * 1.1)
    ctx["episode_duration_seconds"] = round(chars / CHARS_PER_SEC)

    total_secs = round(chars * episodes / CHARS_PER_SEC)
    mins, secs = divmod(total_secs, 60)
    ctx["total_duration_display"] = f"{mins}分{secs}秒" if mins else f"{secs}秒"

    # ── 条件段落：内容非空才生成，否则为空字符串 ─────────────────
    for key, label in (
        ("character_description", "角色设定"),
        ("custom_requirements", "特殊要求"),
        ("forbidden_content", "禁止内容"),
    ):
        val = ctx.get(key, "").strip()
        ctx[f"{key}_section"] = f"- {label}：{val}" if val else ""

    # 「自动」的选项不强调，留空
    hook = ctx.get("hook_style", "自动")
    ctx["hook_style_section"] = f"- 开场钩子风格：{hook}" if hook != "自动" else ""

    cliff = ctx.get("cliffhanger_style", "自动")
    ctx["cliffhanger_style_section"] = f"- 集尾悬念风格：{cliff}" if cliff != "自动" else ""

    sd = ctx.get("shot_density", "自动")
    ctx["shot_density_section"] = f"- 分镜密度：{sd}" if sd != "自动" else ""

    return ctx


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render(template_name: str, context: dict,
           custom_templates: dict | None = None) -> str:
    """用上下文渲染指定模板，返回替换后的文本。"""
    pool = dict(DEFAULT_TEMPLATES)
    if custom_templates:
        pool.update(custom_templates)

    tmpl_str = pool.get(template_name, "")
    result = string.Template(tmpl_str).safe_substitute(context)
    # 清理多余空行（连续 3+ 个换行 → 2 个）
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def get_default_template(name: str) -> str:
    """获取指定名称的默认模板文本。"""
    return DEFAULT_TEMPLATES.get(name, "")


def get_template_names() -> list[str]:
    """返回所有模板名称列表。"""
    return list(DEFAULT_TEMPLATES.keys())
