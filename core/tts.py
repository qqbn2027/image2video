# -*- coding: utf-8 -*-
"""文字转语音：edge-tts 在线优先，Windows 离线（System.Speech）兜底。"""
import asyncio
import os
import re
import subprocess
import tempfile

# 离线兜底用 PowerShell System.Speech，避免 COM 线程问题，无需额外依赖
_POWERSHELL = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell",
    "v1.0", "powershell.exe",
)

# edge-tts 常用中文音色（作为在线获取音色列表失败时的默认项）
DEFAULT_VOICES = [
    "zh-CN-XiaoxiaoNeural",    # 女声 · 晓晓（活泼自然）
    "zh-CN-XiaoyiNeural",      # 女声 · 晓伊
    "zh-CN-YunxiNeural",       # 男声 · 云希（年轻）
    "zh-CN-YunjianNeural",     # 男声 · 云健（浑厚）
    "zh-CN-YunxiaNeural",      # 男声 · 云夏
    "zh-CN-liaoning-XiaobeiNeural",   # 东北话 · 晓北
    "zh-CN-shaanxi-XiaoniNeural",     # 陕西话 · 晓妮
    "zh-HK-HiuMaanNeural",     # 粤语 · 曼怡
    "zh-TW-HsiaoChenNeural",   # 中国台湾 · 晓臻
]

# edge-tts 语速百分比 -> System.Speech 语速(-10..10)
def _rate_to_sapi_rate(rate_percent: int) -> int:
    # +0% 对应 0，每 10% 约等于 SAPI 的 1 档
    return max(-10, min(10, round(rate_percent / 10)))


def _escape_ps(s: str) -> str:
    return s.replace("'", "''")


def _speak_offline_ps(text: str, out_path: str, rate_percent: int = 0) -> None:
    """使用 Windows 自带语音引擎离线合成 WAV。"""
    rate = _rate_to_sapi_rate(rate_percent)
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.Rate = {rate};"
        f"$s.SetOutputToWaveFile('{_escape_ps(out_path)}');"
        f"$s.Speak('{_escape_ps(text)}');"
        "$s.Dispose();"
    )
    proc = subprocess.run(
        [_POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise RuntimeError(f"离线语音合成失败: {proc.stderr[:300]}")


async def _edge_speak(text: str, voice: str, rate: str, out_path: str) -> list:
    """在线合成，同时收集词级时间戳（用于字幕精准对齐）。

    返回 [{"start": 秒, "end": 秒, "text": 词}, ...]；引擎不返回时为空列表。
    """
    import edge_tts
    communicate = edge_tts.Communicate(
        text, voice=voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset/duration 单位是 100 纳秒
                o = float(chunk.get("offset", 0)) / 1e7
                d = float(chunk.get("duration", 0)) / 1e7
                w = (chunk.get("text") or "").strip()
                if w:
                    words.append({"start": o, "end": o + d, "text": w})
    words.sort(key=lambda x: x["start"])
    return words


def synthesize(
    text: str,
    out_base: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    rate_percent: int = 0,
    engine: str = "auto",  # auto / edge / offline
    prefer_offline: bool = False,
    with_words: bool = False,
) -> tuple:
    """合成语音，返回 (实际音频路径, 使用的引擎名 edge/offline[, 词级时间戳])。

    out_base: 不含扩展名的输出路径；在线引擎输出 .mp3，离线引擎输出 .wav。
    engine='edge' 时只允许在线；'offline' 只用离线；
    'auto' 时按 prefer_offline 决定优先级，且失败自动切换。
    with_words=True 时多返回一个词级时间戳列表（离线引擎为空列表），
    字幕可以按真实发音时间对齐，不再靠字数估算。
    """
    text = text.strip()
    if not text:
        raise ValueError("要合成的文字为空")

    rate = f"{rate_percent:+d}%"
    out_edge = out_base + ".mp3"
    out_off = out_base + ".wav"
    tmp_edge = out_base + ".edge.mp3"
    tmp_off = out_base + ".off.wav"

    words_box = []

    def try_edge():
        words = asyncio.run(_edge_speak(text, voice, rate, tmp_edge))
        words_box[:] = words
        return os.path.isfile(tmp_edge) and os.path.getsize(tmp_edge) > 100

    def try_offline():
        _speak_offline_ps(text, tmp_off, rate_percent)
        return os.path.isfile(tmp_off) and os.path.getsize(tmp_off) > 100

    order = []
    if engine == "edge":
        order = [("edge", try_edge)]
    elif engine == "offline":
        order = [("offline", try_offline)]
    elif prefer_offline:
        order = [("offline", try_offline), ("edge", try_edge)]
    else:
        order = [("edge", try_edge), ("offline", try_offline)]

    last_err = None
    for name, fn in order:
        try:
            if fn():
                if name == "edge":
                    if os.path.isfile(out_edge):
                        os.remove(out_edge)
                    os.replace(tmp_edge, out_edge)
                    return (out_edge, "edge", words_box) if with_words else (out_edge, "edge")
                if os.path.isfile(out_off):
                    os.remove(out_off)
                os.replace(tmp_off, out_off)
                return (out_off, "offline", []) if with_words else (out_off, "offline")
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"语音合成失败（在线与离线均不可用）：{last_err}")


async def _list_edge_voices() -> list:
    import edge_tts
    voices = await edge_tts.list_voices()
    zh = [v["ShortName"] for v in voices if v["Locale"].lower().startswith("zh")]
    return zh or [v["ShortName"] for v in voices]


def list_voices() -> list:
    """在线获取 edge-tts 音色列表，失败时返回内置默认列表。"""
    try:
        return asyncio.run(asyncio.wait_for(_list_edge_voices(), timeout=15))
    except Exception:  # noqa: BLE001
        return list(DEFAULT_VOICES)
