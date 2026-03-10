"""
Text2xyq · 小云雀剧本生成器
入口脚本
"""
def main():
    # 在 Windows 上隐藏命令行窗口（通过 pythonw.exe 运行时已自动隐藏）
    from app import App
    application = App()
    application.mainloop()


if __name__ == "__main__":
    main()
