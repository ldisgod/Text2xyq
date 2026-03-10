# Text2xyq · 小云雀剧本生成器

根据用户自定义选材，自动生成多集短视频连续剧剧本大纲及各集提示词，供「小云雀」AI 视频生成软件直接使用。

## 功能概述

### Part 1 · 选材与大纲生成
通过图形界面选择以下选材，由 LLM 生成完整故事大纲：

| 选项 | 可选内容（举例） |
|------|-----------------|
| 主角类型 | 宠物 / 人物 |
| 故事风格 | 逆袭、爽剧、重生、穿越、甜宠… |
| 主角形象 | 猫、狗、乌龟、鹦鹉（宠物）/ 白领、书生… |
| 核心剧情 | 重生复仇、争夺地位、扮猪吃虎… |

### Part 2 · 剧本提示词生成
基于 Part 1 生成的大纲，自动拆解为 N 集（默认 20 集）的视频提示词，可直接粘贴到小云雀软件中生成视频。

## 运行环境

- **操作系统**：Windows 10 / 11
- **Python**：3.9+

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动应用
python main.py
```

首次运行时，程序会弹出「LLM 配置」对话框，填写：
- **Base URL**：你的 LLM API 地址（OpenAI 兼容接口，如 `https://api.openai.com/v1`）
- **API Key**：你的 API 密钥
- **模型名称**：如 `gpt-4o`、`deepseek-chat` 等

配置信息保存在 `%USERPROFILE%\.text2xyq\config.json`，下次启动无需重新填写。

## 文件结构

```
Text2xyq/
├── main.py          # 入口脚本
├── app.py           # Tkinter GUI 主窗口
├── generator.py     # 大纲与剧本提示词生成逻辑
├── llm_client.py    # OpenAI 兼容 LLM 客户端
├── config.py        # 配置读写
└── requirements.txt # 依赖列表
```
