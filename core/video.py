# -*- coding: utf-8 -*-
"""视频合成管线：图片(+轮播) -> Ken Burns 动效分段 -> 转场拼接 -> 字幕/音乐/片头片尾。

设计要点：
- 每段一次 ffmpeg 编码（多图轮播在同一个 filter_complex 内完成）
- 转场用 xfade + acrossfade，时间轴按重叠量精确补偿，字幕时间跟着一起算
- 片头片尾是独立卡片片段，最后统一拼接
"""
import math
import os
import shutil
import tempfile

from .tts import synthesize
from .utils import Cancelled, probe_duration, run_ffmpeg, set_cancel_checker


def _check(cancel):
    if cancel is not None and cancel():
        raise Cancelled("已取消生成")


# ---------------------------------------------------------------- 滤镜

def _prep(i: int, w: int, h: int, fit_mode: str) -> str:
    """把第 i 个输入铺满/适配到 2 倍画布（放大 2 倍再动效，减少抖动）。"""
    w2, h2 = w * 2, h * 2
    if fit_mode == "blur":
        qw, qh = max(2, w // 4), max(2, h // 4)
        return (
            f"[{i}:v]scale={qw}:{qh}:force_original_aspect_ratio=increase,"
            f"crop={qw}:{qh},gblur=sigma=12,scale={w2}:{h2}[bg{i}];"
            f"[{i}:v]scale={w2}:{h2}:force_original_aspect_ratio=decrease[fg{i}];"
            f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2,setsar=1[base{i}];"
        )
    return (
        f"[{i}:v]scale={w2}:{h2}:force_original_aspect_ratio=increase,"
        f"crop={w2}:{h2},setsar=1[base{i}];"
    )


def _zoompan(variant: int, w: int, h: int, fps: int, frames: int, motion: float = 1.0) -> str:
    """Ken Burns 运镜；motion=0 时静止，1 为默认幅度 12%。"""
    amt = 0.12 * max(0.0, motion)
    if amt < 0.005:
        return (f"zoompan=z='1.001':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={fps}")
    inc = amt / max(frames, 1)
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    variants = [
        f"zoompan=z='min(1+{inc:.6f}*on,{1 + amt:.4f})':d={frames}:x='{cx}':y='{cy}':s={w}x{h}:fps={fps}",
        f"zoompan=z='max({1 + amt:.4f}-{inc:.6f}*on,1.0)':d={frames}:x='{cx}':y='{cy}':s={w}x{h}:fps={fps}",
        f"zoompan=z='{1 + amt * 0.8:.4f}':d={frames}:x='(iw-iw/zoom)*on/{frames}':y='{cy}':s={w}x{h}:fps={fps}",
        f"zoompan=z='{1 + amt * 0.8:.4f}':d={frames}:x='(iw-iw/zoom)*(1-on/{frames})':y='{cy}':s={w}x{h}:fps={fps}",
        f"zoompan=z='min(1+{inc:.6f}*on,{1 + amt:.4f})':d={frames}:x='{cx}':y='(ih-ih/zoom)*on/{frames}':s={w}x{h}:fps={fps}",
    ]
    return variants[variant % len(variants)]


def make_segment(
    images,
    audio: str,
    out_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    variant: int = 0,
    tail: float = 0.4,
    fit_mode: str = "cover",
    motion: float = 1.0,
    slice_seconds: float = 0.0,
    fast: bool = False,
) -> float:
    """生成一段视频：一张或多张图轮播 + 该段配音。返回总时长（秒）。

    images 为列表且 slice_seconds>0 时，按每张停留 slice_seconds 秒轮播（循环使用）。
    """
    audio_dur = probe_duration(audio)
    total = audio_dur + tail
    imgs = [images] if isinstance(images, str) else [p for p in images if p]
    if not imgs:
        raise ValueError("这一段没有可用图片")

    if slice_seconds and slice_seconds > 0 and len(imgs) > 1 and total > slice_seconds * 1.3:
        n = max(2, int(math.ceil(total / slice_seconds)))
    else:
        n = 1
    slices = [imgs[i % len(imgs)] for i in range(n)]

    total_frames = max(2, round(total * fps))
    base_frames = max(1, total_frames // n)
    frames_list = [base_frames] * n
    frames_list[-1] = max(1, total_frames - base_frames * (n - 1))

    args = []
    for p in slices:
        args += ["-i", p]
    args += ["-i", audio]

    parts, tags = [], []
    for i, frames in enumerate(frames_list):
        parts.append(
            _prep(i, width, height, fit_mode)
            + f"[base{i}]{_zoompan(variant + i, width, height, fps, frames, motion)},"
            + f"trim=end_frame={frames},setpts=PTS-STARTPTS,setsar=1[v{i}]"
        )
        tags.append(f"[v{i}]")

    audio_idx = len(slices)
    fc = (
        ";".join(parts)
        + ";"
        + "".join(tags)
        + f"concat=n={n}:v=1:a=0,format=yuv420p[v];"
        + f"[{audio_idx}:a]apad=pad_dur={tail:.3f},aresample=44100[a]"
    )

    args += [
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264",
        # 片段后面还要再编码一次（烧字幕/转场）时用快速预设 + 低 CRF 做中间件
        "-preset", "veryfast" if fast else "medium",
        "-crf", "16" if fast else "19",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    run_ffmpeg(args, on_fail_hint=f"生成片段失败: {slices[0]}")
    return total


# ---------------------------------------------------------------- 拼接

def concat_segments(seg_paths: list, out_path: str) -> None:
    """无损拼接规格一致的分段视频。"""
    if len(seg_paths) == 1:
        shutil.copyfile(seg_paths[0], out_path)
        return
    lst = out_path + ".txt"
    with open(lst, "w", encoding="utf-8") as f:
        for p in seg_paths:
            f.write("file '" + os.path.abspath(p).replace("'", "'\\''") + "'\n")
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_path],
        on_fail_hint="拼接视频失败",
    )
    os.remove(lst)


def concat_with_transition(seg_paths: list, out_path: str, transition: str,
                           td: float) -> None:
    """用 xfade + acrossfade 做段落转场。"""
    if transition in ("", "none") or len(seg_paths) < 2 or td <= 0:
        concat_segments(seg_paths, out_path)
        return

    durations = [probe_duration(p) for p in seg_paths]
    td = min(td, min(durations) * 0.45)          # 段落太短时自动收窄
    if td <= 0.05:
        concat_segments(seg_paths, out_path)
        return

    args = []
    for p in seg_paths:
        args += ["-i", p]

    vparts, aparts = [], []
    cur_v, cur_a = "[0:v]", "[0:a]"
    t = durations[0]
    for i in range(1, len(seg_paths)):
        off = max(0.0, t - td)
        nv, na = f"[vx{i}]", f"[ax{i}]"
        vparts.append(
            f"{cur_v}[{i}:v]xfade=transition={transition}:duration={td:.3f}:"
            f"offset={off:.3f}{nv}")
        aparts.append(f"{cur_a}[{i}:a]acrossfade=d={td:.3f}:c1=tri:c2=tri{na}")
        cur_v, cur_a = nv, na
        t = t + durations[i] - td

    fc = ";".join(vparts + aparts)
    args += [
        "-filter_complex", fc,
        "-map", cur_v, "-map", cur_a,
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    run_ffmpeg(args, on_fail_hint="转场拼接失败")


def timeline(durations: list, td: float = 0.0):
    """按转场重叠量计算每段起点与总时长。"""
    starts, t = [], 0.0
    n = len(durations)
    for i, d in enumerate(durations):
        starts.append(t)
        t += d - (td if i < n - 1 else 0)
    return starts, max(0.0, t)


# ---------------------------------------------------------------- 收尾

def finalize(
    concat_path: str,
    ass_path: str,
    bgm_path: str,
    out_path: str,
    bgm_volume: float = 0.22,
    total_duration: float = 0.0,
) -> None:
    """最终处理：烧录字幕 + 混入背景音乐（自动循环/淡出）。"""
    has_subs = bool(ass_path and os.path.isfile(ass_path))
    has_bgm = bool(bgm_path and os.path.isfile(bgm_path))
    vf = ""
    if has_subs:
        subs_arg = ass_path.replace("\\", "/").replace(":", "\\:")
        vf = f"subtitles='{subs_arg}'"

    dt = f"{total_duration:.3f}"
    if has_bgm:
        fc = (
            "[1:a]volume={v},afade=t=out:st={fo}:d=2[b];"
            "[0:a][b]amix=inputs=2:duration=first:dropout_transition=0[a]"
        ).format(v=bgm_volume, fo=max(0.0, total_duration - 2))
        args = ["-i", concat_path, "-stream_loop", "-1", "-i", bgm_path, "-t", dt,
                "-filter_complex", fc, "-map", "0:v", "-map", "[a]"]
        if vf:
            args += ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        else:
            args += ["-c:v", "copy"]
        args += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                 "-movflags", "+faststart", out_path]
    elif has_subs:
        args = ["-i", concat_path, "-vf", vf,
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "copy", "-movflags", "+faststart", out_path]
    else:
        args = ["-i", concat_path, "-c", "copy",
                "-movflags", "+faststart", out_path]
    run_ffmpeg(args, on_fail_hint="字幕/背景音乐合成失败")


class ProgressReporter:
    """简单的进度回调包装：stage, done, total, message。"""

    def __init__(self, callback=None):
        self.callback = callback

    def report(self, stage: str, done: int, total: int, message: str = ""):
        if self.callback:
            try:
                self.callback(stage, done, total, message)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------- 主入口

def build_video(
    items: list,
    output_path: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    rate_percent: int = 0,
    tts_engine: str = "auto",
    prefer_offline: bool = False,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    bgm_path: str = "",
    bgm_volume: float = 0.22,
    show_subtitles: bool = True,
    subtitle_style: dict = None,
    fit_mode: str = "cover",
    image_mode: str = "single",
    rotate_seconds: float = 4.0,
    transition: str = "none",
    transition_duration: float = 0.6,
    motion: float = 1.0,
    intro: dict = None,
    outro: dict = None,
    srt_path: str = "",
    progress=None,
    cancel=None,
) -> str:
    """主入口。

    items: [{"text": str, "image": str}, ...]
    intro/outro: {"enabled","title","subtitle","duration","image","voice_text"}
    返回输出文件路径。
    """
    if not items:
        raise ValueError("没有可用的图文段落")
    rep = ProgressReporter(progress)
    tmpdir = tempfile.mkdtemp(prefix="t2v_")
    total = len(items)
    td = float(transition_duration) if transition not in ("", "none") else 0.0
    tail = max(0.4, td + 0.2) if td else 0.4
    set_cancel_checker(cancel)

    try:
        # ---------- 1) 逐段：配音 + 画面 ----------
        seg_paths, seg_meta = [], []
        used_offline = 0
        # 后面还要再编码一次（烧字幕/混音乐）时，片段用快速预设做中间件，省时间
        fast_seg = bool(show_subtitles or (bgm_path and os.path.isfile(bgm_path)))
        for i, item in enumerate(items):
            _check(cancel)
            rep.report("tts", i, total, f"合成第 {i + 1}/{total} 段语音")
            audio_base = os.path.join(tmpdir, f"audio_{i:03d}")
            audio_path, engine, words = synthesize(
                item["text"], audio_base,
                voice=voice, rate_percent=rate_percent,
                engine=tts_engine, prefer_offline=prefer_offline,
                with_words=True,
            )
            if engine == "offline":
                used_offline += 1

            rep.report("video", i, total, f"生成第 {i + 1}/{total} 段画面")
            seg_path = os.path.join(tmpdir, f"seg_{i:03d}.mp4")
            images = [item["image"]]
            if image_mode == "rotate":
                # 开启轮播时，从该段对应的图开始，把整组图依次铺满这段时长
                pool = [it["image"] for it in items]
                pool += [it.get("extra") for it in items if it.get("extra")]
                try:
                    start = pool.index(item["image"])
                except ValueError:
                    start = 0
                seen = [item["image"]]
                j = 1
                while len(seen) < len(pool):
                    img = pool[(start + j) % len(pool)]
                    if img and img not in seen:
                        seen.append(img)
                    j += 1
                    if j > len(pool) * 2:
                        break
                images = seen

            dur = make_segment(
                images, audio_path, seg_path,
                width=width, height=height, fps=fps,
                variant=i, tail=tail, fit_mode=fit_mode, motion=motion,
                slice_seconds=rotate_seconds if image_mode == "rotate" else 0.0,
                fast=fast_seg,
            )
            seg_paths.append(seg_path)
            seg_meta.append({"text": item["text"], "duration": dur, "kind": "content",
                             "words": words})

        if used_offline:
            rep.report("video", total, total, f"有 {used_offline} 段使用了系统离线语音")

        # ---------- 2) 片头 / 片尾 ----------
        _check(cancel)
        first_img = items[0]["image"]

        def _add_card(cfg: dict, tag: str, fallback_img: str):
            img = cfg.get("image") or fallback_img
            head = (cfg.get("title") or "").strip()
            if not head:
                return
            rep.report("card", 0, 1, f"生成{tag}")
            audio = ""
            voice_text = (cfg.get("voice_text") or "").strip()
            if voice_text:
                try:
                    audio, _ = synthesize(
                        voice_text, os.path.join(tmpdir, f"{tag}_voice"),
                        voice=voice, rate_percent=rate_percent,
                        engine=tts_engine, prefer_offline=prefer_offline,
                    )
                except Exception:  # noqa: BLE001  配音失败不影响卡片生成
                    audio = ""
            from .cards import make_card
            path = os.path.join(tmpdir, f"{tag}.mp4")
            d = make_card(
                img, head, (cfg.get("subtitle") or "").strip(), path,
                width=width, height=height, fps=fps,
                duration=float(cfg.get("duration") or 3.0),
                audio=audio, workdir=tmpdir,
                color=(subtitle_style or {}).get("color", "#FFFFFF"),
            )
            seg_paths.insert(0 if tag == "intro" else len(seg_paths), path)
            seg_meta.insert(0 if tag == "intro" else len(seg_meta),
                            {"text": "", "duration": d, "kind": tag})

        if intro and intro.get("enabled"):
            _add_card(intro, "intro", first_img)
        if outro and outro.get("enabled"):
            _add_card(outro, "outro", first_img)

        # ---------- 3) 拼接 ----------
        _check(cancel)
        # 用文件真实时长算时间轴（与 xfade 的 offset 完全一致），避免字幕累积漂移
        durations = []
        for i, p in enumerate(seg_paths):
            d = 0.0
            try:
                d = probe_duration(p)
            except Exception:  # noqa: BLE001
                d = 0.0
            if not d or d < 0.2:
                d = float(seg_meta[i]["duration"])
            durations.append(d)
        starts, total_dur = timeline(durations, td)
        rep.report("concat", 0, 1, "拼接视频片段")
        concat_path = os.path.join(tmpdir, "concat.mp4")
        concat_with_transition(seg_paths, concat_path, transition, td)

        # ---------- 4) 字幕 ----------
        sub_segments = [
            {"text": m["text"], "duration": durations[i], "start": starts[i],
             "words": m.get("words") or []}
            for i, m in enumerate(seg_meta) if m["text"]
        ]
        ass_path = ""
        if show_subtitles and sub_segments:
            _check(cancel)
            rep.report("finalize", 0, 1, "生成字幕")
            from .subtitles import build_ass
            ass_path = os.path.join(tmpdir, "subs.ass")
            build_ass(sub_segments, ass_path, width=width, height=height,
                      style=subtitle_style, tail=tail)

        if srt_path and sub_segments:
            try:
                from .subtitles import build_srt
                build_srt(sub_segments, srt_path, style=subtitle_style, tail=tail)
                rep.report("finalize", 0, 1, f"字幕文件已导出：{os.path.basename(srt_path)}")
            except Exception:  # noqa: BLE001
                pass

        # ---------- 5) 烧录字幕 + 混音 ----------
        _check(cancel)
        rep.report("finalize", 0, 1, "烧录字幕与背景音乐")
        finalize(concat_path, ass_path, bgm_path, output_path,
                 bgm_volume=bgm_volume, total_duration=total_dur)
        rep.report("done", 1, 1, f"完成：{output_path}")
        return output_path
    finally:
        set_cancel_checker(None)
        shutil.rmtree(tmpdir, ignore_errors=True)
