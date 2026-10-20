"""User settings the tools read (the prose taste lives in preferences.md; these are the knobs commands obey).
Stored in `<memory>/settings.json` (private, per user, outside the repo).

    da settings                       show them
    da settings set resolution max    the highest resolution that still looks good: long side up to 3840 px, lowered
                                      so no photo in the piece is upscaled more than 1.25x (1x at least)
    da settings set resolution 4k     long side exactly 3840 px (2k = 2560, 8k = 7680)
    da settings set resolution 1x     artboard size (1080 x 1350 stays 1080 x 1350)

resolution applies to px artboards in `da export` (png/jpg/webp/psd, the screen pdf) and to the bitmaps placed in
Affinity documents. The Affinity document itself stays at the artboard size (vector; scale it on export there).
Print artboards (mm/in) keep their dpi.
"""
from __future__ import annotations

from .project import memory_dir, read_json, write_json

DEFAULTS = {"resolution": "1x"}
RESOLUTIONS = {"1x": None, "max": 3840, "2k": 2560, "4k": 3840, "8k": 7680}  # long side in px
MAX_UPSCALE = 1.25  # photos: beyond this a bigger file only shows the blur


def path():
    return memory_dir() / "settings.json"


def load() -> dict:
    return {**DEFAULTS, **(read_json(path()) or {})}


def save(key: str, value: str) -> dict:
    if key == "resolution" and value.lower() not in RESOLUTIONS:
        raise SystemExit(f"resolution: one of {', '.join(RESOLUTIONS)}")
    data = read_json(path()) or {}
    data[key] = value.lower() if key == "resolution" else value
    path().parent.mkdir(parents=True, exist_ok=True)
    write_json(path(), data)
    return {**DEFAULTS, **data}


def scale_for(ab: dict, ctx=None) -> float:
    """Raster multiplier for an artboard under the resolution setting (1.0 for print artboards)."""
    if ab.get("unit", "px") != "px":
        return 1.0
    res = str(load().get("resolution", "1x")).lower()
    long_side = RESOLUTIONS.get(res)
    if not long_side:
        return 1.0
    k = max(1.0, long_side / max(float(ab["width"]), float(ab["height"])))
    if res == "max" and ctx is not None:
        k = min(k, max(1.0, _photo_limit(ab, ctx)))
    return k


def _photo_limit(ab: dict, ctx) -> float:
    """Largest scale at which no raster image layer is upscaled more than MAX_UPSCALE."""
    from PIL import Image

    from .design import walk

    limit = float("inf")
    for l, _, _ in walk(ab.get("layers", [])):
        if l["type"] != "image" or l.get("hidden") or str(l.get("src", "")).lower().endswith(".svg"):
            continue
        try:
            with Image.open(ctx.src(l["src"])) as im:
                sw, sh = im.size
        except (OSError, SystemExit):
            continue
        bw, bh = float(l.get("w") or 0), float(l.get("h") or 0)
        if not (bw and bh):
            continue
        fit = l.get("fit", "cover")
        need = min(bw / sw, bh / sh) if fit == "contain" else max(bw / sw, bh / sh)  # source px per box px
        limit = min(limit, MAX_UPSCALE / need)
    return limit


def register(sub) -> None:
    p = sub.add_parser("settings", help="user settings the tools obey (resolution: max | 1x | 2k | 4k | 8k)")
    p.add_argument("action", nargs="?", choices=["show", "set"], default="show")
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")

    def run(a):
        if a.action == "set":
            if not (a.key and a.value):
                raise SystemExit("da settings set <key> <value>")
            data = save(a.key, a.value)
        else:
            data = load()
        return {"settings": data, "file": str(path())}

    p.set_defaults(func=run)
