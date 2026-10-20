"""`da image`: work on image files — info, background removal, upscale, vectorize, crop, faces.

Outputs go to the project's work/ (never into input/):
  work/cutouts/   remove-bg PNGs        work/upscaled/  upscales
  work/vector/    traced SVGs           work/crops/     crops
  work/extended/  outpainted canvases (studio background continued to a new aspect)
"""
from __future__ import annotations

import re
from pathlib import Path

from .project import Project


def _src(project: Project | None, f: str) -> Path:
    p = Path(f).expanduser()
    if not p.is_absolute() and project is not None and project.abs(f).exists():
        p = project.abs(f)
    if not p.exists():
        raise SystemExit(f"image not found: {f}")
    return p.resolve()


def _out(project: Project, sub: str, src: Path, suffix: str, ext: str) -> Path:
    d = project.path("work", sub)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{src.stem}{suffix}{ext}"


def info(path: Path) -> dict:
    from PIL import Image

    from . import images as I

    with Image.open(path) as raw:
        dpi = raw.info.get("dpi")
        mode, fmt = raw.mode, raw.format
        icc = bool(raw.info.get("icc_profile"))
    im = I.open_image(path)
    alpha = im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 255
    try:
        n_faces = len(I.faces(im))
    except Exception:
        n_faces = None
    return {"file": str(path), "format": fmt, "px": [im.width, im.height], "mode": mode, "alpha": alpha,
            "dpi": [round(float(v)) for v in dpi] if dpi else None, "icc_profile": icc, "faces": n_faces,
            "aspect": round(im.width / im.height, 4),
            "print_size_at_300dpi_mm": [round(im.width / 300 * 25.4, 1), round(im.height / 300 * 25.4, 1)],
            "print_size_at_150dpi_mm": [round(im.width / 150 * 25.4, 1), round(im.height / 150 * 25.4, 1)]}


def keep_largest(alpha, haze: int = 90):
    """Alpha of the biggest solid blob only: drops other subjects (a head behind the product) and the
    half-transparent ghosts rembg leaves where people stood. `haze` = alpha below which a pixel isn't solid."""
    import cv2
    import numpy as np

    a = np.asarray(alpha, np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats((a >= haze).astype(np.uint8), connectivity=8)
    if n <= 1:
        return a, 0
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = cv2.dilate((labels == big).astype(np.uint8), np.ones((5, 5), np.uint8))  # keep the soft edge
    return (a * keep).astype(np.uint8), n - 2


def remove_bg(project: Project, src: Path, model: str = "u2net", keep: str = "all", haze: int = 90) -> dict:
    try:
        from rembg import new_session, remove
    except ImportError:
        raise SystemExit("background removal needs the optional extra: `uv sync --extra bg` "
                         "(installs rembg + onnxruntime; the model, ~170 MB, downloads on first use)")
    from PIL import Image

    from . import images as I

    im = I.open_image(src)
    out = remove(im, session=new_session(model))
    dropped = 0
    if keep == "largest":
        a, dropped = keep_largest(out.getchannel("A"), haze)
        out.putalpha(Image.fromarray(a, "L"))
    dst = _out(project, "cutouts", src, "_cutout", ".png")
    out.save(dst)
    bbox = out.getchannel("A").getbbox()
    return {"file": project.rel(dst), "px": list(out.size), "subject_bbox": list(bbox) if bbox else None,
            "model": model, **({"dropped_blobs": dropped} if keep == "largest" else {}), "next": "LOOK at it over a dark and a light background before using it"}


def upscale(project: Project, src: Path, factor: float = 2.0) -> dict:
    from PIL import Image, ImageFilter

    from . import images as I

    im = I.open_image(src)
    w, h = round(im.width * factor), round(im.height * factor)
    big = im.resize((w, h), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    ext = ".png" if big.mode == "RGBA" else ".jpg"
    dst = _out(project, "upscaled", src, f"_x{factor:g}", ext)
    big.save(dst, **({} if ext == ".png" else {"quality": 94}))
    return {"file": project.rel(dst), "px": [w, h], "method": "Lanczos + unsharp mask (not AI: adds no detail; "
            "for real detail use a Higgsfield upscale model via `da hf models --search upscale`)"}


def vectorize(project: Project, src: Path, colors: int = 6, mode: str = "logo", speckle: int | None = None) -> dict:
    """Trace a raster into SVG (vtracer). logo: palette reduced to `colors`, cut-out shapes (holes
    are real holes), background colour dropped. illustration: stacked layers, more detail."""
    import vtracer
    from PIL import Image

    from . import images as I

    im = I.open_image(src)
    work = _out(project, "vector", src, "_prep", ".png")
    has_alpha = im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 255
    rgb = im.convert("RGB")
    if max(rgb.size) < 1000:  # trace at a decent size: smoother curves
        k = 1000 / max(rgb.size)
        rgb = rgb.resize((round(rgb.width * k), round(rgb.height * k)), Image.LANCZOS)
        if has_alpha:
            im = im.resize(rgb.size, Image.LANCZOS)
    q = _quantize(rgb, max(2, colors))
    if has_alpha:
        q = q.convert("RGBA")
        q.putalpha(im.getchannel("A").point(lambda a: 255 if a > 127 else 0))
    q.save(work)
    dst = _out(project, "vector", src, "", ".svg")
    logo = mode == "logo"
    vtracer.convert_image_to_svg_py(
        str(work), str(dst), colormode="color", hierarchical="cutout" if logo else "stacked", mode="spline",
        filter_speckle=speckle if speckle is not None else (8 if logo else 4), color_precision=8,
        layer_difference=16, corner_threshold=60, length_threshold=4.0, max_iterations=10, splice_threshold=45,
        path_precision=3)
    svg = dst.read_text(encoding="utf-8")
    dropped = 0
    if logo and not has_alpha:
        corners = [q.getpixel(p)[:3] for p in ((0, 0), (q.width - 1, 0), (0, q.height - 1), (q.width - 1, q.height - 1))]
        bg = max(set(corners), key=corners.count)

        def keep(m):  # vtracer may shift a channel by 1: compare with a tolerance
            h = re.search(r'fill="#([0-9A-Fa-f]{6})"', m.group(0))
            if h and max(abs(int(h.group(1)[i:i + 2], 16) - bg[i // 2]) for i in (0, 2, 4)) <= 6:
                return ""
            return m.group(0)

        before = svg.count("<path")
        svg = re.sub(r'<path[^>]*/>\s*', keep, svg)
        dropped = before - svg.count("<path")
    if "viewBox" not in svg:
        w = re.search(r'<svg[^>]*\swidth="([\d.]+)"', svg)
        h = re.search(r'<svg[^>]*\sheight="([\d.]+)"', svg)
        if w and h:
            svg = svg.replace("<svg ", f'<svg viewBox="0 0 {w.group(1)} {h.group(1)}" ', 1)
    # vtracer nudges channels by a unit or two: snap every fill back to the quantized palette
    pal = {q.getpixel((x, y))[:3] for x in range(0, q.width, max(1, q.width // 64))
           for y in range(0, q.height, max(1, q.height // 64))}

    def snap(m):
        h = m.group(1)
        c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        best = min(pal, key=lambda p: sum((a - b) ** 2 for a, b in zip(p, c)))
        return 'fill="#%02X%02X%02X"' % best if sum((a - b) ** 2 for a, b in zip(best, c)) <= 75 else m.group(0)

    svg = re.sub(r'fill="#([0-9A-Fa-f]{6})"', snap, svg)
    fills = sorted(set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)))
    dst.write_text(svg, encoding="utf-8")
    work.unlink(missing_ok=True)
    return {"file": project.rel(dst), "paths": svg.count("<path"), "colors": fills, "background_paths_dropped": dropped,
            "mode": mode, "next": "LOOK at it rendered (e.g. as an svg layer) next to the original; "
            "fewer --colors = cleaner logo, more = closer illustration"}


def _quantize(rgb, n: int):
    """Map every pixel to the nearest of n k-means colours (OKLab), no dithering: flat logo colours."""
    import io

    import numpy as np
    from PIL import Image

    from . import colors as C
    from .colortools import palette

    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    buf.seek(0)
    centers = np.array([C.parse(e["hex"]).rgba[:3] for e in palette(buf, n)], dtype=float)
    arr = np.asarray(rgb, dtype=float).reshape(-1, 3)
    # snap each centre to the most common exact colour of its cluster (anti-aliased edges pull
    # k-means means off the real brand colour)
    sample = arr[:: max(1, len(arr) // 200000)]
    lbl = np.argmin(((sample[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
    for k in range(len(centers)):
        members = sample[lbl == k]
        if len(members):
            vals, counts = np.unique(members, axis=0, return_counts=True)
            centers[k] = vals[np.argmax(counts)]
    out = np.empty_like(arr)
    for i in range(0, len(arr), 262144):  # chunked: big images
        chunk = arr[i:i + 262144]
        idx = np.argmin(((chunk[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        out[i:i + 262144] = centers[idx]
    return Image.fromarray(out.reshape(rgb.height, rgb.width, 3).astype("uint8"), "RGB")


def crop(project: Project, src: Path, aspect: str, focus="center", width: int | None = None) -> dict:
    from PIL import Image

    from . import images as I

    m = re.fullmatch(r"(\d+(?:\.\d+)?)[:x/](\d+(?:\.\d+)?)", aspect)
    if not m:
        raise SystemExit("--aspect like 4:5, 9:16 or 1.91:1")
    aw, ah = float(m.group(1)), float(m.group(2))
    im = I.open_image(src)
    fx, fy = I.focus_point(im, focus)
    box = I.crop_box(im.width, im.height, aw, ah, fx, fy)
    out = im.crop(box)
    if width and width != out.width:
        out = out.resize((width, round(width * ah / aw)), Image.LANCZOS)
    ext = ".png" if out.mode == "RGBA" else ".jpg"
    dst = _out(project, "crops", src, f"_{aspect.replace(':', 'x')}", ext)
    out.save(dst, **({} if ext == ".png" else {"quality": 94}))
    return {"file": project.rel(dst), "px": list(out.size), "box": list(box), "focus": [round(fx, 3), round(fy, 3)]}


def _push_pull(rgb, known):
    """Fill the unknown pixels (known = 0) by push-pull: mask-weighted averages down to 1 px, then
    bilinear back up, so the fill is a smooth continuation of the colours at the known edges."""
    import cv2
    import numpy as np

    h, w = known.shape
    if h <= 2 and w <= 2:
        m = known.sum()
        col = (rgb * known[..., None]).sum((0, 1)) / m if m > 0 else rgb.mean((0, 1))
        return np.where(known[..., None] > 0, rgb, col).astype(np.float32)
    size = (max(1, (w + 1) // 2), max(1, (h + 1) // 2))
    m_small = cv2.resize(known, size, interpolation=cv2.INTER_AREA)
    c_small = cv2.resize(rgb * known[..., None], size, interpolation=cv2.INTER_AREA)
    c_small = np.where(m_small[..., None] > 1e-6, c_small / np.maximum(m_small[..., None], 1e-6), 0)
    coarse = _push_pull(c_small.astype(np.float32), (m_small > 1e-6).astype(np.float32))
    up = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_LINEAR)
    k = known[..., None]
    return (rgb * k + up * (1 - k)).astype(np.float32)


def extend(project: Project, src: Path, aspect: str = "4:5", scale: float = 1.0, place=(0.5, 0.5),
           width: int | None = None, feather: int = 48, trim: int = 2, grain: bool = True) -> dict:
    """Outpaint a studio shot onto a bigger canvas of `aspect`: the background continues smoothly from
    the photo's own edge colours (push-pull fill), the seam is feathered and the fill gets grain
    matched to the photo, so a wide product render can sit in a 4:5 post with room for type.
    `scale` resizes the photo first; `place` = where the photo's centre goes (fractions of the canvas);
    `width` = canvas width (default: the scaled photo's width); `trim` drops dark JPEG edge rows."""
    import cv2
    import numpy as np
    from PIL import Image

    from . import images as I

    m = re.fullmatch(r"(\d+(?:\.\d+)?)[:x/](\d+(?:\.\d+)?)", aspect)
    if not m:
        raise SystemExit("--aspect like 4:5, 9:16 or 1.91:1")
    ar = float(m.group(1)) / float(m.group(2))
    im = I.open_image(src).convert("RGB")
    if trim:
        im = im.crop((trim, trim, im.width - trim, im.height - trim))
    if scale != 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    W = int(width or im.width)
    H = round(W / ar)
    if W < im.width * 0.5 or H < 8:
        raise SystemExit("canvas too small for the photo: raise --width or lower --x")
    x0 = round(place[0] * W - im.width / 2)
    y0 = round(place[1] * H - im.height / 2)
    # paste box clipped to the canvas
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(W, x0 + im.width), min(H, y0 + im.height)
    if cx1 <= cx0 or cy1 <= cy0:
        raise SystemExit("--place puts the photo outside the canvas")
    src_a = np.asarray(im, dtype=np.float32)
    canvas = np.zeros((H, W, 3), np.float32)
    known = np.zeros((H, W), np.float32)
    canvas[cy0:cy1, cx0:cx1] = src_a[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    known[cy0:cy1, cx0:cx1] = 1
    plate = _push_pull(canvas, known)
    # the fill copies the photo's edge pixels outward as streaks: blur it (only where it is new) so it
    # reads as a smooth studio sweep, then fade it back into the photo across `feather` px
    soft = cv2.GaussianBlur(plate, (0, 0), max(1, feather))
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.minimum.reduce([
        np.where(cx0 > 0, xx - cx0, 1e9), np.where(cx1 < W, cx1 - 1 - xx, 1e9),
        np.where(cy0 > 0, yy - cy0, 1e9), np.where(cy1 < H, cy1 - 1 - yy, 1e9)]).astype(np.float32)
    inside = known > 0
    alpha = np.where(inside, np.clip(dist / max(1, feather), 0, 1), 0)[..., None]
    out = canvas * alpha + soft * (1 - alpha)
    noise_std = 0.0
    if grain:
        g = np.asarray(im.convert("L"), np.float32)
        hp = g - cv2.GaussianBlur(g, (0, 0), 2)
        e = max(4, min(g.shape) // 20)
        strips = [hp[:e, :], hp[-e:, :], hp[:, :e].T, hp[:, -e:].T]
        noise_std = float(np.median([s.std() for s in strips]))
        rng = np.random.default_rng(7)
        out += (rng.normal(0, noise_std, (H, W))[..., None] * (1 - alpha)).astype(np.float32)
    res = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGB")
    dst = _out(project, "extended", src, f"_{aspect.replace(':', 'x')}", ".jpg")
    res.save(dst, quality=95)
    return {"file": project.rel(dst), "px": [W, H], "photo_box": [x0, y0, im.width, im.height],
            "scale": scale, "grain_std": round(noise_std, 2),
            "next": "LOOK at the seams at 100% (zoom the corners of photo_box); use the file as an image layer"}


def faces_json(src: Path) -> dict:
    from . import images as I

    im = I.open_image(src)
    fs = I.faces(im)
    return {"file": str(src), "px": [im.width, im.height], "faces": [
        {"x": round(f[0]), "y": round(f[1]), "w": round(f[2]), "h": round(f[3]), "score": round(f[4], 3),
         "centre": [round((f[0] + f[2] / 2) / im.width, 3), round((f[1] + f[3] / 2) / im.height, 3)]} for f in fs]}


def cmd_image(a):
    pr = Project(a.project) if getattr(a, "project", None) else None
    if a.action == "info":
        return [info(_src(pr, f)) for f in a.files]
    if a.action == "faces":
        return [faces_json(_src(pr, f)) for f in a.files]
    if pr is None:
        raise SystemExit(f"`da image {a.action}` needs --project <p> (outputs go to its work/)")
    if a.action == "remove-bg":
        return [remove_bg(pr, _src(pr, f), keep=a.keep, haze=a.haze) for f in a.files]
    if a.action == "upscale":
        return [upscale(pr, _src(pr, f), a.x or 2.0) for f in a.files]
    if a.action == "vectorize":
        return [vectorize(pr, _src(pr, f), a.colors, a.mode, a.speckle) for f in a.files]
    if a.action == "crop":
        focus = a.focus
        if focus and re.fullmatch(r"[\d.]+,[\d.]+", focus):
            focus = [float(v) for v in focus.split(",")]
        return [crop(pr, _src(pr, f), a.aspect, focus, a.width) for f in a.files]
    if a.action == "extend":
        place = tuple(float(v) for v in (a.place or "0.5,0.5").split(","))
        return [extend(pr, _src(pr, f), a.aspect, a.x or 1.0, place, a.width, a.feather)
                for f in a.files]
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("image", help="image files: info, faces, remove-bg, upscale, vectorize, crop, extend")
    p.add_argument("action", choices=["info", "faces", "remove-bg", "upscale", "vectorize", "crop", "extend"])
    p.add_argument("files", nargs="+", help="image paths (project-relative with --project)")
    p.add_argument("--project", "-p", help="project (outputs go to its work/)")
    p.add_argument("--x", type=float, help="upscale factor (default 2); extend: scale of the photo (default 1)")
    p.add_argument("--colors", type=int, default=6, help="vectorize: palette size")
    p.add_argument("--mode", choices=["logo", "illustration"], default="logo", help="vectorize mode")
    p.add_argument("--speckle", type=int, help="vectorize: drop specks smaller than this (px)")
    p.add_argument("--aspect", default="4:5", help="crop: e.g. 4:5, 9:16, 1.91:1")
    p.add_argument("--focus", default="center", help="crop: center|face|top|... or fx,fy")
    p.add_argument("--width", type=int, help="crop: resize to this width; extend: canvas width")
    p.add_argument("--place", help="extend: where the photo's centre goes, fx,fy (default 0.5,0.5)")
    p.add_argument("--keep", choices=["all", "largest"], default="all",
                   help="remove-bg: largest = only the biggest subject (drops people/ghosts behind a product)")
    p.add_argument("--haze", type=int, default=90,
                   help="remove-bg --keep largest: alpha (0-255) under which a pixel counts as ghost, not subject")
    p.add_argument("--feather", type=int, default=48, help="extend: seam fade (px)")
    p.set_defaults(func=cmd_image)
