# -*- coding: utf-8 -*-
"""片头 / 片尾卡片：背景图（模糊压暗）+ 居中大字，可选配音。"""
import os

from .config import hex_to_ass
from .utils import run_ffmpeg, probe_duration


def _esc(text: str) -> str:
    """去掉会破坏 ASS 语法的字符。"""
    return (text or "").replace("\\", "/").replace("{", "（").replace("}", "）").replace("\n", " ")


def _card_ass(headline: str, subline: str, out_path: str, width: int, height: int,
              color: str = "#FFFFFF", outline_color: str = "#000000") -> str:
    big = max(26, round(height * 0.062))
    small = max(16, round(height * 0.034))
    text = f"{{\\fs{big}\\b1}}{_esc(headline)}"
    if subline.strip():
        text += f"\\N{{\\fs{small}\\b0}}{_esc(subline)}"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Card,Microsoft YaHei,{big},{hex_to_ass(color)},{hex_to_ass(color)},{hex_to_ass(outline_color)},&H64000000,-1,0,0,0,100,100,2,0,1,3,1.5,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,9:59:59.99,Card,,0,0,0,,{text}
"""
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(header)
    return out_path


def make_card(
    image: str,
    headline: str,
    subline: str,
    out_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    duration: float = 3.0,
    audio: str = "",
    color: str = "#FFFFFF",
    outline_color: str = "#000000",
    workdir: str = "",
) -> float:
    """生成一张卡片视频（带静音/配音音轨），返回实际时长。"""
    if not image or not os.path.isfile(image):
        raise ValueError("片头/片尾需要一张背景图（留空时会用第一张插图）")

    if audio and os.path.isfile(audio):
        audio_dur = probe_duration(audio)
        duration = max(duration, audio_dur + 0.8)
    else:
        audio_dur = 0.0

    duration = max(1.2, float(duration))
    n = max(2, round(duration * fps))
    ass_path = os.path.join(workdir or os.path.dirname(out_path), "card.ass")
    _card_ass(headline, subline, ass_path, width, height, color, outline_color)
    subs_arg = ass_path.replace("\\", "/").replace(":", "\\:")

    qw, qh = max(2, width // 4), max(2, height // 4)
    vf = (
        f"scale={qw}:{qh}:force_original_aspect_ratio=increase,crop={qw}:{qh},"
        f"gblur=sigma=12,scale={width * 2}:{height * 2},"
        f"zoompan=z='min(1+0.04/{n}*on,1.04)':d={n}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},"
        f"eq=brightness=-0.10:saturation=0.95,"
        f"subtitles='{subs_arg}',"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.0, duration - 0.5):.2f}:d=0.5,"
        f"format=yuv420p"
    )

    args = ["-i", image]
    if audio and os.path.isfile(audio):
        args += ["-i", audio]
        amap = "1:a:0"
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = "1:a:0"
    args += [
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-map", "0:v:0", "-map", amap,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    run_ffmpeg(args, on_fail_hint="生成片头/片尾卡片失败")
    return duration
