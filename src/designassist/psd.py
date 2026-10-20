"""Layered PSD via psd-tools: every layer becomes a named pixel layer (groups stay PSD groups),
cropped to its own bounds, with opacity and blend mode carried as layer properties. Opens in
Photoshop, Affinity, Photopea and GIMP without Photoshop being installed here.

Text is pixels in this file; for live, editable text in Photoshop use `da export --to photoshop`
(a script that builds the document inside Photoshop).
"""
from __future__ import annotations

from pathlib import Path

from . import design as D

BLEND = {"normal": "NORMAL", "multiply": "MULTIPLY", "screen": "SCREEN", "overlay": "OVERLAY", "darken": "DARKEN",
         "lighten": "LIGHTEN", "color-dodge": "COLOR_DODGE", "color-burn": "COLOR_BURN", "hard-light": "HARD_LIGHT",
         "soft-light": "SOFT_LIGHT", "difference": "DIFFERENCE", "exclusion": "EXCLUSION", "hue": "HUE",
         "saturation": "SATURATION", "color": "COLOR", "luminosity": "LUMINOSITY"}


def _solo(ctx, ab: dict, layer: dict, ox: float, oy: float, scale: float):
    """Render one layer alone (absolute position kept) with opacity/blend/hidden stripped: those
    become PSD layer properties. Returns (cropped RGBA image, left, top) or None when empty."""
    from .render import render_artboard

    clean = {k: v for k, v in layer.items() if k not in ("opacity", "blend", "hidden")}
    wrapped = {"id": "__solo__", "type": "group", "x": ox, "y": oy, "layers": [clean]}
    im, _ = render_artboard(ctx, {**ab, "layers": [wrapped]}, scale, only=["__solo__"], background=False)
    box = im.getchannel("A").getbbox()
    if not box:
        return None
    return im.crop(box), box[0], box[1]


def write(project, ab_id: str | None, out: Path, scale: float = 1.0) -> dict:
    from psd_tools import PSDImage
    from psd_tools.api.layers import Group, PixelLayer
    from psd_tools.constants import BlendMode

    from .render import render_artboard

    d = D.load(project)
    ctx = D.context(project, d)
    ab = D.artboard(d, ab_id)
    ppu = D.px_per_unit(ab) * scale
    W, H = round(float(ab["width"]) * ppu), round(float(ab["height"]) * ppu)
    psd = PSDImage.new("RGB", (W, H), color=(255, 255, 255))
    names: list[str] = []
    if ab.get("background") not in (None, "none"):
        bg, _ = render_artboard(ctx, {**ab, "layers": []}, scale, only=[], background=True)
        PixelLayer.frompil(bg, psd, "background", top=0, left=0)
        names.append("background")

    def add(layer: dict, parent, ox: float, oy: float) -> None:
        name = str(layer.get("name") or layer.get("id"))
        if layer.get("type") == "group" and not layer.get("clip") and not layer.get("shadow"):
            g = Group.new(parent, name)
            gx, gy = ox + D.length(layer.get("x"), ab.get("unit", "px"), float(ab.get("dpi", 72))), \
                oy + D.length(layer.get("y"), ab.get("unit", "px"), float(ab.get("dpi", 72)))
            for ch in layer.get("layers", []):
                add(ch, g, gx, gy)
            node = g
        else:
            solo = _solo(ctx, ab, layer, ox, oy, scale)
            if solo is None:
                return
            im, left, top = solo
            node = PixelLayer.frompil(im, parent, name, top=top, left=left)
        names.append(name)
        if layer.get("opacity", 1) != 1:
            node.opacity = max(0, min(255, round(float(layer["opacity"]) * 255)))
        if layer.get("blend") and layer["blend"] != "normal":
            node.blend_mode = getattr(BlendMode, BLEND.get(layer["blend"], "NORMAL"))
        if layer.get("hidden"):
            node.visible = False

    for l in ab.get("layers", []):
        add(l, psd, 0.0, 0.0)
    out.parent.mkdir(parents=True, exist_ok=True)
    psd.save(str(out))
    return {"file": project.rel(out), "artboard": ab["id"], "px": [W, H], "layers": names,
            "note": "text is pixels here; `--to photoshop` builds live, editable text in Photoshop"}
