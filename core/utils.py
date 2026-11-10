# -*- coding: utf-8 -*-
"""通用工具：定位 ffmpeg/ffprobe、探测媒体时长、运行命令。"""
import os
import sys
import json
import shutil
import subprocess
import time


class Cancelled(Exception):
    """用户中途取消。"""


_cancel_checker = None


def set_cancel_checker(fn) -> None:
    """注册一个返回 True 表示"应取消"的回调；ffmpeg 运行中会被立即终止。"""
    global _cancel_checker
    _cancel_checker = fn


def app_base_dir() -> str:
    """PyInstaller 打包后返回 exe 所在目录，开发时返回项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidates(name: str):
    names = [name, name + ".exe"]
    # 1) 项目 bin/ 目录（随软件分发）
    for n in names:
        p = os.path.join(app_base_dir(), "bin", n)
        if os.path.isfile(p):
            return p
    # 2) PyInstaller 打包时解压目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for n in names:
            p = os.path.join(meipass, "bin", n)
            if os.path.isfile(p):
                return p
    # 3) 系统 PATH
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def ffmpeg_path() -> str:
    p = _candidates("ffmpeg")
    if not p:
        raise FileNotFoundError(
            "未找到 ffmpeg。请将 ffmpeg.exe 放到软件目录下的 bin 文件夹中。"
        )
    return p


def ffprobe_path() -> str:
    p = _candidates("ffprobe")
    if not p:
        raise FileNotFoundError(
            "未找到 ffprobe。请将 ffprobe.exe 放到软件目录下的 bin 文件夹中。"
        )
    return p


def probe_duration(path: str) -> float:
    """用 ffprobe 获取媒体文件时长（秒）。"""
    cmd = [
        ffprobe_path(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ]
    out = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {out.stderr[:300]}")
    data = json.loads(out.stdout)
    return float(data["format"]["duration"])


def run_ffmpeg(args, on_fail_hint: str = "") -> None:
    """运行 ffmpeg；期间如果用户点了取消，会立刻终止当前进程。"""
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y"] + args
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    while proc.poll() is None:
        if _cancel_checker is not None and _cancel_checker():
            proc.kill()
            proc.communicate()
            raise Cancelled("已取消生成")
        time.sleep(0.15)
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        msg = (stderr or "")[-800:]
        raise RuntimeError(f"ffmpeg 执行失败: {msg}\n{on_fail_hint}")
