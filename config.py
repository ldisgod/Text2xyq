"""
配置管理模块：LLM 连接参数 + 生成偏好 + 自定义模板。
统一存储在 ~/.text2xyq/config.json。
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".text2xyq"
CONFIG_FILE = CONFIG_DIR / "config.json"

_LLM_DEFAULTS: dict = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "",
    "model": "qwen-plus",
}

_GENERATION_DEFAULTS: dict = {
    "episode_count": 20,
    "chars_min": 270,
    "chars_max": 330,
    "visual_style": "写实",
    "aspect_ratio": "9:16竖屏",
    "mood": "自动",
    "narration_style": "第三人称旁白",
    "pacing": "中等",
}


# ---------------------------------------------------------------------------
# 内部 IO
# ---------------------------------------------------------------------------

def _read() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# LLM 配置
# ---------------------------------------------------------------------------

def load_llm() -> dict:
    merged = dict(_LLM_DEFAULTS)
    merged.update(_read().get("llm_config", {}))
    return merged


def save_llm(cfg: dict) -> None:
    data = _read()
    data["llm_config"] = cfg
    _write(data)


# ---------------------------------------------------------------------------
# 生成参数偏好
# ---------------------------------------------------------------------------

def load_generation_params() -> dict:
    merged = dict(_GENERATION_DEFAULTS)
    merged.update(_read().get("generation_params", {}))
    return merged


def save_generation_params(params: dict) -> None:
    data = _read()
    data["generation_params"] = params
    _write(data)


# ---------------------------------------------------------------------------
# 自定义模板覆盖
# ---------------------------------------------------------------------------

def load_custom_templates() -> dict:
    return _read().get("custom_templates", {})


def save_custom_templates(templates: dict) -> None:
    data = _read()
    data["custom_templates"] = templates
    _write(data)
