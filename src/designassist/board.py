"""`da board`: a moodboard from reference images — masonry grid, the combined palette with hex
codes, optional title and notes. work/board/<name>.jpg is a small copy to LOOK at;
output/<name>.jpg is the full-size board for the client. <name> = "board" or, with a title,
"board-<title slug>", so several boards in one project don't overwrite each other."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .project import ROOT, Project

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
BOLD = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
REGULAR = ROOT / "assets" / "fonts" / "Montserrat-VariableFont_wght.ttf"


def gather(project: Project, items: list[str]) -> list[Path]:
    files: list[Path] = []
    for it in items:
        p = project.abs(it) if project.abs(it).exists() else Path(it).expanduser()
        if p.is_dir():
            files += sorted(q for q in p.rglob("*") if q.suffix.lower() in IMG_EXT and q.is_file())
        elif p.is_file() and p.suffix.lower() in IMG_EXT:
            files.append(p)
        else:
            raise SystemExit(f"not an image or folder: {it}")
    if not files:
        raise SystemExit("no reference images found")
    return files


def board(project: Project, items: list[str], title: str | None = None, notes: str | None = None,
          cols: int | None = None, width: int = 2400, n_colors: int = 6) -> dict:
    from . import images as I
    from .colortools import palette

    files = gather(project, items)
    cols = cols or (2 if len(files) <= 3 else 3 if len(files) <= 9 else 4)
    pad, gutter = 80, 24
    colw = (width - 2 * pad - (cols - 1) * gutter) // cols
    ims = []
    for f in files:
        im = I.open_image(f).convert("RGB")
        ims.append(im.resize((colw, max(1, round(colw * im.height / im.width))), Image.LANCZOS))
    heights = [0] * cols
    places = []
    for im in ims:
        c = heights.index(min(heights))
        places.append((c, heights[c], im))
        heights[c] += im.height + gutter
    grid_h = max(heights) - gutter
    head = 0
    if title:
        head = 150
    tf = ImageFont.truetype(str(BOLD), 64)
    nf = ImageFont.truetype(str(REGULAR), 30)
    try:
        nf.set_variation_by_axes([450])  # the variable file defaults to its thinnest weight
    except Exception:
        pass
    lab = ImageFont.truetype(str(BOLD), 26)
    note_lines = textwrap.wrap(notes, 110) if notes else []
    # palette from a mosaic of all references
    mosaic = Image.new("RGBA", (cols * 120, (len(ims) // cols + 1) * 120), (0, 0, 0, 0))  # empty = ignored
    for i, im in enumerate(ims):
        t = im.copy()
        t.thumbnail((120, 120))
        mosaic.paste(t, ((i % cols) * 120, (i // cols) * 120))
    mosaic = mosaic.crop((0, 0, cols * 120, ((len(ims) - 1) // cols + 1) * 120))
    mp = project.path("work", "board", "_mosaic.png")
    mp.parent.mkdir(parents=True, exist_ok=True)
    mosaic.save(mp)
    pal = palette(mp, n_colors)
    mp.unlink(missing_ok=True)
    sw_h = 170
    H = pad + head + grid_h + 60 + sw_h + 50 + len(note_lines) * 44 + pad
    out = Image.new("RGB", (width, H), (247, 246, 243))
    d = ImageDraw.Draw(out)
    if title:
        d.text((pad, pad), title, fill=(20, 20, 20), font=tf)
    for c, y, im in places:
        out.paste(im, (pad + c * (colw + gutter), pad + head + y))
    y0 = pad + head + grid_h + 60
    sw = (width - 2 * pad - (len(pal) - 1) * gutter) // max(1, len(pal))
    for i, e in enumerate(pal):
        x = pad + i * (sw + gutter)
        d.rectangle((x, y0, x + sw, y0 + sw_h - 50), fill=e["hex"])
        d.text((x, y0 + sw_h - 40), f"{e['hex']}  {round(e['share'] * 100)}%", fill=(40, 40, 40), font=lab)
    yn = y0 + sw_h + 30
    for ln in note_lines:
        d.text((pad, yn), ln, fill=(60, 60, 60), font=nf)
        yn += 44
    name = "board" + (f"-{_slug(title)}" if title and _slug(title) else "")
    full = project.path("output", f"{name}.jpg")
    full.parent.mkdir(parents=True, exist_ok=True)
    out.save(full, quality=90)
    small = out.copy()
    small.thumbnail((1400, 1400 * 4), Image.LANCZOS)
    look = project.path("work", "board", f"{name}.jpg")
    small.save(look, quality=85)
    return {"look": project.rel(look), "file": project.rel(full), "images": len(files), "px": list(out.size),
            "palette": [{k: e[k] for k in ("hex", "share", "role")} for e in pal]}


def _slug(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]


def cmd_board(a):
    return board(Project(a.project), a.items, a.title, a.notes, a.cols)


def register(sub) -> None:
    p = sub.add_parser("board", help="moodboard from reference images: grid + palette (+ title, notes)")
    p.add_argument("project")
    p.add_argument("items", nargs="+", help="image files or folders (project-relative or absolute)")
    p.add_argument("--title")
    p.add_argument("--notes")
    p.add_argument("--cols", type=int)
    p.set_defaults(func=cmd_board)
