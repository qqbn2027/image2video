# -*- coding: utf-8 -*-
"""把 PyInstaller 生成的 dist/TextToVideo 发布到 release/文字图片转视频工具。"""
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE, "dist", "TextToVideo")
DST_NAME = "文字图片转视频工具"
DST_DIR = os.path.join(BASE, "release", DST_NAME)
OLD_EXE = "TextToVideo.exe"
NEW_EXE = DST_NAME + ".exe"
README = os.path.join(BASE, "使用说明.txt")


def main() -> int:
    src_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else SRC_DIR
    dst_dir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else DST_DIR
    if not os.path.isdir(src_dir):
        print(f"未找到构建目录: {src_dir}")
        return 1

    if os.path.isdir(dst_dir):
        shutil.rmtree(dst_dir)
    os.makedirs(dst_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dst_dir, NEW_EXE if item == OLD_EXE else item)
        shutil.move(s, d)
    if os.path.isfile(README):
        shutil.copy2(README, os.path.join(dst_dir, "使用说明.txt"))
    print(f"完成: {os.path.join(dst_dir, NEW_EXE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
