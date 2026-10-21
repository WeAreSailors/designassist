"""`da resize`: adapt one artboard to other formats (post -> story, thumbnail, banner...).

A first pass the model then reviews, not a final layout:
- background/photo layers (role background|photo, anchor fill, or covering >= 90% of the canvas)
  re-cover the whole new canvas (images keep their focus point);
- a photo placed by hand (a cut-out larger than the canvas, or fit fill/contain) keeps its aspect and
  framing: it scales by sqrt(sx * sy) around the canvas centre instead of being stretched over it;
- text layers stacked on top of each other (one layer per headline line) move as one block, so the
  safe-zone nudge can't pile them onto the same edge;
- every other top-level layer scales by min(sx, sy) and keeps its distance to its anchor
  (explicit `anchor`, else the nearest edge / centre on each axis);
- text keeps its box (scaled) with autofit on, so longer lines shrink instead of overflowing;
- anything that ends up outside the new safe zone (or canvas) is nudged inside.
"""
from __future__ import annotations

import copy

from . import design as D
from .project import Project

TEXT_LENGTHS = ("size", "min_size")
SCALED = ("x", "y", "w", "h", "x2", "y2", "radius")


def _bbox(l: dict, unit: str, dpi: float) -> tuple[float, float, float, float]:
    L = lambda k: D.length(l.get(k), unit, dpi) if l.get(k) is not None else 0.0  # noqa: E731
    if l.get("type") == "line":
        x1, y1, x2, y2 = L("x"), L("y"), L("x2"), L("y2")
        return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)
    w, h = L("w"), L("h")
    if l.get("type") == "text" and not h:
        h = (L("size") or 48) * float(l.get("line_height", 1.2))
    return L("x"), L("y"), w, h


def infer_anchor(x, y, w, h, W, H) -> str:
    def axis(a, s, total, lo, hi):
        c = a + s / 2
        if s >= total * 0.8:  # spans the axis: hold its start edge (wide text keeps its left margin)
            return lo
        d = {lo: a, "c": abs(c - total / 2), hi: total - (a + s)}
        return min(d, key=d.get)

    ax = axis(x, w, W, "left", "right")
    ay = axis(y, h, H, "top", "bottom")
    if ax in ("c", "stretch") and ay in ("c", "stretch"):
        return "center"
    if ax in ("c", "stretch"):
        return ay
    if ay in ("c", "stretch"):
        return ax
    return f"{ay}-{ax}"


def _is_background(l: dict, x, y, w, h, W, H) -> bool:
    if l.get("role") in ("background", "photo") or l.get("anchor") == "fill":
        return True
    return w * h >= 0.9 * W * H and x <= W * 0.05 and y <= H * 0.05


def _is_placed_photo(l: dict, x, y, w, h, W, H) -> bool:
    """A photo layer framed by hand: a cut-out PNG bigger than the canvas, or fit fill/contain."""
    if l.get("type") != "image" or l.get("role") != "photo" or l.get("anchor") == "fill":
        return False
    tol = 0.01 * max(W, H)
    return l.get("fit", "cover") != "cover" or x < -tol or y < -tol or x + w > W + tol or y + h > H + tol


def _text_blocks(items: list[tuple[int, dict, tuple]], H: float) -> list[list[int]]:
    """Group text layers that sit on top of each other (overlapping columns, vertical gap <= 6% of the
    height) into blocks; every other layer is a block of its own. items = (index, layer, bbox)."""
    blocks: list[list[int]] = []
    texts = sorted((it for it in items if it[1].get("type") == "text"), key=lambda it: it[2][1])
    for i, l, (x, y, w, h) in texts:
        for b in blocks:
            j, _, (bx, by, bw, bh) = next(it for it in items if it[0] == b[-1])
            if x < bx + bw and bx < x + w and -0.01 * H <= y - (by + bh) <= 0.06 * H:
                b.append(i)
                break
        else:
            blocks.append([i])
    seen = {i for b in blocks for i in b}
    blocks += [[it[0]] for it in items if it[0] not in seen]
    return blocks


def _scale_layer(l: dict, r: float, unit: str, dpi: float) -> None:
    """Every length of a layer (and its children) times r: source unit -> target unit, already scaled."""
    cv = lambda v: round(D.length(v, unit, dpi) * r, 3)  # noqa: E731
    for key in SCALED:
        if key in l and l[key] is not None:
            l[key] = [cv(v) for v in l[key]] if isinstance(l[key], list) else cv(l[key])
    if l.get("type") == "text":
        for key in TEXT_LENGTHS:
            if key in l:
                l[key] = cv(l[key])
        hl = l.get("highlight")
        if isinstance(hl, dict) and "radius" in hl:
            hl["radius"] = cv(hl["radius"])
    for key in ("stroke", "shadow"):
        s = l.get(key)
        if isinstance(s, dict):
            for kk in ("width", "x", "y", "blur"):
                if kk in s:
                    s[kk] = cv(s[kk])
            if isinstance(s.get("dash"), list):
                s["dash"] = [cv(v) for v in s["dash"]]
    for child in l.get("layers", []):
        _scale_layer(child, r, unit, dpi)


def _into_bleed(n: dict, NW: float, NH: float, bleed: float) -> dict:
    """Print targets: a layer touching a trim edge runs on into the bleed (no white sliver after cutting)."""
    if bleed <= 0 or n.get("type") == "group":
        return n
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    x1, y1 = x + w, y + h
    if x <= 0.01:
        x = -bleed
    if y <= 0.01:
        y = -bleed
    if x1 >= NW - 0.01:
        x1 = NW + bleed
    if y1 >= NH - 0.01:
        y1 = NH + bleed
    n.update(x=round(x, 3), y=round(y, 3), w=round(x1 - x, 3), h=round(y1 - y, 3))
    return n


def adapt(src: dict, preset: str, new_id: str) -> tuple[dict, list[str]]:
    """Source artboard -> new artboard in `preset`. One factor r = min(NW/W, NH/H) maps source lengths
    (whatever their unit) to target units, so px -> mm conversions need no separate step."""
    unit, dpi = src.get("unit", "px"), float(src.get("dpi", 72))
    W, H = float(src["width"]), float(src["height"])
    ab = D.new_artboard(preset, new_id, background=src.get("background", "$paper"))
    tu, tdpi = ab["unit"], float(ab["dpi"])
    NW, NH = float(ab["width"]), float(ab["height"])
    sx, sy = NW / W, NH / H
    r = min(sx, sy)
    safe = [D.length(v, tu, tdpi) for v in ab.get("safe", [0, 0, 0, 0])]
    if not ab.get("safe") and ab.get("margin"):
        safe = [D.length(ab["margin"], tu, tdpi)] * 4
    bleed = D.length(ab.get("bleed", 0), tu, tdpi)
    notes: list[str] = []
    placed: list[tuple[int, dict, tuple]] = []  # anchored layers, positioned per block after the loop
    for l in src.get("layers", []):
        x, y, w, h = _bbox(l, unit, dpi)
        n = copy.deepcopy(l)
        if _is_placed_photo(l, x, y, w, h, W, H):
            s = (sx * sy) ** 0.5  # keeps its share of the canvas area, aspect untouched
            _scale_layer(n, r, unit, dpi)
            n.update(x=round(NW / 2 + (x - W / 2) * s, 3), y=round(NH / 2 + (y - H / 2) * s, 3),
                     w=round(w * s, 3), h=round(h * s, 3))
            notes.append(f"{l.get('id')}: placed photo kept its aspect; check the framing")
            ab["layers"].append(n)
            continue
        if _is_background(l, x, y, w, h, W, H):
            if n.get("type") == "group":
                _scale_layer(n, r, unit, dpi)
                notes.append(f"{l.get('id')}: background group scaled; check it still covers the canvas")
            n.update(x=0, y=0, w=NW, h=NH)
            if n.get("type") == "image":
                n.setdefault("fit", "cover")
            ab["layers"].append(_into_bleed(n, NW, NH, bleed))
            continue
        if l.get("type") in ("image", "rect", "path") and (w >= 0.9 * W or h >= 0.9 * H) and not l.get("anchor"):
            # full-bleed band (photo across the top, shade, stripe): keep its share of the canvas on both axes;
            # cover-fit images re-crop, so this never distorts a photo
            _scale_layer(n, r, unit, dpi)
            n.update(x=round(x * sx, 3), y=round(y * sy, 3), w=round(w * sx, 3), h=round(h * sy, 3))
            if n.get("type") == "image":
                n.setdefault("fit", "cover")
            ab["layers"].append(_into_bleed(n, NW, NH, bleed))
            continue
        _scale_layer(n, r, unit, dpi)
        placed.append((len(ab["layers"]), l, (x, y, w, h)))
        ab["layers"].append(n)
    for block in _text_blocks(placed, H):
        members = [it for it in placed if it[0] in block]
        ux = min(b[0] for _, _, b in members)
        uy = min(b[1] for _, _, b in members)
        uw = max(b[0] + b[2] for _, _, b in members) - ux
        uh = max(b[1] + b[3] for _, _, b in members) - uy
        first = members[0][1]
        anchor = first.get("anchor") or infer_anchor(ux, uy, uw, uh, W, H)
        nw, nh = uw * r, uh * r
        cx, cy = ux + uw / 2, uy + uh / 2
        if "left" in anchor:
            px = ux * r
        elif "right" in anchor:
            px = NW - (W - ux - uw) * r - nw
        elif anchor in ("top", "bottom"):  # keep the relative horizontal position
            px = cx / W * NW - nw / 2
        else:
            px = NW / 2 + (cx - W / 2) * r - nw / 2
        if anchor.startswith("top"):
            py = uy * r
        elif anchor.startswith("bottom"):
            py = NH - (H - uy - uh) * r - nh
        elif anchor in ("left", "right"):
            py = cy / H * NH - nh / 2
        else:
            py = NH / 2 + (cy - H / 2) * r - nh / 2
        # nudge into the safe zone (canvas when there is none)
        keep_inside = any(l.get("type") in ("text", "svg", "icon") or l.get("role") in ("logo", "cta", "headline", "body")
                          for _, l, _ in members)
        bx0, bx1, by0, by1 = (safe[3], NW - safe[1], safe[0], NH - safe[2]) if keep_inside else (0, NW, 0, NH)
        if keep_inside or px < 0 or py < 0 or px + nw > NW or py + nh > NH:
            npx = min(max(px, bx0), max(bx0, bx1 - nw))
            npy = min(max(py, by0), max(by0, by1 - nh))
            if keep_inside and (abs(npx - px) > 0.5 or abs(npy - py) > 0.5):
                notes.append(f"{', '.join(str(l.get('id')) for _, l, _ in members)}: nudged into the safe zone")
            px, py = npx, npy
        for idx, l, (x, y, w, h) in members:
            n = ab["layers"][idx]
            mx, my = px + (x - ux) * r, py + (y - uy) * r
            nx, ny, _, mh = _bbox(n, tu, tdpi)
            if n.get("type") == "line":
                dx, dy = mx - nx, my - ny
                n["x"], n["y"] = round(n["x"] + dx, 3), round(n["y"] + dy, 3)
                n["x2"], n["y2"] = round(n["x2"] + dx, 3), round(n["y2"] + dy, 3)
            else:
                n["x"], n["y"] = round(mx, 3), round(my, 3)
            if n.get("type") == "text":
                n["autofit"] = True
                if not n.get("h"):  # a stacked line keeps its height: growing it would shift it off its neighbours
                    n["h"] = round(mh * (1.6 if sy > sx * 1.3 and len(members) == 1 else 1.0), 3)
                if n.get("w") and sx > r * 1.3:  # wider canvas: let the text use the width
                    n["w"] = round(min(NW - safe[1] - n["x"], n["w"] * min(sx / r, 1.8)), 3)
    if abs(sx - sy) / max(sx, sy) > 0.25:
        notes.append(f"aspect changed a lot ({W:g}x{H:g} {unit} -> {NW:g}x{NH:g} {tu}): recompose, don't just accept the scale")
    return ab, notes


def resize(project: Project, from_id: str, presets: list[str], ids: list[str] | None = None, replace: bool = False) -> dict:
    d = D.load(project)
    src = D.artboard(d, from_id)
    made = []
    for i, preset in enumerate(presets):
        new_id = ids[i] if ids and i < len(ids) else f"{from_id}-{preset}"
        existing = [a for a in d["artboards"] if a["id"] == new_id]
        if existing and not replace:
            raise SystemExit(f"artboard {new_id} exists (pass --replace to rebuild it)")
        ab, notes = adapt(src, preset, new_id)
        if existing:
            d["artboards"][d["artboards"].index(existing[0])] = ab
        else:
            d["artboards"].append(ab)
        made.append({"artboard": new_id, "preset": preset, "size": f"{ab['width']:g}x{ab['height']:g} {ab['unit']}",
                     "review": notes})
    D.save(project, d)
    return {"from": from_id, "made": made,
            "next": f"uv run da render {project.name} --artboard {' '.join(m['artboard'] for m in made)}, look, then adjust"}


def cmd_resize(a):
    return resize(Project(a.project), a.from_id, a.to, a.ids, a.replace)


def register(sub) -> None:
    p = sub.add_parser("resize", help="adapt an artboard to other presets (first pass to review)")
    p.add_argument("project")
    p.add_argument("--from", dest="from_id", required=True, help="source artboard id")
    p.add_argument("--to", nargs="+", required=True, help="target presets, e.g. ig-story yt-thumb")
    p.add_argument("--ids", nargs="*", help="ids for the new artboards (default <from>-<preset>)")
    p.add_argument("--replace", action="store_true", help="rebuild artboards that already exist")
    p.set_defaults(func=cmd_resize)
