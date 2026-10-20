"""`da mockup`: show a design in context.

Scene mockups: perspective-warp a rendered artboard onto a photo.
  --corners x1,y1,x2,y2,x3,y3,x4,y4   the target quad (top-left, top-right, bottom-right, bottom-left), scene px
  --auto                              find a flat saturated green quad (generate or shoot the scene with a
                                      green screen where the design goes) and replace it
The scene's own light is kept: its luminance inside the quad (relative to its median) multiplies
the design, so folds, gradients and shadows on the green surface show through.

Built-in mockups (no photo needed): --builtin phone | poster | card | post-feed.
Outputs: output/mockups/<artboard>-<kind>.jpg
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .project import ROOT, Project

FONT = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"


# --- scene mockups -----------------------------------------------------------------------------

def order_corners(pts) -> list[tuple[float, float]]:
    """Any 4 points -> TL, TR, BR, BL."""
    import numpy as np

    p = np.asarray(pts, dtype=float).reshape(4, 2)
    s, d = p.sum(1), np.diff(p, axis=1).ravel()
    return [tuple(p[np.argmin(s)]), tuple(p[np.argmin(d)]), tuple(p[np.argmax(s)]), tuple(p[np.argmax(d)])]


def green_mask(scene: Image.Image):
    import numpy as np

    a = np.asarray(scene.convert("RGB"), dtype=int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((g > 90) & (g - np.maximum(r, b) > 50) & (g > 1.4 * np.maximum(r, b))).astype("uint8")


def find_green_quad(scene: Image.Image) -> list[tuple[float, float]]:
    """Corners of the largest green-screen region, as a quadrilateral."""
    import cv2
    import numpy as np

    mask = green_mask(scene) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise SystemExit("no green area found in the scene (--auto needs a saturated green screen where the design goes; "
                         "or pass --corners)")
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.002 * scene.width * scene.height:
        raise SystemExit("the green area is too small to place a design on")
    hull = cv2.convexHull(c)
    peri = cv2.arcLength(hull, True)
    for eps in (0.01, 0.02, 0.03, 0.05, 0.08):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            return order_corners(approx.reshape(4, 2))
    box = cv2.boxPoints(cv2.minAreaRect(c))
    return order_corners(box)


def warp_into(art: Image.Image, scene: Image.Image, corners, shade: bool = True, green: bool = False) -> Image.Image:
    import cv2
    import numpy as np

    W, H = scene.size
    art = art.convert("RGBA")
    src = np.float32([[0, 0], [art.width, 0], [art.width, art.height], [0, art.height]])
    dst = np.float32(order_corners(corners))
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(np.asarray(art), M, (W, H), flags=cv2.INTER_LANCZOS4, borderValue=(0, 0, 0, 0))
    alpha = warped[..., 3:4].astype(float) / 255
    out = np.asarray(scene.convert("RGB"), dtype=float)
    rgb = warped[..., :3].astype(float)
    if shade:
        lum = out[..., 1] if green else out @ np.array([0.299, 0.587, 0.114])
        inside = alpha[..., 0] > 0.5
        if inside.any():
            med = np.median(lum[inside]) or 1.0
            k = np.clip(lum / med, 0.55, 1.2)[..., None]
            rgb = np.clip(rgb * np.minimum(k, 1.0) + (255 - rgb) * np.maximum(k - 1.0, 0), 0, 255)
    if green:  # cover the green fringe at the quad edge
        g = green_mask(scene).astype(float)[..., None]
        grow = cv2.dilate(alpha[..., 0], np.ones((3, 3), np.uint8))[..., None]
        alpha = np.maximum(alpha, g * grow)
    comp = rgb * alpha + out * (1 - alpha)
    return Image.fromarray(comp.astype("uint8"), "RGB")


def parse_corners(s: str) -> list[tuple[float, float]]:
    v = [float(x) for x in re.split(r"[,\s]+", s.strip()) if x]
    if len(v) != 8:
        raise SystemExit("--corners needs 8 numbers: x1,y1,x2,y2,x3,y3,x4,y4 (TL, TR, BR, BL in scene pixels)")
    return [(v[i], v[i + 1]) for i in range(0, 8, 2)]


# --- built-in mockups --------------------------------------------------------------------------

def _shadow(size, box, radius, blur, offset=(0, 18), opacity=90) -> Image.Image:
    sh = Image.new("L", size, 0)
    d = ImageDraw.Draw(sh)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]), radius=radius, fill=opacity)
    return sh.filter(ImageFilter.GaussianBlur(blur))


def _backdrop(size, top=(242, 242, 240), bottom=(220, 220, 216)) -> Image.Image:
    bg = Image.new("RGB", size, top)
    d = ImageDraw.Draw(bg)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        d.line([(0, y), (size[0], y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return bg


def _rounded(im: Image.Image, r: int) -> Image.Image:
    im = im.convert("RGBA")
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=r, fill=255)
    im.putalpha(m)
    return im


def _fit_cover(art: Image.Image, w: int, h: int) -> Image.Image:
    from .images import crop_box

    box = crop_box(art.width, art.height, w, h, 0.5, 0.5)
    return art.crop(box).resize((w, h), Image.LANCZOS)


def builtin_phone(art: Image.Image) -> Image.Image:
    sw = 900
    sh_ = round(sw * 19.5 / 9)
    ratio = (art.width / art.height) / (9 / 19.5)
    if 0.85 <= ratio <= 1.18:  # story-like: fill the screen
        screen = _fit_cover(art.convert("RGB"), sw, sh_)
    else:  # a feed post etc.: whole design centred on a blurred copy of itself, as an app shows it
        screen = _fit_cover(art.convert("RGB"), sw, sh_).filter(ImageFilter.GaussianBlur(40))
        screen = Image.blend(screen, Image.new("RGB", screen.size, (0, 0, 0)), 0.45)
        fit = art.convert("RGB")
        fit.thumbnail((sw, sh_), Image.LANCZOS)
        screen.paste(fit, ((sw - fit.width) // 2, (sh_ - fit.height) // 2))
    bezel, r_out = 34, 150
    fw, fh = sw + 2 * bezel, sh_ + 2 * bezel
    W, H = fw + 700, fh + 500
    bg = _backdrop((W, H))
    x0, y0 = (W - fw) // 2, (H - fh) // 2
    bg.paste((0, 0, 0), (0, 0), _shadow((W, H), (x0, y0, x0 + fw, y0 + fh), r_out, 40, (0, 40), 110))
    frame = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((0, 0, fw - 1, fh - 1), radius=r_out, fill=(28, 28, 30, 255), outline=(70, 70, 74, 255), width=6)
    frame.alpha_composite(_rounded(screen, r_out - bezel), (bezel, bezel))
    iw, ih = 300, 88  # dynamic island
    d.rounded_rectangle(((fw - iw) // 2, bezel + 36, (fw + iw) // 2, bezel + 36 + ih), radius=ih // 2, fill=(0, 0, 0, 255))
    bg.paste(frame, (x0, y0), frame)
    d2 = ImageDraw.Draw(bg)  # side buttons
    d2.rounded_rectangle((x0 - 10, y0 + 420, x0 + 2, y0 + 560), radius=5, fill=(45, 45, 48))
    d2.rounded_rectangle((x0 - 10, y0 + 600, x0 + 2, y0 + 740), radius=5, fill=(45, 45, 48))
    d2.rounded_rectangle((x0 + fw - 2, y0 + 500, x0 + fw + 10, y0 + 720), radius=5, fill=(45, 45, 48))
    return bg


def builtin_poster(art: Image.Image) -> Image.Image:
    a = art.convert("RGB")
    target = 1500
    k = target / max(a.size)
    a = a.resize((round(a.width * k), round(a.height * k)), Image.LANCZOS)
    W, H = round(a.width * 1.7), round(a.height * 1.45)
    bg = _backdrop((W, H), (232, 228, 220), (214, 208, 198))
    noise = Image.effect_noise((W, H), 10).convert("RGB")
    bg = Image.blend(bg, noise, 0.04)
    x0, y0 = (W - a.width) // 2, round((H - a.height) * 0.42)
    bg.paste((0, 0, 0), (0, 0), _shadow((W, H), (x0, y0, x0 + a.width, y0 + a.height), 2, 28, (0, 26), 120))
    bg.paste(a, (x0, y0))
    # soft light falloff from the top
    light = Image.new("L", (W, H), 0)
    ImageDraw.Draw(light).ellipse((-W * 0.2, -H * 0.6, W * 1.2, H * 0.7), fill=40)
    light = light.filter(ImageFilter.GaussianBlur(W // 8))
    bg.paste((255, 255, 250), (0, 0), light)
    return bg


def builtin_card(art: Image.Image) -> Image.Image:
    a = art.convert("RGB")
    cw = 1100
    ch = round(cw * a.height / a.width)
    a = a.resize((cw, ch), Image.LANCZOS)
    W, H = 2200, max(1500, ch * 2 + 300)
    bg = _backdrop((W, H), (58, 60, 64), (36, 38, 42))
    bg = Image.blend(bg, Image.effect_noise((W, H), 14).convert("RGB"), 0.05)
    avg = a.resize((1, 1)).getpixel((0, 0))
    back = Image.new("RGB", (cw, ch), avg)  # the second card, plain back in the art's average colour
    for img, ang, cx, cy in ((back, 14, W * 0.58, H * 0.44), (a, -6, W * 0.44, H * 0.56)):
        card = _rounded(img, 10)
        rot = card.rotate(ang, resample=Image.BICUBIC, expand=True)
        x, y = round(cx - rot.width / 2), round(cy - rot.height / 2)
        sh = Image.new("L", (W, H), 0)
        sh.paste(rot.getchannel("A").point(lambda v: v * 0.55), (x + 14, y + 28))
        bg.paste((0, 0, 0), (0, 0), sh.filter(ImageFilter.GaussianBlur(24)))
        bg.paste(rot, (x, y), rot)
    return bg


def builtin_feed(art: Image.Image, handle: str = "seu_perfil") -> Image.Image:
    from PIL import ImageFont

    w = 1080
    a = art.convert("RGB")
    h = round(w * a.height / a.width)
    a = a.resize((w, h), Image.LANCZOS)
    head, foot = 130, 300
    card = Image.new("RGB", (w, head + h + foot), (255, 255, 255))
    d = ImageDraw.Draw(card)
    d.ellipse((32, 29, 104, 101), fill=(225, 225, 225), outline=(214, 41, 118), width=5)
    font = ImageFont.truetype(str(FONT), 30)
    d.text((126, 46), handle, fill=(20, 20, 20), font=font)
    for i in range(3):
        d.ellipse((w - 70 + i * 16, 62, w - 62 + i * 16, 70), fill=(30, 30, 30))
    card.paste(a, (0, head))
    y = head + h + 30
    ink = (20, 20, 20)
    import math

    heart = [(62 + 1.25 * 16 * math.sin(t) ** 3,
              y + 18 - 1.25 * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)))
             for t in [i * 2 * math.pi / 60 for i in range(61)]]
    d.line(heart, fill=ink, width=4, joint="curve")
    d.ellipse((120, y, 160, y + 38), outline=ink, width=4)  # comment
    d.polygon([(200, y + 2), (246, y + 2), (214, y + 38)], outline=ink, width=4)  # send
    d.polygon([(w - 76, y), (w - 44, y), (w - 44, y + 40), (w - 60, y + 28), (w - 76, y + 40)], outline=ink, width=4)
    for i, bw in enumerate((420, 820, 600)):
        d.rounded_rectangle((44, y + 80 + i * 50, 44 + bw, y + 104 + i * 50), radius=12, fill=(232, 232, 232))
    W, H = card.width + 360, card.height + 360
    bg = _backdrop((W, H), (245, 244, 248), (226, 224, 232))
    x0, y0 = 180, 180
    bg.paste((0, 0, 0), (0, 0), _shadow((W, H), (x0, y0, x0 + card.width, y0 + card.height), 24, 30, (0, 20), 70))
    bg.paste(_rounded(card, 24), (x0, y0), _rounded(card, 24))
    return bg


BUILTINS = {"phone": builtin_phone, "poster": builtin_poster, "card": builtin_card, "post-feed": builtin_feed}


# --- entry ---------------------------------------------------------------------------------

def _art(project: Project, artboard: str) -> Image.Image:
    from . import design as D
    from . import render as R

    d = D.load(project)
    ctx = D.context(project, d)
    ab = D.artboard(d, artboard)
    ppu = D.px_per_unit(ab)
    scale = min(4.0, 2200 / max(ab["width"] * ppu, ab["height"] * ppu))
    im, _ = R.render_artboard(ctx, ab, scale=scale)
    return im


def mockup(project: Project, artboard: str, scene: str | None = None, corners: str | None = None,
           auto: bool = False, builtin: str | None = None, shade: bool = True, handle: str | None = None) -> dict:
    art = _art(project, artboard)
    out_dir = project.path("output", "mockups")
    out_dir.mkdir(parents=True, exist_ok=True)
    if builtin:
        if builtin not in BUILTINS:
            raise SystemExit(f"--builtin: {', '.join(BUILTINS)}")
        im = builtin_feed(art, handle) if builtin == "post-feed" and handle else BUILTINS[builtin](art)
        dst = out_dir / f"{artboard}-{builtin}.jpg"
        im.convert("RGB").save(dst, quality=92)
        return {"file": project.rel(dst), "px": list(im.size), "kind": builtin}
    if not scene:
        raise SystemExit("pass --scene <photo> (with --corners or --auto) or --builtin phone|poster|card|post-feed")
    sp = project.abs(scene) if project.abs(scene).exists() else Path(scene).expanduser()
    if not sp.exists():
        raise SystemExit(f"scene not found: {scene}")
    from .images import open_image

    sc = open_image(sp).convert("RGB")
    if auto:
        quad = find_green_quad(sc)
    elif corners:
        quad = parse_corners(corners)
    else:
        raise SystemExit("scene mockups need --corners x1,y1,...,x4,y4 or --auto (green screen)")
    im = warp_into(art, sc, quad, shade, green=auto)
    dst = out_dir / f"{artboard}-{Path(sp).stem}.jpg"
    im.save(dst, quality=92)
    return {"file": project.rel(dst), "px": list(im.size), "corners": [[round(x), round(y)] for x, y in quad],
            "next": "LOOK at it: check the corners sit on the surface and the light reads right"}


def cmd_mockup(a):
    return mockup(Project(a.project), a.art, a.scene, a.corners, a.auto, a.builtin, not a.flat, a.handle)


def register(sub) -> None:
    p = sub.add_parser("mockup", help="place an artboard in a scene photo (corners / green screen) or a built-in mockup")
    p.add_argument("project")
    p.add_argument("--art", required=True, help="artboard id")
    p.add_argument("--scene", help="scene photo (project-relative or absolute)")
    p.add_argument("--corners", help="x1,y1,x2,y2,x3,y3,x4,y4: TL, TR, BR, BL in scene px")
    p.add_argument("--auto", action="store_true", help="find a green-screen quad in the scene")
    p.add_argument("--builtin", choices=list(BUILTINS))
    p.add_argument("--flat", action="store_true", help="don't apply the scene's light to the design")
    p.add_argument("--handle", help="post-feed: profile name shown above the post")
    p.set_defaults(func=cmd_mockup)
