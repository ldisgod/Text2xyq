"""
配置管理模块：保存和加载 LLM 连接参数（base_url、api_key）。
配置文件存储在用户主目录下的 .text2xyq/config.json。
"""
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".text2xyq"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DEFAULTS = {
    "base_url": "",
    "api_key": "",
    "model": "gpt-4o",
}


def load() -> dict:
    """从磁盘加载配置，若不存在则返回默认值。"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 补全缺失字段
            merged = dict(_DEFAULTS)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save(cfg: dict) -> None:
    """将配置持久化到磁盘。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
