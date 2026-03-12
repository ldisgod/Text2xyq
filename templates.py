"""
提示词模板系统：槽位选项、默认模板、上下文构建与渲染。
"""
from __future__ import annotations

import json
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

VISUAL_STYLES = ["写实", "动漫", "水墨", "赛博朋克", "复古胶片", "梦幻", "极简", "AI仿真"]
ASPECT_RATIOS = ["9:16竖屏", "16:9横屏", "1:1方形"]
MOODS = ["自动", "温馨", "紧张", "搞笑", "悲伤", "热血", "治愈", "悬疑"]
NARRATION_STYLES = ["第三人称旁白", "第一人称独白", "对话为主", "纯画面无旁白"]
PACINGS = ["快节奏", "中等", "慢节奏"]

AVAILABLE_MODELS = [
    # 商业版
    "qwen3-max",
    "qwen-max",
    "qwen3.5-plus",
    "qwen-plus",
    "qwen3.5-flash",
    "qwen-turbo",
    "qwen-long",
    "qwq-plus",
    # 开源版
    "qwen3.5-397b-a17b",
    "qwen3-32b",
    "qwen2.5-72b-instruct",
]

# 换算系数：约 3 个中文字符 ≈ 1 秒视频（旁白语速）
CHARS_PER_SEC = 3

# 分镜时长常量
MIN_SHOT_SECONDS = 5
MAX_SHOT_SECONDS = 8
MIN_EPISODE_SECONDS = 60
MAX_SHOTS = 20

CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# ---------------------------------------------------------------------------
# 默认提示词模板（${变量名} 语法）
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: dict[str, str] = {
    "character_profile_system": (
        "你是专业的角色设定师，为 AI 视频生成工具制作统一的角色档案（视觉+声音）。\n"
        "档案中每项描述必须精确到可直接用于视频生成的关键词（颜色、体型、声线等），\n"
        "避免任何抽象词汇，确保 AI 每次生成时角色外貌与声音高度一致。\n"
        "${protagonist_constraint_section}\n"
        "\n"
        "你必须以纯 JSON 数组格式输出，不要输出 markdown 代码块或任何其他内容。"
    ),

    "character_profile_user": (
        "故事大纲：\n"
        "${outline}\n"
        "\n"
        "主角信息：\n"
        "- 类型：${protagonist_type}\n"
        "- 形象：${character_type}\n"
        "\n"
        "请为故事中的主要角色生成完整档案（视觉+声音），以 JSON 数组返回。\n"
        "每个角色一个对象，字段如下：\n"
        '[\n'
        '  {\n'
        '    "name": "角色名",\n'
        '    "性别": "男/女/未知",\n'
        '    "年龄段": "幼年/少年/青年/中年/老年（影响外貌与声线）",\n'
        '    "种类": "具体品种（如：橘色中华田园猫、柯基犬、金丝仓鼠等；人物则填人类）",\n'
        '    "体型": "身高比例、胖瘦、体格特征",\n'
        '    "外貌": "毛色/肤色/发色（精确到色值）、面部特征、五官细节",\n'
        '    "声音特征": "音色（低沉/清亮/沙哑等）、语速、口头禅、说话风格",\n'
        '    "标志性特征": "每集必须出现的固定视觉元素",\n'
        '    "常见姿势与动作": "该角色标志性的肢体语言",\n'
        '    "情绪表现": "高兴/紧张/愤怒时的具体表情与肢体变化",\n'
        '    "固定道具与配件": "随身携带或经常出现的物品"\n'
        '  }\n'
        ']\n'
        "\n"
        "请用精简的短语描述，便于在每集分镜中直接引用。只输出 JSON 数组。"
    ),

    "outline_system": (
        "你是一位专业的短视频剧本策划师，擅长创作短视频连续剧剧本大纲。\n"
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
        "\n"
        "【要求】\n"
        "1. 输出整体故事大纲：背景设定、主要人物、核心冲突、故事走向、结局方向。\n"
        "2. 大纲需支撑 ${episode_count} 集剧情，节奏紧凑，每集都有看点。\n"
        "3. 每集视频目标时长约 ${episode_duration_seconds} 秒，请据此控制信息密度。\n"
        "\n"
        "请直接输出大纲内容，不需要额外说明。"
    ),

    # ---- 剧情框架（每集叙事骨架，不含分镜细节）----

    "episode_system": (
        "你是专业短视频分镜编剧，为「小云雀」AI视频软件创作分镜脚本。\n"
        "\n"
        "## 风格要求\n"
        "- 画面风格：${visual_style}\n"
        "- 画面比例：${aspect_ratio}\n"
        "- 情绪基调：${mood}\n"
        "- 叙事方式：${narration_style}\n"
        "${protagonist_constraint_section}\n"
        "\n"
        "## 输出格式（严格遵循）\n"
        "第X集：[集名]\n"
        "\n"
        "【场景】[时间·地点·氛围，15字以内]\n"
        "\n"
        "【剧情概要】\n"
        "[用3~5句话概括本集故事走向、关键冲突、角色互动与情绪转折，"
        "后续将据此逐镜展开]\n"
        "\n"
        "【集末悬念】[一句话勾住下集，20字以内]"
    ),

    "episode_user": (
        "故事大纲：\n"
        "${outline}\n"
        "\n"
        "---\n"
        "当前任务：请为第 ${current_episode} 集（共 ${episode_count} 集）"
        "编写剧情框架。\n"
        "\n"
        "请直接输出第 ${current_episode} 集的框架内容，不要任何额外说明。"
    ),

    # ---- 逐镜生成（每次只输出一个分镜）----

    "shot_system": (
        "你是专业短视频分镜编剧，为「小云雀」AI视频软件逐镜创作分镜。\n"
        "\n"
        "## 核心约束\n"
        "- 每个镜头时长严格控制在 5~8 秒\n"
        "- 每个镜头必须包含对白台词或旁白台词，旁白字段不可为「无」或留空\n"
        "\n"
        "## 风格要求\n"
        "- 画面风格：${visual_style}\n"
        "- 画面比例：${aspect_ratio}\n"
        "- 情绪基调：${mood}\n"
        "- 叙事方式：${narration_style}\n"
        "${protagonist_constraint_section}\n"
        "${character_profile_section}\n"
        "\n"
        "## 输出格式\n"
        "只输出一个分镜，严格按以下格式，不要输出任何其他内容：\n"
        "序号（Xs）画面：[动作与构图] | 旁白：[必填，对白或旁白台词] "
        "| 音效：[环境音或「无」] | 光线：[光线描述]"
    ),

    "shot_user": (
        "第 ${current_episode} 集（共 ${episode_count} 集）\n"
        "【场景】${episode_scene}\n"
        "\n"
        "【剧情概要】\n"
        "${episode_narrative}\n"
        "\n"
        "${previous_shots_section}\n"
        "\n"
        "请生成第 ${shot_num} 个分镜（序号 ${shot_label}），时长 5~8 秒。\n"
        "${shot_hint}"
    ),
}

# ---------------------------------------------------------------------------
# 模板编辑器：各模板的可用槽位说明
# ---------------------------------------------------------------------------

SLOT_REFERENCE: dict[str, list[tuple[str, str]]] = {
    "character_profile_system": [
        ("${protagonist_constraint_section}", "宠物约束段落（宠物主角时自动生成）"),
    ],
    "character_profile_user": [
        ("${outline}", "故事大纲（自动填入）"),
        ("${protagonist_type}", "主角类型"),
        ("${character_type}", "主角形象"),
    ],
    "outline_system": [
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
    ],
    "episode_system": [
        ("${visual_style}", "画面风格"),
        ("${aspect_ratio}", "画面比例"),
        ("${mood}", "情绪基调"),
        ("${narration_style}", "旁白风格"),
        ("${protagonist_constraint_section}", "宠物约束段落"),
    ],
    "episode_user": [
        ("${outline}", "故事大纲（自动填入）"),
        ("${current_episode}", "当前集号"),
        ("${episode_count}", "总集数"),
    ],
    "shot_system": [
        ("${visual_style}", "画面风格"),
        ("${aspect_ratio}", "画面比例"),
        ("${mood}", "情绪基调"),
        ("${narration_style}", "旁白风格"),
        ("${protagonist_constraint_section}", "宠物约束段落"),
        ("${character_profile_section}", "角色档案（自动注入）"),
    ],
    "shot_user": [
        ("${current_episode}", "当前集号"),
        ("${episode_count}", "总集数"),
        ("${episode_scene}", "场景（自动提取）"),
        ("${episode_narrative}", "剧情概要（自动提取）"),
        ("${previous_shots_section}", "已生成的分镜（自动填入）"),
        ("${shot_num}", "当前镜头序号"),
        ("${shot_label}", "当前镜头标号（①②…）"),
        ("${shot_hint}", "收尾提示（最后一镜自动填入）"),
    ],
}


# ---------------------------------------------------------------------------
# 上下文构建
# ---------------------------------------------------------------------------

def build_context(raw_slots: dict) -> dict:
    """从原始槽位值构建完整渲染上下文（计算派生值、生成条件段落）。"""
    ctx = dict(raw_slots)

    # 时长计算
    episodes = int(ctx.get("episode_count", 20))
    ctx["episode_duration_seconds"] = MIN_EPISODE_SECONDS

    total_secs = MIN_EPISODE_SECONDS * episodes
    mins, secs = divmod(total_secs, 60)
    ctx["total_duration_display"] = f"{mins}分{secs}秒" if mins else f"{secs}秒"

    # 兼容旧自定义模板中可能残留的变量
    ctx.setdefault("character_description_section", "")
    ctx.setdefault("forbidden_content_section", "")
    ctx.setdefault("target_platform", "")

    # 宠物主角 → 画面只出现动物
    ptype = ctx.get("protagonist_type", "")
    ctx["protagonist_constraint_section"] = (
        "- 【重要】画面中只能出现动物，不得出现人类面孔或人物作为主角"
        if ptype == "宠物" else ""
    )

    # 角色视觉档案（生成后注入，为空则段落为空）
    profile = ctx.get("character_profile", "").strip()
    ctx["character_profile_section"] = (
        f"## 角色视觉档案（每集严格遵守，保持外貌一致）\n{profile}"
        if profile else ""
    )

    # 逐镜生成所需的默认值
    ctx.setdefault("current_episode", 1)
    ctx.setdefault("episode_scene", "")
    ctx.setdefault("episode_narrative", "")
    ctx.setdefault("previous_shots_section", "")
    ctx.setdefault("shot_num", 1)
    ctx.setdefault("shot_label", "①")
    ctx.setdefault("shot_hint", "")

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


# ---------------------------------------------------------------------------
# 角色视觉档案：解析、提取、注入
# ---------------------------------------------------------------------------

def parse_character_profiles(profile_text: str) -> dict[str, str]:
    """将视觉档案解析为 {角色名: 格式化文本块} 字典。

    优先尝试 JSON 解析（LLM 被要求返回 JSON 数组）；
    若 JSON 失败则降级为正则文本解析。
    """
    if not profile_text or not profile_text.strip():
        return {}

    result = _parse_json_profiles(profile_text)
    if result:
        return result
    return _parse_text_profiles(profile_text)


def _parse_json_profiles(raw: str) -> dict[str, str]:
    """从 JSON 数组解析角色档案。"""
    text = raw.strip()
    # 剥离 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # 去掉 ```json
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    # 尝试提取 JSON 数组
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if not m:
            return {}
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return {}

    if not isinstance(data, list):
        return {}

    result: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict) or "name" not in item:
            continue
        name = str(item["name"])
        lines = [f"【{name}】"]
        for key, val in item.items():
            if key == "name" or not val:
                continue
            lines.append(f"- {key}：{val}")
        result[name] = "\n".join(lines)

    return result


def _parse_text_profiles(raw: str) -> dict[str, str]:
    """降级方案：用正则从自由文本中解析角色档案。"""
    pattern = r'(?:^|\n)[^\S\n]*(?:-{3,}[^\S\n]*\n[^\S\n]*)?[#* ]*【([^】]+)】[* ]*'
    matches = list(re.finditer(pattern, raw))
    if not matches:
        return {}

    result: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.start()
        if start < len(raw) and raw[start] == '\n':
            start += 1
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        result[name] = raw[start:end].rstrip()

    return result


def extract_episode_profiles(
    parsed_profiles: dict[str, str],
    episode_text: str,
) -> str:
    """返回所有角色的视觉档案文本，确保每集视觉描述完整一致。"""
    if not parsed_profiles:
        return ""
    return "\n\n".join(parsed_profiles.values())


# ---------------------------------------------------------------------------
# 分镜解析
# ---------------------------------------------------------------------------

def parse_shot_durations(text: str) -> list[int]:
    """从分镜文本中提取每个镜头的秒数，如 ①（6s） → [6]。"""
    return [int(m) for m in re.findall(r'（(\d+)[sS秒]）', text)]


def get_shot_label(shot_num: int) -> str:
    """返回分镜序号标签：①②…⑳，超出则用 (21) 形式。"""
    idx = shot_num - 1
    if 0 <= idx < len(CIRCLED_NUMBERS):
        return CIRCLED_NUMBERS[idx]
    return f"({shot_num})"


# ---------------------------------------------------------------------------
# 剧情框架解析与组装
# ---------------------------------------------------------------------------

def parse_episode_narrative(text: str) -> dict[str, str]:
    """解析集剧情框架，提取标题行、场景、剧情概要、集末悬念。"""
    result: dict[str, str] = {}

    m = re.search(r'(第\s*\d+\s*集[：:]\s*.+)', text)
    if m:
        result['header'] = m.group(1).strip()

    m = re.search(r'【场景】\s*(.+)', text)
    if m:
        result['scene'] = m.group(1).strip()

    m = re.search(r'【剧情概要】\s*(.*?)(?=\s*【集末悬念】|\Z)', text, re.DOTALL)
    if m:
        result['narrative'] = m.group(1).strip()

    m = re.search(r'【集末悬念】\s*(.+)', text)
    if m:
        result['cliffhanger'] = m.group(1).strip()

    return result


def assemble_episode(narrative: dict[str, str], shots: list[str]) -> str:
    """将剧情框架和分镜列表组装为完整集脚本（不含视觉档案，由调用方注入）。"""
    parts: list[str] = []

    if 'header' in narrative:
        parts.append(narrative['header'])

    if 'scene' in narrative:
        parts.append(f"\n\n【场景】{narrative['scene']}")

    if shots:
        parts.append("\n\n【分镜】")
        for shot in shots:
            parts.append(f"\n{shot.strip()}")

    if 'cliffhanger' in narrative:
        parts.append(f"\n\n【集末悬念】{narrative['cliffhanger']}")

    return "".join(parts)


def strip_visual_profiles(text: str) -> str:
    """移除文本中的【视觉档案】段落（如果 LLM 自行生成了该段落）。"""
    return re.sub(
        r'\s*【视觉档案】.*?(?=【分镜】|【集末悬念】|\Z)', '',
        text, flags=re.DOTALL)


def inject_visual_profiles(episode_text: str, profiles_text: str) -> str:
    """将视觉档案文本插入到【场景】与【分镜】之间。"""
    if not profiles_text:
        return episode_text

    visual_section = f"【视觉档案】\n{profiles_text}"

    idx = episode_text.find("【分镜】")
    if idx != -1:
        return episode_text[:idx] + visual_section + "\n\n" + episode_text[idx:]

    return episode_text + "\n\n" + visual_section
