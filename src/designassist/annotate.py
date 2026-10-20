"""Annotation helpers for build scripts: the "computer vision" look (a thin box around something + a small
solid label on its edge) and crops of screenshots placed at exact coordinates. Everything comes out as plain
design.json layers (rect, text with highlight, clipped group + image), so every export and Affinity keep them
editable.

    from designassist import annotate as A
    shot, at, h = A.crop("s4-shot", "work/telas/reunioes@4x.png", (680, 622, 1480, 776), x=96, y=96, w=984,
                         src_size=(2560, 1720), filters={"grayscale": 1})
    layers += [shot] + A.track("ata", *at(704, 976, 268, 72), "ata pronta")
    word = {"id": "w", "type": "text", "text": "ROTEIRO", ...}
    layers += [word] + A.track("w-t", *A.around(word, ctx, pad=14), "maestro")  # box hugging the ink

`region` and the `at()` coordinates are in `src_size` units (the screenshot's 1x/2x pixel grid), whatever the
file's real resolution: recapture at 4x and the layout stays put.
"""
from __future__ import annotations


def tag(id: str, text: str, x: float, y: float, color="$primary", ink="$paper", size: float = 24, font="$label") -> dict:
    """A small caps label on a solid chip (the chip is the text's highlight, so it hugs the words)."""
    return {"id": id, "type": "text", "text": text, "x": round(x, 1), "y": round(y, 1), "font": font, "size": size,
            "tracking": 50, "case": "upper", "color": ink, "highlight": {"color": color, "pad": [0.45, 0.32]}}


def track(id: str, x: float, y: float, w: float, h: float, label: str | None = None, color="$primary", ink="$paper",
          width: float = 2.5, below: bool = False, size: float = 24) -> list[dict]:
    """A tracking box around (x, y, w, h) and its label on the top edge (or under the box)."""
    out = [{"id": f"{id}-box", "type": "rect", "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1),
            "fill": "none", "stroke": {"color": color, "width": width}}]
    if label:
        ty = y + h + size * 0.66 if below else y - size * 1.5
        out.append(tag(f"{id}-tag", label, x + size * 0.38, ty, color, ink, size))
    return out


def around(layer: dict, ctx, pad: float | tuple = 12, unit: str = "px", dpi: float = 72) -> tuple:
    """(x, y, w, h) of a text layer's ink (glyph outlines, not the line box) grown by `pad` (one value or
    (x, y)): a tracking box that hugs the words. ctx = design.context(project, doc) of the project it goes in."""
    from . import text as T

    box = T.ink_box(T.layout(layer, ctx, unit, dpi))
    if box is None:
        raise ValueError(f"{layer.get('id')}: no ink to box")
    px, py = pad if isinstance(pad, (tuple, list)) else (pad, pad)
    x0, y0, x1, y1 = box
    return x0 - px, y0 - py, x1 - x0 + 2 * px, y1 - y0 + 2 * py


def crop(id: str, src: str, region: tuple, x: float, y: float, w: float, src_size: tuple, filters: dict | None = None,
         shadow: dict | None = None):
    """Show `region` (x, y, w, h in src_size units) of an image `w` wide at (x, y). Returns (group layer,
    at(rx, ry, rw, rh) -> artboard box of a region inside it, height)."""
    x0, y0, w0, h0 = region
    s = w / w0
    h = round(h0 * s, 1)
    img = {"id": f"{id}-img", "type": "image", "src": src, "x": round(-x0 * s, 1), "y": round(-y0 * s, 1),
           "w": round(src_size[0] * s, 1), "h": round(src_size[1] * s, 1), "fit": "fill"}
    if filters:
        img["filters"] = filters
    g = {"id": id, "type": "group", "x": x, "y": y, "w": w, "h": h, "clip": True, "role": "photo", "layers": [img]}
    if shadow:
        g["shadow"] = shadow

    def at(rx: float, ry: float, rw: float, rh: float) -> tuple:
        return x + (rx - x0) * s, y + (ry - y0) * s, rw * s, rh * s
    return g, at, h
