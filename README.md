# Text2xyq · 小云雀剧本生成器

为「小云雀」AI 视频工具生成多集短视频分镜剧本。通过 LLM 自动生成故事大纲、角色视觉档案和逐集分镜脚本。

## Windows 用户

从 [Releases](../../releases) 页面下载最新的 `Text2xyq.exe`，双击运行即可。

## 从源码运行

需要 Python 3.10+，使用 [uv](https://docs.astral.sh/uv/) 管理依赖：

```bash
uv sync
uv run main.py
```

也可以用 pip：

```bash
pip install -r requirements.txt
python main.py
```

## 打包 Windows EXE

**方式一：GitHub Actions 自动构建**

打 tag 后自动构建并发布到 Releases：

```bash
git tag v1.0.0
git push --tags
```

**方式二：本地打包（需在 Windows 上）**

双击运行 `build_win.bat`，生成的 exe 在 `dist/Text2xyq.exe`。
