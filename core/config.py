# -*- coding: utf-8 -*-
"""平台预设与各类默认参数（自媒体常用尺寸/字幕安全区）。"""

# 每个平台预设：宽高、字幕默认字号、字幕距边（安全区）、每行字数
PLATFORMS = [
    {
        "key": "douyin",
        "label": "抖音 / 快手（竖屏 1080×1920）",
        "w": 1080, "h": 1920,
        "sub_size": 62, "sub_margin": 340, "sub_chars": 15,
    },
    {
        "key": "wxchannel",
        "label": "视频号（竖屏 1080×1920）",
        "w": 1080, "h": 1920,
        "sub_size": 58, "sub_margin": 280, "sub_chars": 15,
    },
    {
        "key": "xhs",
        "label": "小红书（竖屏 3:4 · 1080×1440）",
        "w": 1080, "h": 1440,
        "sub_size": 54, "sub_margin": 180, "sub_chars": 16,
    },
    {
        "key": "bili",
        "label": "B 站 / 西瓜（横屏 1920×1080）",
        "w": 1920, "h": 1080,
        "sub_size": 44, "sub_margin": 70, "sub_chars": 24,
    },
    {
        "key": "v720",
        "label": "竖屏 720p（省流量）",
        "w": 720, "h": 1280,
        "sub_size": 42, "sub_margin": 230, "sub_chars": 10,
    },
    {
        "key": "h720",
        "label": "横屏 720p（省流量）",
        "w": 1280, "h": 720,
        "sub_size": 30, "sub_margin": 46, "sub_chars": 24,
    },
    {
        "key": "square",
        "label": "正方形 1:1（1080×1080）",
        "w": 1080, "h": 1080,
        "sub_size": 52, "sub_margin": 90, "sub_chars": 16,
    },
]

POSITION_LABELS = {
    "bottom": "底部",
    "center": "画面中央",
    "top": "顶部",
}

TRANSITIONS = [
    ("none", "无转场（硬切）"),
    ("fade", "淡入淡出"),
    ("dissolve", "溶解"),
    ("slideleft", "向左推移"),
    ("slideup", "向上推移"),
    ("circleopen", "圆形展开"),
]

FIT_MODES = [
    ("cover", "裁剪铺满（画面撑满，边缘裁掉）"),
    ("blur", "模糊背景（完整保留画面，两侧/上下补模糊）"),
]

IMAGE_MODES = [
    ("single", "每段固定一张图"),
    ("rotate", "多图自动轮播"),
]

MOTIONS = [
    (0.0, "关闭"),
    (0.6, "轻微"),
    (1.0, "标准"),
    (1.6, "明显"),
]


def by_label(label: str) -> dict:
    for p in PLATFORMS:
        if p["label"] == label:
            return p
    return PLATFORMS[0]


def by_key(key: str) -> dict:
    for p in PLATFORMS:
        if p["key"] == key:
            return p
    return PLATFORMS[0]


def platform_labels() -> list:
    return [p["label"] for p in PLATFORMS]


def hex_to_ass(color: str, alpha: int = 0) -> str:
    """#RRGGBB -> ASS 的 &HAABBGGRR。"""
    c = (color or "#FFFFFF").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        c = "FFFFFF"
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return f"&H{alpha & 0xFF:02X}{b:02X}{g:02X}{r:02X}"


def default_subtitle_style(platform_key: str = "douyin") -> dict:
    """按平台给一套好用的字幕默认样式。"""
    p = by_key(platform_key)
    return {
        "font": "Microsoft YaHei",
        "size": p["sub_size"],
        "color": "#FFFFFF",
        "outline_color": "#000000",
        "outline": 2.4 if p["h"] >= 1000 else 1.8,
        "shadow": 1.0,
        "bold": True,
        "position": "bottom",
        "margin": p["sub_margin"],
        "max_chars": p["sub_chars"],
    }


def normalize_style(style: dict, width: int, height: int) -> dict:
    """补全/校正字幕样式；max_chars 按实际画布宽度收敛。"""
    st = dict(style or {})
    st.setdefault("font", "Microsoft YaHei")
    st.setdefault("color", "#FFFFFF")
    st.setdefault("outline_color", "#000000")
    st.setdefault("outline", 2.4)
    st.setdefault("shadow", 1.0)
    st.setdefault("bold", True)
    st.setdefault("position", "bottom")
    size = int(st.get("size") or max(24, round(height / 26)))
    st["size"] = max(12, min(160, size))
    # 一行能放多少字，取平台默认与实际宽度中更保守的一个
    by_width = max(6, int(width / max(1, st["size"]) * 1.05))
    st["max_chars"] = int(min(st.get("max_chars") or by_width, by_width, 26))
    st["margin"] = int(max(0, st.get("margin") or 0))
    if st["position"] not in POSITION_LABELS:
        st["position"] = "bottom"
    return st
