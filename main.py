# -*- coding: utf-8 -*-
import ctypes
import os
import sys
import tempfile
import traceback


def _enable_dpi_awareness():
    """让界面在高 DPI 屏幕上保持清晰（Windows）。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _selftest() -> int:
    """打包自检：验证 ffmpeg 定位、离线语音、完整视频生成。日志写入临时文件。"""
    from core.utils import ffmpeg_path, ffprobe_path, run_ffmpeg, probe_duration
    from core.video import build_video

    log_path = os.path.join(tempfile.gettempdir(), "t2v_selftest.log")
    lines = []

    def log(msg):
        lines.append(str(msg))

    try:
        log("frozen: " + str(getattr(sys, "frozen", False)))
        log("ffmpeg: " + ffmpeg_path())
        log("ffprobe: " + ffprobe_path())
        tmpdir = tempfile.mkdtemp(prefix="t2v_selftest_")

        # 在线语音（主路径）是否可用
        from core.tts import synthesize, list_voices
        try:
            voices = list_voices()
            log(f"online voices: {len(voices)}")
            _, eng = synthesize("在线语音自检。", os.path.join(tmpdir, "online"))
            log("online tts engine: " + eng)
        except Exception as e:  # noqa: BLE001
            log(f"online tts unavailable: {e}")

        img = os.path.join(tmpdir, "img.jpg")
        run_ffmpeg(["-f", "lavfi", "-i", "color=c=steelblue:s=1280x720:d=1",
                    "-frames:v", "1", img])
        log("image ok, exists=" + str(os.path.isfile(img)))
        out = os.path.join(tmpdir, "out.mp4")
        build_video(
            items=[{"text": "打包自检，检查视频生成是否正常。", "image": img}],
            output_path=out, prefer_offline=True,
            width=1280, height=720, fps=24, show_subtitles=True,
        )
        log(f"video ok, duration={probe_duration(out):.2f}s, size={os.path.getsize(out)}")
        log("SELFTEST OK")
        code = 0
    except Exception:
        log("SELFTEST FAILED\n" + traceback.format_exc())
        code = 1

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    from app.gui import run
    _enable_dpi_awareness()
    run()
