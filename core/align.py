# -*- coding: utf-8 -*-
"""图文对齐：支持段落数 ≠ 图片数 的多种生成规则。"""

MODE_AUTO = "auto"        # 自动分组：连续段落平均合并到每张图片
MODE_CYCLE = "cycle"      # 图片循环：每段独立，图片按顺序循环复用
MODE_STRICT = "strict"    # 严格一致：数量不相等则报错

MODE_LABELS = {
    MODE_AUTO: "自动分组（多段文字合并到每张图）",
    MODE_CYCLE: "图片循环（每段一段，图片轮流复用）",
    MODE_STRICT: "严格一一对应（数量必须相等）",
}


def _join_text(texts: list) -> str:
    """把同组的多个段落拼成一段解说文本。"""
    parts = []
    for t in texts:
        t = t.strip()
        if not t:
            continue
        # 已是标点结尾的直接接上，否则补句号，避免朗读时粘连
        if t[-1] not in "。！？!?…；;：:":
            t += "。"
        parts.append(t)
    return "".join(parts)


def align(paragraphs: list, images: list, mode: str = MODE_AUTO):
    """返回 (items, notes)。

    items: [{"text": str, "image": str, "source_count": int}, ...]
    notes: 给用户看的提示信息列表
    """
    paras = [p.strip() for p in paragraphs if p.strip()]
    imgs = list(images)
    notes = []
    if not paras:
        raise ValueError("没有可用的文字段落")
    if not imgs:
        raise ValueError("没有选择图片")

    if mode == MODE_STRICT:
        if len(paras) != len(imgs):
            raise ValueError(
                f"严格模式下段落数（{len(paras)}）与图片数（{len(imgs)}）必须相等")
        items = [{"text": t, "image": i, "source_count": 1} for t, i in zip(paras, imgs)]
        return items, notes

    if mode == MODE_CYCLE:
        items = [
            {"text": t, "image": imgs[i % len(imgs)], "source_count": 1}
            for i, t in enumerate(paras)
        ]
        if len(paras) > len(imgs):
            notes.append(f"{len(paras)} 段文字循环使用 {len(imgs)} 张图片")
        return items, notes

    # MODE_AUTO：段落多于图片 -> 平均分组合并；段落少于图片 -> 忽略多余图片
    n_img = len(imgs)
    n_par = len(paras)
    if n_par == n_img:
        items = [{"text": t, "image": i, "source_count": 1} for t, i in zip(paras, imgs)]
        return items, notes

    if n_par < n_img:
        items = [
            {"text": paras[i], "image": imgs[i], "source_count": 1}
            for i in range(n_par)
        ]
        notes.append(
            f"段落数（{n_par}）少于图片数（{n_img}），仅使用前 {n_par} 张图片")
        return items, notes

    base, extra = divmod(n_par, n_img)
    items = []
    idx = 0
    for i in range(n_img):
        take = base + (1 if i < extra else 0)
        group = paras[idx:idx + take]
        idx += take
        items.append({
            "text": _join_text(group),
            "image": imgs[i],
            "source_count": len(group),
        })
    sizes = [it["source_count"] for it in items]
    notes.append(
        f"{n_par} 段文字合并为 {n_img} 段（各段合并 {sizes} 个原始段落）")
    return items, notes


def preview(paragraphs: list, images: list, mode: str = MODE_AUTO,
            rate_percent: int = 0) -> str:
    """给界面用的一行预览说明（含预计时长）。"""
    n_par, n_img = len(paragraphs), len(images)
    try:
        items, _ = align(paragraphs, images, mode)
    except Exception as e:  # noqa: BLE001
        return f"⚠ {e}"
    total_chars = sum(len(it["text"]) for it in items)
    # 中文约 4.4 字/秒（语速 0%），再按段尾停顿估算
    cps = max(1.5, 4.4 * (1 + rate_percent / 100.0))
    est = total_chars / cps + len(items) * 0.4
    mm, ss = divmod(int(round(est)), 60)
    dur = f"{mm} 分 {ss} 秒" if mm else f"{ss} 秒"
    return (f"{n_par} 段文字 + {n_img} 张图片 → 生成 {len(items)} 个视频段落，"
            f"共约 {total_chars} 字，预计时长 {dur}")
