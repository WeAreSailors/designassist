"""Image preparation shared by every renderer: crop to the layer's box around a focus point,
resize to the output resolution, apply filters, round corners / circle mask. The result is a
plain bitmap the SVG, PDF, PSD and Adobe exports place at x, y, w, h without further logic.

Cached in work/cache/ by content (source file + parameters), so re-renders are cheap.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from .project import ROOT

YUNET = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
FOCUS_WORDS = {"center": (0.5, 0.5), "top": (0.5, 0.0), "bottom": (0.5, 1.0), "left": (0.0, 0.5), "right": (1.0, 0.5),
               "top-left": (0.0, 0.0), "top-right": (1.0, 0.0), "bottom-left": (0.0, 1.0), "bottom-right": (1.0, 1.0)}
Image.MAX_IMAGE_PIXELS = 400_000_000


@dataclass
class Prepared:
    path: Path
    width: int  # pixels written
    height: int
    source_px: tuple  # source pixels that cover the box (w, h): effective resolution
    upscaled: float  # > 1 when the source had fewer pixels than the output needs
    alpha: bool


def open_image(path: Path) -> Image.Image:
    if path.suffix.lower() == ".heic":
        raise SystemExit(f"{path.name}: HEIC isn't readable here; export it as JPG/PNG first")
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode or im.mode == "P" else "RGB")
    return im


def faces(im: Image.Image) -> list[tuple[float, float, float, float, float]]:
    """Faces as (x, y, w, h, score) in pixels (YuNet)."""
    import cv2
    import numpy as np

    try:  # YuNet prints a "setPreferableTarget" WARN on stderr every call; it's harmless noise
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        pass
    small = im.convert("RGB")
    scale = min(1.0, 960 / max(small.size))
    if scale < 1:
        small = small.resize((round(small.width * scale), round(small.height * scale)))
    arr = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2BGR)
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (arr.shape[1], arr.shape[0]), 0.7)
    _, found = det.detect(arr)
    if found is None:
        return []
    return [(f[0] / scale, f[1] / scale, f[2] / scale, f[3] / scale, float(f[-1])) for f in found]


def focus_point(im: Image.Image, focus) -> tuple[float, float]:
    """(fx, fy) 0-1 inside the image."""
    if isinstance(focus, (list, tuple)) and len(focus) == 2:
        return float(focus[0]), float(focus[1])
    if focus == "face":
        fs = faces(im)
        if fs:
            # weighted centre of the faces; biased up a little so eyes sit on the upper third
            tot = sum(f[2] * f[3] for f in fs)
            cx = sum((f[0] + f[2] / 2) * f[2] * f[3] for f in fs) / tot
            cy = sum((f[1] + f[3] * 0.4) * f[2] * f[3] for f in fs) / tot
            return cx / im.width, cy / im.height
        return 0.5, 0.4
    return FOCUS_WORDS.get(focus or "center", (0.5, 0.5))


def cached_focus(im: Image.Image, src: Path, focus, cache_dir: Path) -> tuple[float, float]:
    """focus_point, cached per source file: face detection is the slow part and every output size
    (preview, @2x, print dpi, PSD) would otherwise run it again."""
    if focus != "face":
        return focus_point(im, focus)
    key = hashlib.sha1(f"{src}|{src.stat().st_mtime_ns}".encode()).hexdigest()[:16]
    f = cache_dir / f"focus-{key}.json"
    if f.exists():
        return tuple(json.loads(f.read_text(encoding="utf-8")))
    pt = focus_point(im, focus)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(list(pt)), encoding="utf-8")
    return pt


def crop_box(src_w: int, src_h: int, box_w: float, box_h: float, fx: float, fy: float) -> tuple[int, int, int, int]:
    """Largest box_w:box_h window inside the source, as centred on (fx, fy) as the edges allow."""
    target = box_w / box_h
    if src_w / src_h > target:
        cw, ch = src_h * target, src_h
    else:
        cw, ch = src_w, src_w / target
    left = min(max(fx * src_w - cw / 2, 0), src_w - cw)
    top = min(max(fy * src_h - ch / 2, 0), src_h - ch)
    return round(left), round(top), round(left + cw), round(top + ch)


def _filters(im: Image.Image, flt: dict, ctx) -> Image.Image:
    from PIL import ImageEnhance

    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    if flt.get("grayscale"):
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    for key, enh in (("brightness", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast),
                     ("saturation", ImageEnhance.Color)):
        if key in flt and float(flt[key]) != 1:
            rgb = enh(rgb).enhance(float(flt[key]))
    if flt.get("duotone"):
        dark, light = (ctx.color(c) for c in flt["duotone"])
        rgb = ImageOps.colorize(ImageOps.grayscale(rgb), dark.hex, light.hex)
    if flt.get("tint"):
        c = ctx.color(flt["tint"])
        overlay = Image.new("RGB", rgb.size, (c.r, c.g, c.b))
        rgb = Image.blend(rgb, overlay, c.a if c.a < 1 else 0.35)
    if flt.get("blur"):
        rgb = rgb.filter(ImageFilter.GaussianBlur(float(flt["blur"])))
    if alpha is not None:
        rgb = rgb.convert("RGBA")
        rgb.putalpha(alpha)
    return rgb


def _round(im: Image.Image, radius_px, circle: bool) -> Image.Image:
    from PIL import ImageDraw

    im = im.convert("RGBA")
    ss = 4  # supersampled mask for smooth edges
    mask = Image.new("L", (im.width * ss, im.height * ss), 0)
    d = ImageDraw.Draw(mask)
    if circle:
        d.ellipse((0, 0, mask.width - 1, mask.height - 1), fill=255)
    else:
        r = radius_px if isinstance(radius_px, (list, tuple)) else [radius_px] * 4
        r = [max(0, min(v * ss, mask.width / 2, mask.height / 2)) for v in r]
        d.rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius=max(r), fill=255,
                            corners=tuple(v > 0 for v in r))
    mask = mask.resize(im.size, Image.LANCZOS)
    a = im.getchannel("A")
    from PIL import ImageChops

    im.putalpha(ImageChops.multiply(a, mask))
    return im


def prepare(layer: dict, src: Path, box_w_px: float, box_h_px: float, cache_dir: Path, ctx,
            radius_px=0) -> Prepared:
    """Bitmap for an image layer at box_w_px x box_h_px output pixels."""
    fit = layer.get("fit", "cover")
    params = {"src": str(src), "mtime": src.stat().st_mtime_ns, "w": round(box_w_px), "h": round(box_h_px),
              "fit": fit, "focus": layer.get("focus", "center"), "filters": layer.get("filters"),
              "radius": radius_px, "mask": layer.get("mask"), "box": layer.get("_src_box"), "v": 2}
    key = hashlib.sha1(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]
    meta_file = cache_dir / f"{key}.json"
    if meta_file.exists():
        m = json.loads(meta_file.read_text(encoding="utf-8"))
        p = cache_dir / m["file"]
        if p.exists():
            return Prepared(p, m["width"], m["height"], tuple(m["source_px"]), m["upscaled"], m["alpha"])
    im = open_image(src)
    if layer.get("_src_box"):  # only this part of the source is visible (svg.trim_to_clip)
        a0, b0, a1, b1 = layer["_src_box"]
        im = im.crop((round(a0 * im.width), round(b0 * im.height), max(round(a1 * im.width), round(a0 * im.width) + 1),
                      max(round(b1 * im.height), round(b0 * im.height) + 1)))
    W, H = max(1, round(box_w_px)), max(1, round(box_h_px))
    if fit == "cover":
        fx, fy = cached_focus(im, src, layer.get("focus", "center"), cache_dir)
        box = crop_box(im.width, im.height, W, H, fx, fy)
        crop = im.crop(box)
        source_px = (crop.width, crop.height)
        out = crop.resize((W, H), Image.LANCZOS)
    elif fit == "contain":
        r = min(W / im.width, H / im.height)
        nw, nh = max(1, round(im.width * r)), max(1, round(im.height * r))
        source_px = (im.width, im.height)
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out.paste(im.convert("RGBA").resize((nw, nh), Image.LANCZOS), ((W - nw) // 2, (H - nh) // 2))
    else:  # fill / stretch
        source_px = (im.width, im.height)
        out = im.resize((W, H), Image.LANCZOS)
    if layer.get("filters"):
        out = _filters(out, layer["filters"], ctx)
    if radius_px or layer.get("mask") == "circle":
        out = _round(out, radius_px, layer.get("mask") == "circle")
    alpha = out.mode == "RGBA" and out.getchannel("A").getextrema()[0] < 255
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = f"{key}.png" if alpha else f"{key}.jpg"
    if alpha:
        out.save(cache_dir / name, optimize=False)
    else:
        out.convert("RGB").save(cache_dir / name, quality=93, subsampling=0)
    upscaled = max(W / max(1, source_px[0]), H / max(1, source_px[1]))
    meta_file.write_text(json.dumps({"file": name, "width": W, "height": H, "source_px": source_px,
                                     "upscaled": round(upscaled, 3), "alpha": alpha}), encoding="utf-8")
    return Prepared(cache_dir / name, W, H, source_px, round(upscaled, 3), alpha)
