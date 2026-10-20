"""Raster output: artboard -> PNG (resvg), contact sheets the agent looks at, JPG/WebP derivatives."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import design as D
from . import svg as S
from .project import ROOT, Project

LABEL_FONT = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"


def svg_to_png_bytes(svg: str, resources_dir: Path) -> bytes:
    import resvg_py

    # text is already outlined, so the system font database (slow to load) is never needed
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, resources_dir=str(resources_dir), skip_system_fonts=True))


def svg_to_image(svg: str, resources_dir: Path) -> Image.Image:
    return Image.open(io.BytesIO(svg_to_png_bytes(svg, resources_dir))).convert("RGBA")


def render_artboard(ctx: D.Context, ab: dict, scale: float = 1.0, bleed: bool = False,
                    only: list[str] | None = None, background: bool = True) -> tuple[Image.Image, S.Report]:
    svg, rep = S.artboard_svg(ctx, ab, "preview", scale, bleed, only, background)
    return svg_to_image(svg, ctx.project.dir), rep


def render(project: Project, artboards: list[str] | None = None, scale: float = 1.0, out_dir: Path | None = None,
           sheet: bool = True, bleed: bool = False) -> dict:
    d = D.load(project)
    ctx = D.context(project, d)
    check = D.validate(d, ctx)
    if check["errors"]:
        raise SystemExit("design.json has errors:\n  " + "\n  ".join(check["errors"]))
    out_dir = out_dir or project.path("output", "preview")
    out_dir.mkdir(parents=True, exist_ok=True)
    results, files = [], []
    for ab in d["artboards"]:
        if artboards and ab["id"] not in artboards:
            continue
        im, rep = render_artboard(ctx, ab, scale, bleed)
        f = out_dir / f"{ab['id']}.png"
        im.convert("RGB").save(f) if ab.get("background") not in (None, "none") else im.save(f)
        files.append(f)
        problems = [f"{lid}: text overflows its box" for lid, t in rep.texts.items() if t["overflow"]]
        problems += [f"{lid}: missing glyphs {''.join(t['missing_glyphs'])}" for lid, t in rep.texts.items() if t["missing_glyphs"]]
        problems += [f"{lid}: font not found ({', '.join(t['fallback_fonts'])}), used Montserrat" for lid, t in rep.texts.items()
                     if t["fallback_fonts"]]
        results.append({"artboard": ab["id"], "file": project.rel(f), "px": list(im.size),
                        "problems": problems + rep.warnings})
    if not results:
        raise SystemExit(f"no artboard matched {artboards}")
    res: dict = {"rendered": results}
    if sheet and len(files) > 1:
        res["sheet"] = project.rel(contact_sheet(files, project.path("work", "preview", "sheet.jpg")))
    if ctx.warnings:
        res["warnings"] = ctx.warnings
    return res


def contact_sheet(files: list[Path], out: Path, cell: int = 520, cols: int | None = None, labels: bool = True) -> Path:
    """Grid of images (fit into cell x cell) with file-stem labels, for the model to look at."""
    ims = [Image.open(f).convert("RGB") for f in files]
    cols = cols or min(len(ims), 4 if len(ims) > 6 else 3)
    rows = -(-len(ims) // cols)
    pad, lab = 24, (34 if labels else 0)
    W = cols * cell + (cols + 1) * pad
    H = rows * (cell + lab) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (236, 236, 236))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(LABEL_FONT), 20)
    for i, (im, f) in enumerate(zip(ims, files)):
        r, c = divmod(i, cols)
        im.thumbnail((cell, cell), Image.LANCZOS)
        x0 = pad + c * (cell + pad) + (cell - im.width) // 2
        y0 = pad + r * (cell + lab + pad) + (cell - im.height) // 2
        sheet.paste(im, (x0, y0))
        draw.rectangle((x0 - 1, y0 - 1, x0 + im.width, y0 + im.height), outline=(200, 200, 200))
        if labels:
            draw.text((pad + c * (cell + pad), pad + r * (cell + lab + pad) + cell + 6), Path(f).stem, fill=(40, 40, 40), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out
