from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
REEL_W, REEL_H = 1080, 1920
BG = (15, 15, 15)
FG = (245, 245, 245)
MUTED = (160, 160, 160)
ACCENT = (99, 102, 241)
SURFACE = (26, 26, 26)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    if bold:
        candidates = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            *candidates,
        ]
    for p in candidates:
        path = Path(p)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:8]


def _slide(text: str, idx: int, total: int, offer: str) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 12, H), fill=ACCENT)
    num = _font(28)
    body = _font(52, bold=True)
    foot = _font(22)
    d.text((64, 64), f"{idx + 1}/{total}", font=num, fill=MUTED)
    lines = _wrap(d, text, body, W - 128)
    y = 280
    for line in lines:
        d.text((64, y), line, font=body, fill=FG)
        y += 72
    d.text((64, H - 96), offer[:48], font=foot, fill=ACCENT)
    return img


def _reel_frame(line: str, idx: int, total: int, offer: str) -> Image.Image:
    img = Image.new("RGB", (REEL_W, REEL_H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, REEL_W, 16), fill=ACCENT)
    body = _font(56, bold=True)
    foot = _font(24)
    lines = _wrap(d, line, body, REEL_W - 120)
    y = 760
    for ln in lines:
        d.text((60, y), ln, font=body, fill=FG)
        y += 78
    d.text((60, REEL_H - 140), f"{idx + 1}/{total}  ·  {offer[:40]}", font=foot, fill=MUTED)
    return img


def render_pack(out_dir: str, slides: list[str], reel_script: str, offer: str) -> dict:
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, s in enumerate(slides):
        p = dest / f"slide_{i + 1:02d}.png"
        _slide(s, i, len(slides), offer).save(p, "PNG", optimize=True)
        paths.append(str(p))
    lines = [x.strip() for x in reel_script.split("|") if x.strip()] or slides[:5]
    reel_paths: list[str] = []
    for i, line in enumerate(lines):
        p = dest / f"reel_{i + 1:02d}.png"
        _reel_frame(line, i, len(lines), offer).save(p, "PNG", optimize=True)
        reel_paths.append(str(p))
    meta = dest / "pack.json"
    meta.write_text(
        json.dumps({"slides": paths, "reel_frames": reel_paths, "offer": offer}, indent=2),
        encoding="utf-8",
    )
    return {"slides": paths, "reel_frames": reel_paths}


_POOL: ProcessPoolExecutor | None = None


def pool(workers: int) -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=workers)
    return _POOL


def shutdown_pool() -> None:
    global _POOL
    if _POOL is not None:
        _POOL.shutdown(wait=False)
        _POOL = None
