# -*- coding: utf-8 -*-
"""项目文件（.t2v）：把文字、图片、参数存成 JSON，下次一键恢复。"""
import json
import os

VERSION = 1
EXT = ".t2v"


def save(path: str, data: dict) -> str:
    payload = dict(data)
    payload["version"] = VERSION
    if not path.lower().endswith(EXT):
        path += EXT
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("项目文件格式不正确")
    # 图片路径失效时给出提示信息，由界面决定如何提示
    data["_missing_images"] = [
        p for p in data.get("images", []) if p and not os.path.isfile(p)
    ]
    return data
