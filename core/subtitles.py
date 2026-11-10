# -*- coding: utf-8 -*-
"""ASS 字幕文件生成：按句切分、按字数分配时间，长文本自动分多条显示。"""
import re

from .config import hex_to_ass, normalize_style

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{size},{primary},{primary},{outline_c},&H64000000,{bold},0,0,0,100,100,0,0,1,{ow},{shadow},{align},{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# 位置 -> (ASS Alignment, MarginV 取法)
_POS_ALIGN = {"bottom": 2, "center": 5, "top": 8}

# 句子结束符
_SENT_END = "。！？!?…；;"


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def split_sentences(text: str) -> list:
    """按句末标点和换行切句，保留标点。"""
    text = text.replace("\r", "")
    out = []
    buf = ""
    for ch in text:
        if ch == "\n":
            if buf.strip():
                out.append(buf.strip())
            buf = ""
            continue
        buf += ch
        if ch in _SENT_END:
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())

    # 过长的句子再按逗号切开，保证单句不会太长
    result = []
    for s in out:
        if len(s) <= 60:
            result.append(s)
            continue
        cur = ""
        for part in re.split(r"(?<=[，,、])", s):
            if cur and len(cur) + len(part) > 44:
                result.append(cur)
                cur = part
            else:
                cur += part
        if cur.strip():
            result.append(cur.strip())
    return [s for s in result if s]


def _ch_width(ch: str) -> float:
    """估算字符显示宽度：中文/全角算 1，ASCII 算 0.55。"""
    return 1.0 if ord(ch) > 127 else 0.55


def _width(s: str) -> float:
    return sum(_ch_width(c) for c in s)


MIDDOTS = "·・‧•･"          # 各种"间隔号"变体，都不能出现在行首/行尾
BAD_END = MIDDOTS + "《（(【、-—"
BAD_START = MIDDOTS + "》），,、。！？：:"
PUNCT = "，,、；;。！？：:）》)”"

# 不会真正"读出来"的字符（标点/括号/引号/空白），用于对齐词级时间戳
_NON_SPOKEN = set("，,、；;。！？!?…—－~～:：\"'“”‘’《》〈〉「」『』【】（）()[]<>·・‧•･ \t\r\n　")
# 行尾/句尾可以安全去掉的标点
_TAIL_STRIP = "，,、；;。！？!?…—－~～:：\"'“”‘’" + MIDDOTS + \
              "）》」』】〉)〉 \t\r\n　"
# 右引号/右括号 -> 对应的左侧符号（避免把引号去掉一半）
_PAIRS = {"”": "“", "’": "‘", "》": "《", "」": "「", "』": "『",
          "）": "（", ")": "(", "】": "【", "〉": "〈"}


def _strip_tail_punct(s: str) -> str:
    """去掉句尾/行尾的标点符号（保留数字里的点、保留成对引号的右半边）。"""
    s = (s or "").rstrip()
    keep = ""
    while s:
        c = s[-1]
        if c in _PAIRS and s.count(_PAIRS[c]) >= s.count(c):
            # 去掉就只剩左引号了：先留着，继续往前清理（如 “好的。”
            keep = c + keep
            s = s[:-1].rstrip()
            continue
        if c in _TAIL_STRIP:
            s = s[:-1].rstrip()
            continue
        if c in ".．" and not (len(s) > 1 and s[-2].isdigit()):
            s = s[:-1].rstrip()
            continue
        break
    return s + keep


def _spoken_len(s: str) -> int:
    """真正会被读出来的字符数（不算标点、括号、空白）。"""
    return sum(1 for c in s if c not in _NON_SPOKEN and not c.isspace())


def _smart_cut(s: str, limit: float) -> int:
    """在不超过 limit 宽度的前提下，找一个观感好的切点下标（1..len(s)）。"""
    acc, i = 0.0, 0
    while i < len(s) and acc + _ch_width(s[i]) <= limit:
        acc += _ch_width(s[i])
        i += 1
    if i >= len(s):
        return len(s)

    cut = max(1, i)
    # 1) 优先断在标点后（只在接近行宽时才采用，避免行首浪费太多空间）
    floor = max(2, int(i * 0.85))
    for j in range(cut, floor, -1):
        if s[j - 1] in PUNCT:
            return j
    # 2) 英文单词中间不切：回退到最近的空格
    if s[cut - 1].isascii() and s[cut].isascii() \
            and s[cut - 1].isalnum() and s[cut].isalnum():
        sp = s.rfind(" ", max(0, cut - 16), cut)
        if sp > floor:
            return sp + 1
    # 3) 行尾不留间隔号/左括号
    while cut > 1 and s[cut - 1] in BAD_END:
        cut -= 1
    # 3.5) 不切在书名号/括号/引号中间（退到左符号前，太靠前就算了）
    for op, cl in (("《", "》"), ("（", "）"), ("(", ")"), ("「", "」"),
                   ("【", "】"), ("“", "”"), ("『", "』")):
        lp = s.rfind(op, 0, cut)
        if lp >= 0 and s.find(cl, lp, cut) < 0 and lp + 1 < cut:
            if lp >= max(2, int(cut * 0.55)):
                cut = lp
            break
    # 4) 行首不以标点开头；若是间隔号，则把整个名字一起挪到下一行
    if cut < len(s) and s[cut] in BAD_START:
        if s[cut] in MIDDOTS:
            j, steps = cut, 0
            while j > 1 and steps < 5 and (
                    s[j - 1] in MIDDOTS
                    or s[j - 1].isalnum()
                    or "\u4e00" <= s[j - 1] <= "\u9fff"):
                j -= 1
                steps += 1
            cut = max(1, j)
            while cut > 1 and s[cut - 1] in BAD_END:
                cut -= 1
        else:
            cut = max(1, cut - 1)
    return cut


def _wrap(chunk: str, max_chars: int, max_lines: int, strip_punct: bool = True) -> str:
    """按显示宽度换行，最多 max_lines 行，用 \\N 连接。"""
    lines, s = [], chunk
    while s and len(lines) < max_lines:
        cut = _smart_cut(s, max_chars)
        if cut >= len(s):
            lines.append(s)
            s = ""
            break
        # 别把最后一行挤成一个孤零零的字
        while cut > 1 and len(_strip_tail_punct(s[cut:])) <= 1:
            cut -= 1
        lines.append(s[:cut])
        s = s[cut:].lstrip(" ")   # 只回退不跳过，保证不丢字符
    if s:  # 超出最大行数时余量并入最后一行
        lines[-1] += s
    if strip_punct:
        cleaned = [_strip_tail_punct(x) for x in lines]
        cleaned = [x for x in cleaned if x]
        if cleaned:                      # 极端情况下别把整行删空
            lines = cleaned
    return "\\N".join(lines)


def _make_cues(text: str, max_chars: int = 24, max_lines: int = 2) -> list:
    """把一段文字切成若干"屏"字幕，每屏宽度不超过 max_chars * max_lines。"""
    limit = max_chars * max_lines
    cues = []
    cur = ""
    for sent in split_sentences(text):
        if not cur:
            cur = sent
        elif _width(cur) + _width(sent) <= limit:
            cur += sent
        else:
            cues.append(cur)
            cur = sent
    if cur:
        cues.append(cur)

    # 单屏仍然超宽（如长英文名）时按宽度强制切块
    final = []
    for c in cues:
        s = c
        while _width(s) > limit:
            cut = _smart_cut(s, limit)
            if cut >= len(s):
                break
            final.append(s[:cut].strip())
            s = s[cut:].lstrip(" ")
        if s.strip():
            final.append(s.strip())

    # 末尾只剩一两个字时并回上一屏，避免一闪而过的残句
    if len(final) > 1 and _width(final[-1]) < 8:
        final[-2] = final[-2] + final[-1]
        final.pop()
    return final


def _word_spans(words, text: str = "") -> list:
    """把词级时间戳转成 [(起始字序号, 结束字序号, 开始秒, 结束秒), ...]。

    传入原文时会做一次轻量对齐：原文里的符号（如 +、&）可能不发音、
    也不在词表里，靠字符数累加会越错越多，这里用词本身去原文里找位置自我校正。
    """
    src = "".join(c for c in (text or "")
                  if c not in _NON_SPOKEN and not c.isspace())
    spans, n = [], 0
    for w in words or []:
        wt = "".join(c for c in (w.get("text") or "")
                     if c not in _NON_SPOKEN and not c.isspace())
        if not wt:
            continue
        try:
            t0 = float(w.get("start", 0.0))
            t1 = float(w.get("end", t0))
        except (TypeError, ValueError):
            continue
        k = len(wt)
        if src:
            pos = src.find(wt, max(0, n - 2))
            if pos >= 0 and abs(pos - n) <= 8:
                n = pos
        spans.append((n, n + k, t0, max(t1, t0)))
        n += k
    return spans


def _time_at(spans: list, idx: int, at_end: bool = False) -> float:
    """取第 idx 个字所在的词的开始/结束时间。"""
    for a, b, t0, t1 in spans:
        if a <= idx < b:
            return t1 if at_end else t0
    if not spans:
        return 0.0
    # 越界时（文本比词表长一点）贴到最后一个词
    return spans[-1][3] if at_end else spans[-1][2]


def _cue_weight(s: str) -> float:
    """按字数和停顿给一屏字幕估权重：句末标点后有明显停顿。"""
    w = 0.0
    for ch in s:
        if ch in "。！？!?…":
            w += 4.0
        elif ch in "；;，,、：:—":
            w += 1.5
        elif ch in _NON_SPOKEN or ch.isspace():
            continue
        else:
            w += 1.0
    return max(1.0, w)


def make_cues(segments: list, style: dict = None, tail: float = 0.4) -> list:
    """把分段文本切成带时间的字幕条目。

    segments: [{"text": str, "duration": float, "start": float(可选),
                "words": [{"start","end","text"}, ...](可选)}, ...]
    有 words（在线配音的词级时间戳）时按真实发音时间对齐，否则按字数和停顿估算。
    返回 [{"start","end","text"(已换行),"plain"}, ...]
    """
    st = dict(style or {})
    max_chars = int(st.get("max_chars") or 24)
    max_lines = 2
    strip_punct = st.get("strip_punct", True)
    tail = max(0.0, float(tail))

    out = []
    t = 0.0
    prev_end = 0.0
    for seg in segments:
        dur = float(seg.get("duration") or 0.0)
        start = float(seg.get("start", t))
        seg_end = start + dur
        cues = _make_cues(seg.get("text", ""), max_chars=max_chars, max_lines=max_lines)
        if cues:
            spoken = [_spoken_len(c) for c in cues]
            total_spoken = sum(spoken) or 1
            spans = _word_spans(seg.get("words"), seg.get("text", ""))
            # 词表覆盖度不足时（比如引擎没返回）退回估算，避免错位
            use_words = bool(spans) and spans[-1][1] >= max(1, int(total_spoken * 0.55))
            speak_dur = max(0.1, dur - tail)
            weights = [_cue_weight(c) for c in cues]
            total_w = sum(weights) or 1.0
            ct = start
            token = 0
            for i, cue in enumerate(cues):
                if use_words:
                    s = start + _time_at(spans, token, at_end=False)
                    e = start + _time_at(spans, max(token, token + spoken[i] - 1), at_end=True)
                    e += 0.15                     # 说完再稍留一点，避免字幕先消失
                    s = max(start, min(s, seg_end - 0.1))
                    e = min(e, seg_end - 0.03)
                else:
                    share = speak_dur * (weights[i] / total_w)
                    s, e = ct, ct + share
                    ct += share
                    e = min(e, seg_end - 0.03)
                token += spoken[i]
                if e - s < 0.55:                  # 太短的字幕稍微延长
                    e = min(s + 0.55, seg_end)
                if s < prev_end:                  # 不让两屏字幕叠在一起
                    s = prev_end
                if e <= s + 0.2:
                    e = min(s + 0.2, seg_end) if seg_end - s > 0.2 else seg_end
                if e <= s:
                    e = s + 0.05
                text = _wrap(cue, max_chars, max_lines, strip_punct)
                plain = _strip_tail_punct(cue) if strip_punct else cue
                if not plain:
                    plain = cue
                out.append({"start": s, "end": e, "text": text, "plain": plain})
                prev_end = e
        t = max(t, seg_end)
    return out


def build_ass(
    segments: list,
    out_path: str,
    width: int = 1920,
    height: int = 1080,
    style: dict = None,
    tail: float = 0.4,
) -> str:
    """生成 ASS 字幕（烧录用）。支持字号/颜色/描边/位置自定义。"""
    st = normalize_style(style, width, height)
    align = _POS_ALIGN.get(st["position"], 2)
    mv = st["margin"] if st["position"] in ("bottom", "top") else 0
    header = ASS_HEADER.format(
        w=width, h=height,
        font=st["font"], size=st["size"],
        primary=hex_to_ass(st["color"]),
        outline_c=hex_to_ass(st["outline_color"]),
        bold=-1 if st.get("bold") else 0,
        ow=st["outline"], shadow=st["shadow"],
        align=align, ml=40, mr=40, mv=mv,
    )

    events = []
    for c in make_cues(segments, st, tail=tail):
        events.append(
            f"Dialogue: 0,{_ts(c['start'])},{_ts(c['end'])},Sub,,0,0,0,,{c['text']}"
        )

    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_path


def _srt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:            # 四舍五入进位
        ms -= 1000
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list, out_path: str, style: dict = None, tail: float = 0.4) -> str:
    """导出 .srt 字幕文件（上传平台时可直接用）。"""
    st = dict(style or {})
    lines = []
    for i, c in enumerate(make_cues(segments, st, tail=tail), 1):
        lines.append(f"{i}\r\n{_srt_ts(c['start'])} --> {_srt_ts(c['end'])}\r\n{c['plain']}\r\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))
    return out_path
