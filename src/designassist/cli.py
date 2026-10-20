"""`da`: the command line the AI designer drives. Every command prints JSON or short text so the
model can read results directly. Run `da <command> -h` for options.

Commands live next to their code: any module in this package that defines `register(sub)` adds
its own subcommands (each parser sets `func`, which returns what to print). Keep heavy imports
inside the functions so `da` starts fast.
"""
from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from pathlib import Path

from . import design as D
from .project import Project, write_json


def out(obj) -> None:
    if obj is None:
        return
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str) if not isinstance(obj, str) else obj)


# --- core commands -------------------------------------------------------------------------

def cmd_new(a):
    from . import brand

    client = brand.client_slug(a.client) if a.client else None
    pr = Project.create(a.name, client=a.client, purpose=a.purpose)
    res: dict = {"project": str(pr.dir), "input": str(pr.path("input"))}
    if client:
        res["client"] = brand.create(a.client)
    dpath = D.path(pr)
    if not dpath.exists():
        d = D.empty(a.name, client)
        for i, p in enumerate(a.preset or []):
            d["artboards"].append(D.new_artboard(p, p if (a.preset or []).count(p) == 1 else f"{p}-{i + 1}"))
        D.save(pr, d)
        res["design"] = str(dpath)
        res["artboards"] = [ab["id"] for ab in d["artboards"]]
    res["next"] = "drop assets (photos, logos, brief) into input/, then build design.json"
    return res


def cmd_presets(a):
    from . import presets

    return [{"preset": p["preset"], "size": f"{p['width']}x{p['height']} {p['unit']}", "label": p["label"]}
            for p in presets.listing(a.kind)]


def cmd_info(a):
    pr = Project(a.project)
    d = D.load(pr)
    ctx = D.context(pr, d)
    abs_ = []
    for ab in d.get("artboards", []):
        layers = list(D.walk(ab.get("layers", []), include_hidden=True))
        abs_.append({"id": ab["id"], "size": f"{ab['width']}x{ab['height']} {ab.get('unit', 'px')}",
                     "preset": ab.get("preset"), "layers": [f"{l.get('id')} ({l.get('type')})" for l, _, _ in layers]})
    return {"project": pr.name, "settings": pr.settings, "brand": d.get("brand"), "tokens": {
        "colors": {k: (v if isinstance(v, str) else v.get("hex")) for k, v in ctx.colors.items()},
        "fonts": ctx.fonts}, "artboards": abs_, "inputs": [pr.rel(p) for p in pr.input_files()],
        "warnings": ctx.warnings}


def cmd_validate(a):
    pr = Project(a.project)
    d = D.load(pr)
    res = D.validate(d, D.context(pr, d))
    res["ok"] = not res["errors"]
    return res


def cmd_render(a):
    from . import render

    pr = Project(a.project)
    return render.render(pr, a.artboard, a.scale, Path(a.out) if a.out else None, not a.no_sheet, a.bleed)


def cmd_layout(a):
    """Text metrics of one text layer: lines, final size after autofit, overflow."""
    from . import text as T

    pr = Project(a.project)
    d = D.load(pr)
    ctx = D.context(pr, d)
    ab = D.artboard(d, a.artboard)
    hits = [(l, ox, oy) for l, ox, oy in D.walk(ab["layers"], include_hidden=True) if l.get("id") == a.layer]
    if not hits:
        raise SystemExit(f"no layer {a.layer} in {ab['id']}")
    l, ox, oy = hits[0]
    if l["type"] != "text":
        raise SystemExit(f"{a.layer} is a {l['type']} layer, not text")
    return T.layout(l, ctx, ab.get("unit", "px"), float(ab.get("dpi", 72)), ox, oy).to_json()


def cmd_artboard(a):
    pr = Project(a.project)
    d = D.load(pr)
    if a.action == "add":
        ab_id = a.id or (a.preset or "artboard")
        if any(x["id"] == ab_id for x in d["artboards"]):
            raise SystemExit(f"artboard {ab_id} exists; pass --id")
        ab = D.new_artboard(a.preset, ab_id, a.width, a.height, a.unit)
        d["artboards"].append(ab)
    elif a.action == "duplicate":
        import copy

        src = D.artboard(d, a.source)
        ab = copy.deepcopy(src)
        ab["id"] = a.id or f"{src['id']}-copy"
        d["artboards"].insert(d["artboards"].index(src) + 1, ab)
    elif a.action == "remove":
        ab = D.artboard(d, a.source)
        d["artboards"].remove(ab)
    else:
        raise SystemExit(a.action)
    D.save(pr, d)
    return {"artboards": [x["id"] for x in d["artboards"]]}


def cmd_version(a):
    """Snapshots of design.json in work/versions/ so feedback rounds can be compared or undone."""
    import shutil
    from datetime import datetime

    pr = Project(a.project)
    vdir = pr.path("work", "versions")
    if a.action == "save":
        vdir.mkdir(parents=True, exist_ok=True)
        n = len(list(vdir.glob("v*.json"))) + 1
        name = f"v{n}" + (f"-{a.label}" if a.label else "")
        shutil.copy2(D.path(pr), vdir / f"{name}.json")
        return {"saved": name}
    if a.action == "list":
        return [{"version": p.stem, "saved": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")}
                for p in sorted(vdir.glob("v*.json"), key=lambda p: p.stat().st_mtime)]
    if a.action == "restore":
        hits = [p for p in vdir.glob("v*.json") if p.stem == a.label or p.stem.split("-")[0] == a.label]
        if not hits:
            raise SystemExit(f"no version {a.label}")
        shutil.copy2(hits[0], D.path(pr))
        return {"restored": hits[0].stem}
    raise SystemExit(a.action)


def cmd_selftest(a):
    import subprocess

    from .project import ROOT

    r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")], cwd=ROOT)
    return {"ok": r.returncode == 0}


def core(sub) -> None:
    p = sub.add_parser("new", help="create a project (and its client brand kit)")
    p.add_argument("name")
    p.add_argument("--client", help="client name: preferences + brand kit in the private memory")
    p.add_argument("--purpose", choices=["social", "identity", "web", "print"])
    p.add_argument("--preset", nargs="*", help="artboards to start with, e.g. ig-post ig-story")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("presets", help="canvas presets (social, print, web, identity)")
    p.add_argument("--kind", choices=["social", "print", "web", "identity"])
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("info", help="artboards, layers, tokens and inputs of a project")
    p.add_argument("project")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("validate", help="check design.json")
    p.add_argument("project")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("render", help="preview PNGs (output/preview/) + contact sheet")
    p.add_argument("project")
    p.add_argument("--artboard", nargs="*")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--out", help="folder (default output/preview)")
    p.add_argument("--bleed", action="store_true", help="include the print bleed")
    p.add_argument("--no-sheet", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("layout", help="text metrics of one text layer (lines, fitted size, overflow)")
    p.add_argument("project")
    p.add_argument("artboard")
    p.add_argument("layer")
    p.set_defaults(func=cmd_layout)

    p = sub.add_parser("artboard", help="add / duplicate / remove artboards")
    p.add_argument("project")
    p.add_argument("action", choices=["add", "duplicate", "remove"])
    p.add_argument("source", nargs="?", help="artboard to duplicate/remove")
    p.add_argument("--preset")
    p.add_argument("--id")
    p.add_argument("--width", type=float)
    p.add_argument("--height", type=float)
    p.add_argument("--unit", choices=list(D.UNITS_PER_INCH))
    p.set_defaults(func=cmd_artboard)

    p = sub.add_parser("version", help="save / list / restore snapshots of design.json")
    p.add_argument("project")
    p.add_argument("action", choices=["save", "list", "restore"])
    p.add_argument("label", nargs="?")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("selftest", help="run the test suite")
    p.set_defaults(func=cmd_selftest)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="da", description="designassist: the design tools the AI designer drives")
    sub = ap.add_subparsers(dest="cmd", required=True)
    core(sub)
    pkg = Path(__file__).parent
    for m in sorted(pkgutil.iter_modules([str(pkg)]), key=lambda m: m.name):
        if m.name == "cli":
            continue
        src = pkg / f"{m.name}.py"
        if src.exists() and "\ndef register(" in src.read_text(encoding="utf-8"):
            importlib.import_module(f"{__package__}.{m.name}").register(sub)
    return ap


def main(argv: list[str] | None = None) -> None:
    for s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    a = build_parser().parse_args(argv)
    out(a.func(a))


if __name__ == "__main__":
    main()
