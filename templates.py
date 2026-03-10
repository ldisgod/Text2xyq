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

STYLES = [
    "逆袭", "爽剧", "重生", "穿越", "系统",
    "打脸", "复仇", "治愈", "搞笑", "反转",
    "萌宠", "励志", "权谋", "团宠", "冒险",
    "霸总", "古风", "都市", "甜宠",
]

PLOTS = [
    "重生复仇", "争夺地位", "扮猪吃虎", "逆天改命",
    "赘婿逆袭", "豪门秘辛", "异世冒险", "校园成长",
    "职场风云", "神兽觉醒", "打脸全场", "团宠逆袭",
    "系统加持", "权谋争霸",
]

# 故事风格 → 推荐核心剧情（联动）
STYLE_PLOTS: dict[str, list[str]] = {
    "逆袭": ["扮猪吃虎", "逆天改命", "赘婿逆袭", "职场风云", "校园成长"],
    "爽剧": ["重生复仇", "争夺地位", "扮猪吃虎", "打脸全场", "团宠逆袭"],
    "重生": ["重生复仇", "逆天改命", "豪门秘辛", "争夺地位"],
    "穿越": ["异世冒险", "豪门秘辛", "逆天改命", "校园成长"],
    "系统": ["系统加持", "逆天改命", "异世冒险", "神兽觉醒", "扮猪吃虎"],
    "打脸": ["重生复仇", "争夺地位", "打脸全场", "扮猪吃虎"],
    "复仇": ["重生复仇", "争夺地位", "豪门秘辛", "逆天改命"],
    "治愈": ["校园成长", "神兽觉醒", "异世冒险"],
    "搞笑": ["扮猪吃虎", "校园成长", "职场风云", "团宠逆袭"],
    "反转": ["重生复仇", "扮猪吃虎", "豪门秘辛", "系统加持"],
    "萌宠": ["神兽觉醒", "逆天改命", "异世冒险", "校园成长"],
    "励志": ["逆天改命", "职场风云", "校园成长", "赘婿逆袭"],
    "权谋": ["权谋争霸", "争夺地位", "豪门秘辛", "重生复仇"],
    "团宠": ["团宠逆袭", "争夺地位", "校园成长", "豪门秘辛"],
    "冒险": ["异世冒险", "神兽觉醒", "逆天改命"],
    "霸总": ["豪门秘辛", "赘婿逆袭", "争夺地位"],
    "古风": ["重生复仇", "争夺地位", "异世冒险", "权谋争霸"],
    "都市": ["职场风云", "豪门秘辛", "赘婿逆袭", "逆天改命"],
    "甜宠": ["校园成长", "豪门秘辛", "职场风云"],
}

CHARACTER_TYPES_MAP: dict[str, list[str]] = {
    "宠物": ["猫", "狗", "仓鼠", "兔子", "鹦鹉", "乌龟", "狐狸", "松鼠", "金鱼", "蜥蜴"],
    "人物": [
        "普通少女", "落魄少爷", "现代白领", "古代书生",
        "修仙弟子", "侦探", "厨师", "医生", "程序员", "律师",
    ],
}

VISUAL_STYLES = ["写实", "动漫", "水墨", "赛博朋克", "复古胶片", "梦幻", "极简"]
ASPECT_RATIOS = ["9:16竖屏", "16:9横屏", "1:1方形"]
MOODS = ["自动", "温馨", "紧张", "搞笑", "悲伤", "热血", "治愈", "悬疑"]
NARRATION_STYLES = ["第三人称旁白", "第一人称独白", "对话为主", "纯画面无旁白"]
PACINGS = ["快节奏", "中等", "慢节奏"]
PLATFORMS = ["抖音", "快手", "小红书", "B站", "视频号"]

AVAILABLE_MODELS = [
    "qwen3-max",
    "qwen-max",
    "qwen-plus",
    "qwen-turbo",
    "qwen-long",
]

# 换算系数：约 3 个中文字符 ≈ 1 秒视频（旁白语速）
CHARS_PER_SEC = 3

# ---------------------------------------------------------------------------
# 默认提示词模板（${变量名} 语法）
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
        "${protagonist_constraint_section}\n"
        "\n"
        "请用中文回答，格式清晰，内容精炼。"
    ),

    "outline_user": (
        "请根据以下选材，为一部共 ${episode_count} 集的短视频连续剧创作完整的故事大纲。\n"
        "\n"
        "【选材信息】\n"
        "- 主角类型：${protagonist_type}\n"
        "- 故事风格：${style}\n"
        "- 主角形象：${character_type}\n"
        "- 核心剧情：${plot}\n"
        "${character_description_section}\n"
        "${forbidden_content_section}\n"
        "\n"
        "【要求】\n"
        "1. 输出整体故事大纲：背景设定、主要人物、核心冲突、故事走向、结局方向。\n"
        "2. 大纲需支撑 ${episode_count} 集剧情，节奏紧凑，每集都有看点。\n"
        "3. 每集视频目标时长约 ${episode_duration_seconds} 秒，请据此控制信息密度。\n"
        "\n"
        "请直接输出大纲内容，不需要额外说明。"
    ),

    "episode_system": (
        "你是专业短视频分镜编剧，为「小云雀」AI视频软件创作分镜脚本。\n"
        "\n"
        "## 字数约束（最重要）\n"
        "每集脚本总字数严格控制在 ${chars_min}~${chars_max} 字（目标 ${chars_per_episode} 字）。\n"
        "字数直接决定视频时长（约 3 字/秒），超出或低于范围均会影响成片效果。\n"
        "\n"
        "## 风格要求\n"
        "- 画面风格：${visual_style}\n"
        "- 画面比例：${aspect_ratio}\n"
        "- 情绪基调：${mood}\n"
        "- 叙事方式：${narration_style}\n"
        "- 目标平台：${target_platform}\n"
        "${protagonist_constraint_section}\n"
        "${forbidden_content_section}\n"
        "\n"
        "## 输出格式（每集严格遵循）\n"
        "第X集：[集名]\n"
        "\n"
        "【场景】[时间·地点·氛围，15字以内]\n"
        "\n"
        "【分镜】\n"
        "①（Xs）画面：[动作/构图] | 旁白：[旁白文字或「无」] | 音效：[音效或「无」]\n"
        "②（Xs）画面：... | 旁白：... | 音效：...\n"
        "（根据总时长安排合理分镜数，每镜 3~6 秒）\n"
        "\n"
        "【集末悬念】[一句话勾住下集，20字以内]"
    ),

    "episode_user": (
        "故事大纲：\n"
        "${outline}\n"
        "\n"
        "${character_description_section}\n"
        "\n"
        "---\n"
        "当前任务：请为第 ${current_episode} 集（共 ${episode_count} 集）编写完整分镜脚本。\n"
        "\n"
        "字数要求：${chars_min}~${chars_max} 字（目标 ${chars_per_episode} 字 ≈ ${episode_duration_seconds} 秒）\n"
        "${retry_note}\n"
        "\n"
        "请直接输出第 ${current_episode} 集的分镜脚本，不要任何额外说明。"
    ),
}

# ---------------------------------------------------------------------------
# 模板编辑器：各模板的可用槽位说明
# ---------------------------------------------------------------------------

SLOT_REFERENCE: dict[str, list[tuple[str, str]]] = {
    "outline_system": [
        ("${target_platform}", "目标平台"),
        ("${visual_style}", "画面风格"),
        ("${aspect_ratio}", "画面比例"),
        ("${mood}", "情绪基调"),
        ("${narration_style}", "旁白风格"),
        ("${pacing}", "节奏"),
        ("${protagonist_constraint_section}", "宠物约束段落（宠物主角时自动生成）"),
    ],
    "outline_user": [
        ("${episode_count}", "生成集数"),
        ("${protagonist_type}", "主角类型"),
        ("${style}", "故事风格"),
        ("${character_type}", "主角形象"),
        ("${plot}", "核心剧情"),
        ("${episode_duration_seconds}", "每集预计时长(秒)"),
        ("${character_description_section}", "角色设定段落（非空时生成）"),
        ("${forbidden_content_section}", "禁止内容段落（非空时生成）"),
    ],
    "episode_system": [
        ("${chars_per_episode}", "每集目标字数"),
        ("${chars_min}", "最小字数（目标×0.9）"),
        ("${chars_max}", "最大字数（目标×1.1）"),
        ("${visual_style}", "画面风格"),
        ("${aspect_ratio}", "画面比例"),
        ("${mood}", "情绪基调"),
        ("${narration_style}", "旁白风格"),
        ("${target_platform}", "目标平台"),
        ("${protagonist_constraint_section}", "宠物约束段落"),
        ("${forbidden_content_section}", "禁止内容段落"),
    ],
    "episode_user": [
        ("${outline}", "故事大纲（自动填入）"),
        ("${current_episode}", "当前集号"),
        ("${episode_count}", "总集数"),
        ("${chars_per_episode}", "每集目标字数"),
        ("${chars_min}", "最小字数"),
        ("${chars_max}", "最大字数"),
        ("${episode_duration_seconds}", "每集预计时长(秒)"),
        ("${character_description_section}", "角色设定段落"),
        ("${retry_note}", "重试提示（字数超标时自动填入）"),
    ],
}


# ---------------------------------------------------------------------------
# 上下文构建
# ---------------------------------------------------------------------------

def build_context(raw_slots: dict) -> dict:
    """从原始槽位值构建完整渲染上下文（计算派生值、生成条件段落）。"""
    ctx = dict(raw_slots)

    # 数值计算
    chars = int(ctx.get("chars_per_episode", 300))
    episodes = int(ctx.get("episode_count", 20))

    ctx["chars_min"] = int(chars * 0.9)
    ctx["chars_max"] = int(chars * 1.1)
    ctx["episode_duration_seconds"] = round(chars / CHARS_PER_SEC)

    total_secs = round(chars * episodes / CHARS_PER_SEC)
    mins, secs = divmod(total_secs, 60)
    ctx["total_duration_display"] = f"{mins}分{secs}秒" if mins else f"{secs}秒"

    # 条件段落
    for key, label in (
        ("character_description", "角色设定"),
        ("forbidden_content", "禁止内容"),
    ):
        val = ctx.get(key, "").strip()
        ctx[f"{key}_section"] = f"- {label}：{val}" if val else ""

    # 宠物主角 → 画面只出现动物
    ptype = ctx.get("protagonist_type", "")
    ctx["protagonist_constraint_section"] = (
        "- 【重要】画面中只能出现动物，不得出现人类面孔或人物作为主角"
        if ptype == "宠物" else ""
    )

    # 单集生成所需的默认值
    ctx.setdefault("retry_note", "")
    ctx.setdefault("current_episode", 1)

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
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def get_default_template(name: str) -> str:
    return DEFAULT_TEMPLATES.get(name, "")


def get_template_names() -> list[str]:
    return list(DEFAULT_TEMPLATES.keys())
