"""Deliverables: `da export` (one or more formats) and `da package` (handoff folder + spec sheet).

Targets and where they land (relative to the project):
  png            output/<artboard>.png at the resolution setting (`da settings`: max = as big as stays sharp);
                 output/<artboard>@2x.png with an explicit --scale 2
  jpg / webp     output/<artboard>.jpg / .webp (alpha flattened on white)
  svg            output/<artboard>.svg            live <text>, images embedded (Illustrator, Inkscape, Affinity)
  svg-outlined   output/<artboard>-outlined.svg   text as outlines, self-contained (Canva, web, print shops)
  pdf            output/<project>.pdf             RGB, one page per artboard (carousels, proofs, Canva import)
  print          output/print/<artboard>-print.pdf  CMYK + bleed + crop marks, preflight report
  psd            output/<artboard>.psd            layered pixels (any app that reads PSD)
  illustrator    script that builds the artboards in Illustrator with live text (adobe.py)
  photoshop      script that builds the document in Photoshop with live text layers (adobe.py)
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import design as D
from .project import ROOT, Project

TARGETS = ["png", "jpg", "webp", "svg", "svg-outlined", "pdf", "print", "psd", "affinity", "illustrator", "photoshop"]
PURPOSE_TARGETS = {
    "social": ["png", "jpg", "pdf"],
    "identity": ["svg", "svg-outlined", "png", "pdf"],
    "web": ["png", "svg-outlined"],
    "print": ["print", "pdf", "png"],
}


def _suffix(scale: float) -> str:
    return "" if scale == 1 else f"@{scale:g}x"


def _raster(project, ctx, ab, fmt: str, scale: float, quality: int, out_dir: Path, suffix: str | None = None) -> dict:
    from PIL import Image

    from .render import render_artboard

    im, rep = render_artboard(ctx, ab, scale)
    f = out_dir / f"{ab['id']}{_suffix(scale) if suffix is None else suffix}.{fmt}"
    f.parent.mkdir(parents=True, exist_ok=True)
    opaque = ab.get("background") not in (None, "none")
    if fmt == "png":
        (im.convert("RGB") if opaque else im).save(f, optimize=True)
    else:
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.getchannel("A"))
        if fmt == "jpg":
            flat.save(f, quality=quality, optimize=True, progressive=True, subsampling=0 if quality >= 90 else 2)
        else:
            (flat if opaque else im).save(f, "WEBP", quality=quality, method=6)
    res = {"artboard": ab["id"], "file": project.rel(f), "px": list(im.size)}
    over = [lid for lid, t in rep.texts.items() if t["overflow"]]
    if over:
        res["warnings"] = [f"text overflows: {', '.join(over)}"]
    return res


def _svg(project, ctx, ab, mode: str, out_dir: Path) -> dict:
    from .svg import artboard_svg

    s, rep = artboard_svg(ctx, ab, mode)
    name = f"{ab['id']}.svg" if mode == "editable" else f"{ab['id']}-outlined.svg"
    f = out_dir / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + s, encoding="utf-8")
    res = {"artboard": ab["id"], "file": project.rel(f)}
    if mode == "editable":
        missing = sorted({r.family for r in rep.fonts if not r.installed})
        res["note"] = "live text: the fonts must be installed where it's opened"
        if missing:
            res["warnings"] = [f"not installed on this machine: {', '.join(missing)} (`da fonts install`)"]
    return res


def export(project: Project, targets: list[str], artboards: list[str] | None = None, scale: float | None = None,
           quality: int = 90, out: Path | None = None) -> dict:
    """scale None = the user's resolution setting (`da settings`: max / 4k = long side up to 3840 px), files named plainly;
    an explicit scale names them @Nx."""
    d = D.load(project)
    ctx = D.context(project, d)
    check = D.validate(d, ctx)
    if check["errors"]:
        raise SystemExit("design.json has errors:\n  " + "\n  ".join(check["errors"]))
    abs_ = [ab for ab in d["artboards"] if not artboards or ab["id"] in artboards]
    if not abs_:
        raise SystemExit(f"no artboard matched {artboards}")
    out_dir = out or project.path("output")
    results: dict = {}
    from . import settings as ST

    # one scale per artboard size: slides of a carousel come out the same pixel size even when `max` would let
    # one go higher than another (the set is capped by its most limiting photo)
    by_size: dict = {}
    for ab in abs_:
        key = (ab.get("unit", "px"), float(ab["width"]), float(ab["height"]))
        by_size[key] = min(by_size.get(key, float("inf")), ST.scale_for(ab, ctx))

    def sc(ab) -> float:
        if scale is not None:
            return float(scale)
        return by_size[(ab.get("unit", "px"), float(ab["width"]), float(ab["height"]))]

    def suffix() -> str:
        return _suffix(float(scale)) if scale is not None else ""
    for t in targets:
        if t in ("png", "jpg", "webp"):
            results[t] = [_raster(project, ctx, ab, t, sc(ab), quality, out_dir, suffix()) for ab in abs_]
        elif t in ("svg", "svg-outlined"):
            results[t] = [_svg(project, ctx, ab, "editable" if t == "svg" else "outlined", out_dir) for ab in abs_]
        elif t == "pdf":
            from . import pdf

            results[t] = pdf.write(project, out_dir / f"{project.name}.pdf", abs_, "screen", max([2.0] + [sc(ab) for ab in abs_]))
        elif t == "print":
            from . import pdf

            todo = abs_
            if not artboards and any(ab.get("unit", "px") != "px" for ab in abs_):
                # a mixed project (feed post + business card): only the print-sized artboards go to the shop
                todo = [ab for ab in abs_ if ab.get("unit", "px") != "px"]
            results[t] = [pdf.write(project, out_dir / "print" / f"{ab['id']}-print.pdf", [ab], "print")
                          for ab in todo]
        elif t == "psd":
            from . import psd

            results[t] = [psd.write(project, ab["id"], out_dir / f"{ab['id']}{suffix()}.psd", sc(ab)) for ab in abs_]
        elif t == "affinity":
            from . import affinity as A
            from . import affinity_build as AB

            ids = [ab["id"] for ab in abs_] if artboards else None
            if A.reachable():
                results[t] = AB.build(project, ids, live=True)
            else:
                results[t] = AB.build(project, ids, live=False)
                results[t]["note"] = A.NOT_RUNNING
        elif t in ("illustrator", "photoshop"):
            try:
                from .adobe import write_script
            except ImportError:
                results[t] = {"error": "adobe exporter not available"}
                continue
            results[t] = write_script(project, t, [ab["id"] for ab in abs_] if artboards else None)
        else:
            raise SystemExit(f"unknown target {t} (one of {', '.join(TARGETS)})")
    if ctx.warnings:
        results["warnings"] = ctx.warnings
    return results


# --- package -----------------------------------------------------------------------------------

def _purpose(project: Project, d: dict) -> str:
    p = project.settings.get("purpose")
    if p in PURPOSE_TARGETS:
        return p
    from . import presets

    kinds = [presets.PRESETS.get(ab.get("preset", ""), {}).get("kind") for ab in d["artboards"]]
    if any(ab.get("unit", "px") != "px" for ab in d["artboards"]) or "print" in kinds:
        return "print"
    for k in ("identity", "web", "social"):
        if k in kinds:
            return k
    return "social"


def _used_colors(d: dict, ctx) -> list[tuple[str, object]]:
    """Token names referenced anywhere in the design (in token order), then literal hex colours."""
    import json
    import re

    from . import colors as C

    blob = json.dumps(d["artboards"], ensure_ascii=False)
    used = []
    for name in ctx.colors:
        if re.search(r'"\$' + re.escape(name) + r'(?:/\d+)?"', blob):
            used.append((f"${name}", ctx.color(f"${name}")))
    for hx in sorted(set(re.findall(r'"(#[0-9A-Fa-f]{6})(?:[0-9A-Fa-f]{2})?(?:/\d+)?"', blob))):
        used.append((hx.upper(), C.parse(hx)))
    return [(n, c) for n, c in used if c is not None]


def _fonts_used(d: dict, ctx) -> list:
    from . import text as T

    refs = {}
    for ab in d["artboards"]:
        for l, ox, oy in D.walk(ab.get("layers", [])):
            if l.get("type") == "text":
                for r in T.layout(l, ctx, ab.get("unit", "px"), float(ab.get("dpi", 72))).fonts:
                    refs[(r.family, r.weight, r.italic)] = r
    return [refs[k] for k in sorted(refs)]


def _font_source(ref) -> str:
    p = Path(ref.path)
    if ROOT / "assets" / "fonts" in p.parents or (ROOT / "assets" / "user-fonts" / "google") in p.parents:
        return "free (SIL OFL), https://fonts.google.com/specimen/" + ref.family.replace(" ", "+")
    if ref.installed:
        return "installed on the designer's machine; licensed font, get it from the foundry or the client"
    return "client-supplied font file (brand kit); not redistributable unless the licence says so"


def readme(project: Project, d: dict, ctx, targets: list[str], files: list[str]) -> str:
    from . import colors as C

    lines = [f"{d.get('name', project.name)} — design handoff", "=" * 40, ""]
    lines.append("ARTBOARDS")
    for ab in d["artboards"]:
        unit = ab.get("unit", "px")
        ppu = D.px_per_unit(ab)
        px = f"{round(ab['width'] * ppu)}x{round(ab['height'] * ppu)} px"
        size = f"{ab['width']:g} x {ab['height']:g} {unit}" + ("" if unit == "px" else f" ({px} at {ab.get('dpi')} dpi)")
        bleed = f", bleed {ab.get('bleed'):g} {unit}" if ab.get("bleed") else ""
        lines.append(f"  {ab['id']}: {size}{bleed}" + (f"  [{ab['preset']}]" if ab.get("preset") else ""))
    lines += ["", "COLOURS"]
    for name, c in _used_colors(d, ctx):
        cm = C.to_cmyk(c)
        authored = " (authored)" if c.cmyk else ""
        extra = ""
        tok = ctx.colors.get(name[1:]) if name.startswith("$") else None
        if isinstance(tok, dict) and tok.get("pantone"):
            extra = f"  Pantone {tok['pantone']}"
        lines.append(f"  {name:<14} HEX {c.hex}  RGB {c.r},{c.g},{c.b}  CMYK {'/'.join(f'{v:g}' for v in cm)}{authored}{extra}")
    lines += ["", "FONTS"]
    for r in _fonts_used(d, ctx):
        lines.append(f"  {r.family} {r.weight}{' italic' if r.italic else ''} ({r.postscript}) — {_font_source(r)}")
    lines += ["", "FILES"] + [f"  {f}" for f in files]
    lines += ["", f"Formats: {', '.join(targets)}.", "Made with designassist."]
    return "\n".join(lines) + "\n"


def package(project: Project, zip_: bool = False, targets: list[str] | None = None) -> dict:
    d = D.load(project)
    ctx = D.context(project, d)
    purpose = _purpose(project, d)
    targets = targets or PURPOSE_TARGETS[purpose]
    pkg = project.path("output", "package")
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    from . import settings as ST

    # the resolution setting rules (4k...); with none set, web/identity files still go out @2x
    hi = ST.load().get("resolution", "1x") != "1x"
    res = export(project, targets, out=pkg, scale=None if hi else (2.0 if purpose in ("web", "identity") else 1.0))
    files = sorted(p.relative_to(pkg).as_posix() for p in pkg.rglob("*") if p.is_file())
    (pkg / "README.txt").write_text(readme(project, d, ctx, targets, files), encoding="utf-8")
    out = {"purpose": purpose, "folder": project.rel(pkg), "files": files + ["README.txt"], "exports": res}
    if zip_:
        z = shutil.make_archive(str(project.path("output", f"{project.name}-package")), "zip", pkg)
        out["zip"] = project.rel(Path(z))
    return out


# --- CLI -------------------------------------------------------------------------------------

def cmd_export(a):
    pr = Project(a.project)
    return export(pr, a.to, a.artboard, a.scale, a.quality, pr.abs(a.out) if a.out else None)


def cmd_package(a):
    return package(Project(a.project), a.zip, a.to)


def register(sub) -> None:
    p = sub.add_parser("export", help="deliverables: png jpg webp svg svg-outlined pdf print psd illustrator photoshop")
    p.add_argument("project")
    p.add_argument("--to", nargs="+", required=True, choices=TARGETS)
    p.add_argument("--artboard", nargs="*")
    p.add_argument("--scale", type=float, default=None,
                   help="raster/psd scale (2 = @2x); default: the resolution setting (`da settings`, e.g. 4k)")
    p.add_argument("--quality", type=int, default=90, help="jpg/webp quality")
    p.add_argument("--out", help="folder, project-relative (default output/)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("package", help="handoff folder output/package/ with the formats the purpose needs + README spec")
    p.add_argument("project")
    p.add_argument("--zip", action="store_true")
    p.add_argument("--to", nargs="+", choices=TARGETS, help="override the formats")
    p.set_defaults(func=cmd_package)
