"""`da qa`: checks a design the way a picky art director and a print shop would, from the actual
render (not guesses): overflowing text, missing glyphs/fonts, contrast against what is really
under the text, safe zones, tiny text, soft images, bleed and margins, font families, off-brand
colours, overlapping text and near-miss alignments.

Each issue: {level: error|warn|info, artboard, layer, check, message, fix}.
"""
from __future__ import annotations

import copy
import json
import re

from . import colors as C
from . import design as D
from .project import Project

LIVE_ROLES = ("logo", "cta", "headline", "body")


def _issue(out, level, ab, layer, check, message, fix=""):
    out.append({"level": level, "artboard": ab, "layer": layer, "check": check, "message": message, "fix": fix})


def _kind(ab: dict) -> str:
    from . import presets

    if ab.get("preset") in presets.PRESETS:
        return presets.PRESETS[ab["preset"]]["kind"]
    return "print" if ab.get("unit", "px") != "px" else "social"


def _hide(layers: list, lid: str) -> list:
    out = []
    for l in layers:
        l = dict(l)
        if l.get("id") == lid:
            l["hidden"] = True
        elif l.get("type") == "group":
            l["layers"] = _hide(l.get("layers", []), lid)
        out.append(l)
    return out


def _text_bbox(t: dict) -> tuple[float, float, float, float] | None:
    """Ink-ish box of laid-out text (local coords): x0, y0, x1, y1."""
    lines = [ln for ln in t["lines"] if ln["text"].strip()]
    if not lines:
        return None
    s = t["size"]
    x0 = min(ln["x"] for ln in lines)
    x1 = max(ln["x"] + ln["width"] for ln in lines)
    return x0, lines[0]["baseline"] - s * 0.75, x1, lines[-1]["baseline"] + s * 0.22


def _geom(l: dict, unit: str, dpi: float, ox: float, oy: float, rep) -> tuple[float, float, float, float] | None:
    """Absolute box (x0, y0, x1, y1) of a layer in artboard units."""
    L = lambda k: D.length(l.get(k), unit, dpi) if l.get(k) is not None else 0.0  # noqa: E731
    t = l.get("type")
    if t == "text":
        tx = rep.texts.get(l.get("id"))
        if not tx:
            return None
        b = _text_bbox(tx)
        return None if b is None else (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)
    if t == "line":
        xs, ys = (L("x"), L("x2")), (L("y"), L("y2"))
        return min(xs) + ox, min(ys) + oy, max(xs) + ox, max(ys) + oy
    if t == "group" and not l.get("w"):
        return None
    return L("x") + ox, L("y") + oy, L("x") + L("w") + ox, L("y") + L("h") + oy


def _is_bg(l, box, W, H) -> bool:
    if l.get("role") in ("background", "photo") or l.get("anchor") == "fill":
        return True
    x0, y0, x1, y1 = box
    return (x1 - x0) * (y1 - y0) >= 0.85 * W * H


def _size_pt(size_units: float, unit: str, dpi: float) -> float:
    if unit == "px":
        return size_units * 72 / dpi
    return size_units / D.UNITS_PER_INCH[unit] * 72


def _literal_colors(v) -> list[str]:
    if isinstance(v, str):
        return [v] if not v.startswith("$") and v.lower() not in ("none", "transparent") else []
    if isinstance(v, dict):
        if "stops" in v:
            return [c for _, c in v["stops"] for c in _literal_colors(c)]
        if "color" in v:
            return _literal_colors(v["color"])
        if "hex" in v:
            return _literal_colors(v["hex"])
    return []


def _widow(l: dict, tx: dict) -> str | None:
    """The last line of a wrapped paragraph when it holds one or two short words (a widow): 3+ lines,
    the line came from wrapping (not a hand-made "\\n") and is under 40% of the longest line."""
    lines = tx.get("lines") or []
    if len(lines) < 3 or not l.get("w"):
        return None
    last = lines[-1]["text"].strip()
    para = re.sub(r"\*\*", "", str(l.get("text", ""))).split("\n")[-1].strip()
    if not last or last.lower() == para.lower():
        return None
    widest = max(ln["width"] for ln in lines)
    if len(last.split()) <= 2 and lines[-1]["width"] < 0.4 * widest:
        return last
    return None


def contrast_check(ctx, ab, l, box, scale, issues, cache):
    """Contrast of a text layer's colour(s) against the render without that layer, in its ink box."""
    import numpy as np

    from .render import render_artboard

    lid = l["id"]
    colors = []
    try:
        base = ctx.color(l.get("color", l.get("fill", "$ink")))
        if base is not None:
            colors.append(("text", base))
        acc = (l.get("accent") or {}).get("color")
        if acc and "**" in l.get("text", ""):
            colors.append(("accent", ctx.color(acc)))
    except C.ColorError:
        return
    if not colors:
        return
    hl = l.get("highlight")
    if isinstance(hl, dict) and hl.get("color"):
        try:
            bgc = ctx.color(hl["color"])
        except C.ColorError:
            bgc = None
        if bgc is not None and bgc.a >= 0.99:
            ratios = [(n, C.contrast(c, bgc)) for n, c in colors]
            _grade(issues, ab, l, ratios, ctx)
            return
    hidden = copy.deepcopy(ab)
    hidden["layers"] = _hide(ab["layers"], lid)
    im, _ = render_artboard(ctx, hidden, scale)
    ppu = D.px_per_unit(ab) * scale
    x0, y0, x1, y1 = (int(round(v * ppu)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, max(x0 + 1, x1)), min(im.height, max(y0 + 1, y1))
    if x1 <= x0 or y1 <= y0:
        return
    from PIL import ImageFilter

    # film grain / noise layers are specks, not background: a small median filter removes them before measuring
    crop = im.convert("RGB").crop((x0, y0, x1, y1))
    if min(crop.size) >= 5:
        crop = crop.filter(ImageFilter.MedianFilter(5))
    region = np.asarray(crop, dtype=np.float64).reshape(-1, 3)
    if len(region) > 40000:
        region = region[np.random.default_rng(0).choice(len(region), 40000, replace=False)]
    lin = region / 255
    lin = np.where(lin <= 0.04045, lin / 12.92, ((lin + 0.055) / 1.055) ** 2.4)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    ratios = []
    for n, c in colors:
        if c.a < 1:  # composite over the average background
            avg = region.mean(axis=0)
            c = C.blend_over(c, C.Color(int(avg[0]), int(avg[1]), int(avg[2])))
        lt = C.luminance(c)
        r = (np.maximum(lum, lt) + 0.05) / (np.minimum(lum, lt) + 0.05)
        ratios.append((n, round(float(np.percentile(r, 10)), 2)))  # worst 10% of the background
    _grade(issues, ab, l, ratios, ctx)


def _grade(issues, ab, l, ratios, ctx):
    unit, dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
    size = D.length(l.get("size", 48), unit, dpi)
    pt = _size_pt(size, unit, dpi) if unit != "px" else size * 0.75  # CSS px -> pt
    weight = int(ctx.font_spec(l).get("weight", 400))
    large = pt >= 18 or (pt >= 14 and weight >= 700)
    need = 3.0 if large else 4.5
    for name, r in ratios:
        if r < need:
            level = "error" if r < 3.0 else "warn"
            _issue(issues, level, ab["id"], l["id"], "contrast",
                   f"{name} contrast {r}:1 against what's behind it (WCAG AA needs {need}:1 for {'large' if large else 'normal'} text)",
                   "darken/lighten the text, add a shade or highlight box behind it, or move it to a calmer area")


def qa(project: Project, artboards: list[str] | None = None, contrast: bool = True) -> dict:
    from .render import render_artboard

    d = D.load(project)
    ctx = D.context(project, d)
    issues: list[dict] = []
    v = D.validate(d, ctx)
    for e in v["errors"]:
        _issue(issues, "error", None, None, "structure", e, "fix design.json, then `da validate`")
    if v["errors"]:
        return _summary(issues, [])
    families: set[str] = set()
    adobe_out = project.path("output", "adobe")
    has_adobe = adobe_out.is_dir() and any(adobe_out.iterdir()) or any(project.path("output").glob("**/*.jsx"))
    token_hex = set()
    for k in ctx.colors:
        try:
            c = C.parse(f"${k}", ctx.colors)
            if c:
                token_hex.add(c.hex)
        except C.ColorError:
            pass
    checked = []
    for ab in d["artboards"]:
        if artboards and ab["id"] not in artboards:
            continue
        checked.append(ab["id"])
        aid = ab["id"]
        unit, dpi = ab.get("unit", "px"), float(ab.get("dpi", 72))
        W, H = float(ab["width"]), float(ab["height"])
        kind = _kind(ab)
        _, rep = render_artboard(ctx, ab, 1.0)
        for w in rep.warnings:
            _issue(issues, "error" if "missing image" in w else "warn", aid, w.split(":")[0], "render", w)
        scale = min(1.0, 900 / (max(W, H) * D.px_per_unit(ab)))
        safe = [D.length(x, unit, dpi) for x in ab["safe"]] if ab.get("safe") else None
        margin = D.length(ab["margin"], unit, dpi) if ab.get("margin") else None
        bleed = D.length(ab.get("bleed", 0), unit, dpi)
        unit_px = 1.0 if unit == "px" else D.length("1px", unit, 96)  # near-miss tolerance unit
        boxes = []
        for l, ox, oy in D.walk(ab.get("layers", [])):
            lid, t = l.get("id"), l.get("type")
            box = _geom(l, unit, dpi, ox, oy, rep)
            if t == "text":
                tx = rep.texts.get(lid)
                if tx:
                    if tx["overflow"] or tx["truncated"]:
                        _issue(issues, "error", aid, lid, "overflow",
                               f"text doesn't fit its box{' (lines cut by max_lines)' if tx['truncated'] else ''}",
                               "shorten the copy, enlarge the box, or set autofit")
                    if tx["missing_glyphs"]:
                        _issue(issues, "error", aid, lid, "glyphs", f"font has no glyph for {''.join(tx['missing_glyphs'])}",
                               "pick a font that covers these characters or change the text")
                    for fam in tx["fallback_fonts"]:
                        _issue(issues, "error", aid, lid, "font", f"font {fam!r} not found; rendered with Montserrat",
                               f"`da fonts get \"{fam}\"` or put the font file in the brand kit / input/")
                    for f in tx["fonts"]:  # "Montserrat 800 italic" -> "Montserrat"
                        families.add(re.sub(r" \d+( italic)?$", "", f))
                    size = tx["size"]
                    if kind == "social":
                        min_px = 24 * min(W, H * 0.8) / 1080 if unit == "px" else None
                        if min_px and size < min_px:
                            _issue(issues, "warn", aid, lid, "tiny-text", f"text is {size:.0f} px; under {min_px:.0f} px it's unreadable on a phone",
                                   "make it bigger or cut it")
                    elif kind == "web" and unit == "px" and size < 12:
                        _issue(issues, "warn", aid, lid, "tiny-text", f"text is {size:.1f} px (min 12 px on screens)", "make it bigger")
                    elif kind == "print" or unit != "px":
                        pt = _size_pt(size, unit, dpi)
                        if pt < 6:
                            _issue(issues, "warn", aid, lid, "tiny-text", f"text is {pt:.1f} pt; under 6 pt doesn't print legibly",
                                   "use at least 6-7 pt (8 pt+ for body)")
                    widow = _widow(l, tx)
                    if widow:
                        _issue(issues, "warn", aid, lid, "widow", f"last line {widow!r} is left alone under the paragraph",
                               "break the lines by hand with \\n so they balance, or change the width a little")
                    if contrast and box:
                        contrast_check(ctx, ab, l, box, scale, issues, None)
            if t == "image" and lid in rep.images:
                info = rep.images[lid]
                up = info["upscaled"]
                if kind == "print" or unit != "px":
                    eff = dpi / up if up else dpi
                    if eff < 300:
                        _issue(issues, "error" if eff < 150 else "warn", aid, lid, "resolution",
                               f"image prints at ~{eff:.0f} dpi (source {info['source_px'][0]}x{info['source_px'][1]} px for this box)",
                               "use a larger original, shrink the box, or upscale with `da image upscale`")
                elif up > 1.25:
                    _issue(issues, "error" if up > 2 else "warn", aid, lid, "resolution",
                           f"image is enlarged {up:.2f}x (source {info['source_px'][0]}x{info['source_px'][1]} px)",
                           "use a larger original or a smaller box")
            if box is None:
                continue
            x0, y0, x1, y1 = box
            if x1 < 0 or y1 < 0 or x0 > W or y0 > H:
                _issue(issues, "warn", aid, lid, "off-canvas", "layer is entirely outside the artboard", "move it in or delete it")
                continue
            live = t in ("text", "svg", "icon") or l.get("role") in LIVE_ROLES
            bg = _is_bg(l, box, W, H)
            if live and not bg and safe:
                if x0 < safe[3] - 0.5 or y0 < safe[0] - 0.5 or x1 > W - safe[1] + 0.5 or y1 > H - safe[2] + 0.5:
                    _issue(issues, "warn", aid, lid, "safe-zone",
                           "outside the safe zone (platform UI or cropping covers it)", "move it inside the safe zone")
            if live and not bg and margin is not None:
                if x0 < margin - 0.01 or y0 < margin - 0.01 or x1 > W - margin + 0.01 or y1 > H - margin + 0.01:
                    _issue(issues, "warn", aid, lid, "margin",
                           f"closer than {margin:g} {unit} to the trim: may be cut off", "keep text and logos inside the margin")
            if bleed > 0 and not live and t in ("rect", "image", "path", "ellipse"):
                for edge, touches, extends in (("left", x0 <= 0.5 * unit_px and x0 > -bleed + 0.01, x0 <= -bleed + 0.01),
                                               ("top", y0 <= 0.5 * unit_px and y0 > -bleed + 0.01, y0 <= -bleed + 0.01),
                                               ("right", x1 >= W - 0.5 * unit_px and x1 < W + bleed - 0.01, x1 >= W + bleed - 0.01),
                                               ("bottom", y1 >= H - 0.5 * unit_px and y1 < H + bleed - 0.01, y1 >= H + bleed - 0.01)):
                    if touches and not extends:
                        _issue(issues, "warn", aid, lid, "bleed",
                               f"touches the {edge} trim edge but doesn't extend into the {bleed:g} {unit} bleed: a white sliver after cutting",
                               f"extend it {bleed:g} {unit} past the edge")
            if not bg:
                boxes.append((l, box, ox, oy))
            if ctx.brand_dir:
                for key in ("fill", "color"):
                    for lit in _literal_colors(l.get(key)):
                        try:
                            c = C.parse(lit)
                        except C.ColorError:
                            continue
                        if c and c.hex not in token_hex and c.hex not in ("#FFFFFF", "#000000"):
                            _issue(issues, "warn", aid, lid, "off-brand", f"colour {c.hex} isn't in the brand palette",
                                   "use a $token from the brand kit (or add the colour to it)")
        # overlapping text boxes
        texts = [(l, b) for l, b, _, _ in boxes if l.get("type") == "text"]
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                (la, a), (lb, b) = texts[i], texts[j]
                ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
                iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
                small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
                if ix * iy > 0.1 * small:
                    _issue(issues, "warn", aid, la["id"], "overlap", f"text overlaps {lb['id']}", "separate them or merge into one text layer")
        # near-miss left edges. Text is compared by its INK (glyph outlines), not its box: big type is often
        # nudged left on purpose so the letters line up optically with smaller text. Icons sit centred in
        # their own padding, so they're left out.
        def left(l, b, ox, oy):
            if l.get("type") == "text":
                from . import text as T

                ink = T.ink_box(T.layout(l, ctx, unit, dpi, ox, oy))
                if ink:
                    return ink[0]
            return b[0]

        kinds = {l["id"]: l.get("type") for l, _, _, _ in boxes}
        lefts = sorted((left(l, b, ox, oy), l["id"]) for l, b, ox, oy in boxes
                       if l.get("type") in ("text", "rect", "image", "svg"))
        hi = 6 * unit_px
        seen = set()
        for i in range(len(lefts)):
            for j in range(i + 1, len(lefts)):
                dx = lefts[j][0] - lefts[i][0]
                if dx > hi:
                    break
                # ink edges of different letters differ by 1-2 px by design (round letters overshoot)
                lo = (3 if "text" in (kinds[lefts[i][1]], kinds[lefts[j][1]]) else 1) * unit_px
                if lo <= dx <= hi and (lefts[i][1], lefts[j][1]) not in seen:
                    seen.add((lefts[i][1], lefts[j][1]))
                    _issue(issues, "info", aid, lefts[j][1], "alignment",
                           f"left edge {dx:.1f} {unit} off {lefts[i][1]}'s: align them exactly or make the offset deliberate",
                           f"set the same x as {lefts[i][1]}")
        if has_adobe:
            for f in rep.fonts:
                if not f.installed and not f.fallback:
                    _issue(issues, "warn", aid, None, "font-install",
                           f"{f.family} isn't installed on this machine: Photoshop/Illustrator will substitute it",
                           f"`da fonts install \"{f.family}\"`")
    fams = sorted(families)
    if len(fams) > 3:
        _issue(issues, "warn", None, None, "families", f"{len(fams)} font families ({', '.join(fams)}); 2-3 reads as a system",
               "cut down to a display + a text family")
    # de-duplicate (font-install repeats per artboard)
    uniq, seen_keys = [], set()
    for it in issues:
        key = (it["level"], it["check"], it["layer"], it["message"]) if it["check"] == "font-install" else id(it)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        uniq.append(it)
    return _summary(uniq, checked)


def _summary(issues, checked) -> dict:
    order = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: (order[i["level"]], str(i["artboard"]), str(i["layer"])))
    n = {k: sum(1 for i in issues if i["level"] == k) for k in order}
    return {"ok": n["error"] == 0, "checked": checked, "errors": n["error"], "warnings": n["warn"], "info": n["info"],
            "issues": issues}


def cmd_qa(a):
    res = qa(Project(a.project), a.artboard, not a.no_contrast)
    if a.strict and not res["ok"]:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        raise SystemExit(1)
    return res


def register(sub) -> None:
    p = sub.add_parser("qa", help="check a design: overflow, fonts, contrast, safe zones, resolution, bleed, alignment")
    p.add_argument("project")
    p.add_argument("--artboard", nargs="*")
    p.add_argument("--strict", action="store_true", help="exit 1 when there are errors")
    p.add_argument("--no-contrast", action="store_true", help="skip the (slower) contrast renders")
    p.set_defaults(func=cmd_qa)
