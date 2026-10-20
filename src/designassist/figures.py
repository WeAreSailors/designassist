"""Human silhouettes (`figure:<pose>` sources): small solid people for editorial / isometric scenes, like the
tiny walkers with long shadows in minimalist posters. Each pose is a skeleton (joint angles) dressed in tapered
limbs, drawn big, unioned and softened as a raster, then traced into ONE clean outline (no seams between body
parts). Facing right; `figure:<pose>-left` is mirrored. The ground is the bottom edge of the viewBox, so a
layer's bottom = where the feet stand (pair it with the `cast` effect for the shadow).

    da figure list                      poses
    da figure show <p> [--out f.png]    contact sheet of every pose
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .project import ROOT

H = 1000  # figure units: top of the head 0, soles at H
CANVAS = 2  # raster px per unit while tracing
CACHE = ROOT / ".cache" / "figures"
VERSION = 5  # bump when the drawing changes (invalidates cached svgs)

# body proportions in figure units (a clothed adult, ~6.8 heads: chunky enough to read at 60 px tall).
# limb widths are half-widths at (root, middle joint, end)
BODY = {"head": (50, 62), "neck": 40, "shoulder_drop": 150, "torso": 300, "upper_arm": 182, "forearm": 160,
        "thigh": 250, "shin": 238, "ankle_h": 30, "foot": 112, "heel": 30,
        "arm_w": (31, 25, 19), "leg_w": (56, 40, 23)}

# Poses. Angles in degrees from straight down; positive = towards +x (the way the figure faces).
#   lean: torso tilt; head: extra head tilt (positive = looking down/forward)
#   legs: [(dx, lift)] ankle offset from the hip on the ground; lift > 0 raises the heel (pushing off on the toes)
#   arms: [(upper, forearm, hand)] absolute angles; hand "" (open), "fist", "none" (hidden behind the body / pocket)
POSES = {
    "stand": {"lean": 0, "head": 0, "legs": [(10, 0), (-8, 0)],
              "arms": [(5, 8, ""), (-3, 2, "")], "desc": "standing straight, arms down"},
    "stand-back": {"lean": -2, "head": -6, "legs": [(8, 0), (-6, 0)],
                   "arms": [(-16, 62, "none"), (-12, 70, "none")],
                   "desc": "standing, hands behind the back (waiting, looking up)"},
    "walk": {"lean": 3, "head": 4, "legs": [(150, 0), (-140, 44)], "straight": 0.985,
             "arms": [(-20, -8, ""), (20, 38, "")], "desc": "mid-stride, arms swinging"},
    "pocket": {"lean": 0, "head": 8, "legs": [(16, 0), (-22, 0)],
               "arms": [(10, 26, "none"), (6, 22, "none")],
               "desc": "standing relaxed, hands in the pockets, head down a little"},
    "point": {"lean": 0, "head": -4, "legs": [(30, 0), (-24, 0)],
              "arms": [(92, 95, ""), (-2, 4, "")], "desc": "standing, one arm pointing forward"},
    "phone": {"lean": 2, "head": 22, "legs": [(14, 0), (-12, 0)],
              "arms": [(8, 150, "fist"), (-4, 2, "")], "desc": "standing, looking down at a phone"},
}


def _pt(o, ang, length):
    a = math.radians(ang)
    return (o[0] + math.sin(a) * length, o[1] + math.cos(a) * length)


def _ik(hip, ankle, l1, l2):
    """Knee for a two-bone leg from hip to ankle, bending forward (+x)."""
    dx, dy = ankle[0] - hip[0], ankle[1] - hip[1]
    d = min(math.hypot(dx, dy), l1 + l2 - 1e-3)
    base = math.atan2(dx, dy)  # angle from straight down
    a = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))))
    ang = base + a  # knee towards +x
    return (hip[0] + math.sin(ang) * l1, hip[1] + math.cos(ang) * l1)


def _skeleton(pose: dict) -> dict:
    b = BODY
    L = b["thigh"] + b["shin"]
    ankle_y = H - b["ankle_h"]
    # the hip sits as high as the most stretched leg allows (`straight`: 1 = locked knee)
    st = pose.get("straight", 0.997)
    hip_y = min(ankle_y - lift - math.sqrt(max((st * L) ** 2 - dx * dx, 1.0)) for dx, lift in pose["legs"])
    hip = (0.0, hip_y)
    legs = []
    for dx, lift in pose["legs"]:
        if lift:
            # pushing off: toes on the ground, heel raised by `lift`
            ankle = (hip[0] + dx, ankle_y - lift)
            reach = b["foot"] - 10
            toe_dx = math.sqrt(max(reach * reach - (H - ankle[1] - 12) ** 2, 1.0))
            toe = (ankle[0] + toe_dx, H - 12)
        else:
            ankle = (hip[0] + dx, ankle_y)
            toe = (ankle[0] + b["foot"] - 10, H - 12)
        heel = _pt(ankle, math.degrees(math.atan2(ankle[0] - toe[0], ankle[1] - toe[1])), b["heel"])
        legs.append((hip, _ik(hip, ankle, b["thigh"], b["shin"]), ankle, toe, heel))
    lean = pose.get("lean", 0)
    shoulder = _pt(hip, 180 - lean, b["torso"])
    neck = _pt(shoulder, 180 - lean - pose.get("head", 0) * 0.4, b["neck"])
    head = _pt(neck, 180 - lean - pose.get("head", 0), b["head"][1] - 8)
    arms = []
    for up, fore, hand in pose["arms"]:
        s0 = (shoulder[0] - 4, shoulder[1] + 26)
        elbow = _pt(s0, up, b["upper_arm"])
        wrist = _pt(elbow, fore, b["forearm"] * (0.75 if hand == "none" else 1.0))
        arms.append((s0, elbow, wrist, hand))
    return {"hip": hip, "shoulder": shoulder, "neck": neck, "head": head, "legs": legs, "arms": arms, "lean": lean}


def _capsule(draw, a, b, ra, rb, k):
    """Tapered limb: two circles and the tangent quad between them."""
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy) or 1e-6
    nx, ny = -dy / d, dx / d
    pts = [(ax + nx * ra, ay + ny * ra), (bx + nx * rb, by + ny * rb), (bx - nx * rb, by - ny * rb), (ax - nx * ra, ay - ny * ra)]
    draw.polygon([(x * k, y * k) for x, y in pts], fill=255)
    for (cx, cy), r in ((a, ra), (b, rb)):
        draw.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=255)


def _smooth_poly(points, steps=10):
    """Closed Catmull-Rom spline through points."""
    out, n = [], len(points)
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
    return out


def _draw(pose: dict):
    from PIL import Image, ImageDraw, ImageFilter

    b, k = BODY, CANVAS
    sk = _skeleton(pose)
    pad = 400
    im = Image.new("L", (int((H + 2 * pad) * k), int((H + 2 * pad) * k)), 0)
    off = (H / 2 + pad, pad)  # figure x is centred on 0
    dr = ImageDraw.Draw(im)

    def T(p):
        return (p[0] + off[0], p[1] + off[1])

    def cap(a, c, ra, rc):
        _capsule(dr, T(a), T(c), ra, rc, k)

    def ell(c, rx, ry):
        x, y = T(c)
        dr.ellipse([(x - rx) * k, (y - ry) * k, (x + rx) * k, (y + ry) * k], fill=255)

    lw = b["leg_w"]
    for hip, knee, ankle, toe, heel in sk["legs"]:
        cap(hip, knee, lw[0], lw[1])
        cap(knee, ankle, lw[1], lw[2])
        cap(heel, toe, 17, 12)  # shoe
        cap(ankle, _pt(ankle, 90, 22), 20, 17)
    # torso, a side view: chest and back, a slim waist, jacket over the hips
    hip, sh = sk["hip"], sk["shoulder"]
    ux, uy = sh[0] - hip[0], sh[1] - hip[1]
    ln = math.hypot(ux, uy)
    ux, uy = ux / ln, uy / ln
    fx, fy = -uy, ux
    if fx < 0:
        fx, fy = -fx, -fy

    def P(t, side, w):
        return (hip[0] + ux * ln * t + fx * w * side, hip[1] + uy * ln * t + fy * w * side)

    # (t up the spine, front half-width, back half-width)
    prof = [(-0.06, 60, 66), (0.12, 58, 64), (0.38, 56, 56), (0.62, 66, 60), (0.84, 70, 64), (1.0, 52, 58)]
    poly = _smooth_poly([P(t, 1, f) for t, f, _ in prof] + [P(t, -1, bk) for t, _, bk in reversed(prof)], 8)
    dr.polygon([(T(p)[0] * k, T(p)[1] * k) for p in poly], fill=255)
    ell(_pt(sh, 180, 4), 62, 40)  # shoulders round over the top
    cap(sh, sk["neck"], 30, 26)
    hx, hy = sk["head"]
    rx, ry = b["head"]
    ell((hx + 4, hy), rx, ry)
    ell((hx - 6, hy - 6), rx - 2, ry - 6)  # hair volume at the back of the head
    ell((hx + 10, hy + 26), rx - 16, ry - 30)  # jaw, a little forward
    aw = b["arm_w"]
    for s0, elbow, wrist, hand in sk["arms"]:
        cap(s0, elbow, aw[0], aw[1])
        cap(elbow, wrist, aw[1], aw[2])
        if hand == "":
            ang = math.degrees(math.atan2(wrist[0] - elbow[0], wrist[1] - elbow[1]))
            cap(wrist, _pt(wrist, ang, 34), 20, 15)
        elif hand == "fist":
            ell(wrist, 22, 22)
            ell(_pt(wrist, 150, 30), 14, 20)  # the phone
    # soften every join into one organic outline
    return im.filter(ImageFilter.GaussianBlur(6 * k)).point(lambda v: 255 if v > 120 else 0)


def _trace(im) -> tuple[str, list[float]]:
    """Binary raster -> one path d (figure units), viewBox with the soles on its bottom edge."""
    import tempfile

    import vtracer
    from PIL import Image, ImageOps

    bbox = im.getbbox()
    crop = im.crop(bbox)
    inv = ImageOps.invert(crop).convert("RGB")  # vtracer binary traces dark shapes
    pad = 8
    canvas = Image.new("RGB", (inv.width + 2 * pad, inv.height + 2 * pad), (255, 255, 255))
    canvas.paste(inv, (pad, pad))
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "f.png", Path(td) / "f.svg"
        canvas.save(src)
        vtracer.convert_image_to_svg_py(str(src), str(dst), colormode="binary", mode="spline", filter_speckle=16,
                                        corner_threshold=80, length_threshold=6.0, max_iterations=10,
                                        splice_threshold=45, path_precision=2)
        svg = dst.read_text(encoding="utf-8")
    ds = []
    for tag in re.findall(r"<path[^>]*>", svg):
        d = re.search(r'\sd="([^"]+)"', tag)
        tr = re.search(r'translate\(([-\d.]+)[ ,]([-\d.]+)\)', tag)
        if d:
            ds.append((d.group(1), float(tr.group(1)) if tr else 0.0, float(tr.group(2)) if tr else 0.0))
    if not ds:
        raise SystemExit("figure: trace produced no path")
    from . import svgflat
    from .pdf import svg_path_to

    s = 1 / CANVAS
    parts = []
    for d, tx, ty in ds:
        rec = svgflat._Recorder((s, 0, 0, s, (tx - pad) * s, (ty - pad) * s))
        svg_path_to(rec, d)
        for sp in rec.subpaths:
            for seg in sp:
                parts.append("Z" if seg[0] == "Z" else seg[0] + " ".join(f"{v:.1f}" for v in seg[1:]))
    return " ".join(parts), [0, 0, round(crop.width / CANVAS, 1), round(crop.height / CANVAS, 1)]


def figure_file(name: str) -> Path:
    """Cached SVG for `name` (a pose, optionally `-left` for the mirrored one)."""
    left = name.endswith("-left")
    pose_name = name[:-5] if left else name
    if pose_name not in POSES:
        raise SystemExit(f"figure:{name}: unknown pose (have: {', '.join(POSES)}; add -left to mirror)")
    f = CACHE / f"v{VERSION}-{name}.svg"
    if f.exists():
        return f
    d, vb = _trace(_draw(POSES[pose_name]))
    tr = f' transform="translate({vb[2]} 0) scale(-1 1)"' if left else ""
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb[2]} {vb[3]}" width="{vb[2]}" '
                 f'height="{vb[3]}"><path{tr} fill="#000" fill-rule="nonzero" d="{d}"/></svg>', encoding="utf-8")
    return f


def aspect(name: str) -> float:
    """width / height of a figure: w for a layer of height h is h * aspect."""
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', figure_file(name).read_text(encoding="utf-8"))
    return float(m.group(1)) / float(m.group(2))


def sheet(out: Path) -> Path:
    from .render import svg_to_image

    names = list(POSES)
    cell = 260
    parts = []
    for i, n in enumerate(names):
        a = aspect(n)
        h = 200
        w = h * a
        x = i * cell + (cell - w) / 2
        body = re.search(r"<path[^>]*/>", figure_file(n).read_text(encoding="utf-8")).group(0)
        vb = re.search(r'viewBox="([^"]+)"', figure_file(n).read_text(encoding="utf-8")).group(1)
        parts.append(f'<svg x="{x:.1f}" y="30" width="{w:.1f}" height="{h}" viewBox="{vb}">{body}</svg>'
                     f'<line x1="{i * cell + 20}" y1="230" x2="{i * cell + cell - 20}" y2="230" stroke="#bbb"/>'
                     f'<text x="{i * cell + cell / 2}" y="262" font-size="18" text-anchor="middle" fill="#555">{n}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{cell * len(names)}" height="285">'
           f'<rect width="100%" height="100%" fill="#F3EFE6"/>{"".join(parts)}</svg>')
    out.parent.mkdir(parents=True, exist_ok=True)
    svg_to_image(svg, out.parent).save(out)
    return out


def register(sub) -> None:
    p = sub.add_parser("figure", help="human silhouettes for `figure:<pose>` svg sources")
    s = p.add_subparsers(dest="figure_cmd", required=True)
    s.add_parser("list", help="poses")
    sh = s.add_parser("show", help="contact sheet of every pose")
    sh.add_argument("--out", default=None)

    def run(a):
        if a.figure_cmd == "list":
            return {"poses": {n: {"desc": p["desc"], "aspect": round(aspect(n), 3)} for n, p in POSES.items()},
                  "use": {"type": "svg", "src": "figure:walk", "h": 70, "w": "h * aspect",
                          "cast": {"angle": 24, "length": 1.5, "blur": 1.2, "color": "$ink/85"}},
                  "note": "figures face right; figure:<pose>-left mirrors. Feet = bottom of the layer box."}
        else:
            out = Path(a.out) if a.out else CACHE / "sheet.png"
            return {"sheet": str(sheet(out))}

    p.set_defaults(func=run)
