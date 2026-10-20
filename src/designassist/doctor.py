"""doctor: one command that tells a new user what is missing."""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .project import ROOT, memory_dir


def adobe_apps() -> dict[str, str | None]:
    """{'illustrator': path or None, 'photoshop': path or None} — newest install wins."""
    found: dict[str, str | None] = {"illustrator": None, "photoshop": None}
    if sys.platform == "darwin":
        roots = [Path("/Applications")]
    elif os.name == "nt":
        roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Adobe"]
    else:
        roots = []
    for app, prefix in (("illustrator", "Adobe Illustrator"), ("photoshop", "Adobe Photoshop")):
        hits = []
        for r in roots:
            if r.is_dir():
                hits += [p for p in r.iterdir() if p.name.startswith(prefix)]
        if hits:
            found[app] = str(sorted(hits)[-1])
    return found


def _playwright_browsers() -> list[Path]:
    pw = {"darwin": Path.home() / "Library/Caches/ms-playwright",
          "win32": Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"}.get(sys.platform, Path.home() / ".cache/ms-playwright")
    if not pw.is_dir():
        return []
    names = ("chrome-headless-shell", "chrome-headless-shell.exe", "chrome", "chrome.exe", "Chromium")
    return [p for p in sorted(pw.rglob("*"), reverse=True) if p.is_file() and p.name in names and os.access(p, os.X_OK)]


def find_browser() -> str | None:
    """A Chromium-family browser able to run headless (for `da web`). Brave comes last: its headless
    mode hung without output on macOS (2026-10-17), Chrome/Edge/Chromium/Playwright's shell work."""
    env = os.environ.get("DA_BROWSER")
    if env and Path(env).exists():
        return env
    first: list[Path] = []
    last: list[Path] = []
    if sys.platform == "darwin":
        for app in ("Google Chrome", "Chromium", "Microsoft Edge", "Google Chrome Canary"):
            for base in (Path("/Applications"), Path.home() / "Applications"):
                first.append(base / f"{app}.app" / "Contents" / "MacOS" / app)
        last = [Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")]
    elif os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            b = Path(base)
            first += [b / "Google/Chrome/Application/chrome.exe", b / "Microsoft/Edge/Application/msedge.exe",
                      b / "Chromium/Application/chrome.exe"]
            last.append(b / "BraveSoftware/Brave-Browser/Application/brave.exe")
    for c in first:
        if c.exists():
            return str(c)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    for p in _playwright_browsers():
        return str(p)
    for c in last + [Path(p) for p in (shutil.which("brave-browser"),) if p]:
        if c.exists():
            return str(c)
    return None


def checks() -> tuple[bool, list[dict]]:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    ok = True
    rows: list[dict] = []

    def row(name, good, detail, required=True):
        nonlocal ok
        ok &= bool(good) or not required
        rows.append({"name": name, "ok": bool(good), "required": required, "detail": detail})

    row("python", sys.version_info >= (3, 11), platform.python_version())
    for mod, label in (("resvg_py", "resvg (render)"), ("uharfbuzz", "harfbuzz (text shaping)"), ("fontTools", "fonttools"),
                       ("reportlab", "reportlab (PDF)"), ("psd_tools", "psd-tools (PSD)"), ("vtracer", "vtracer (vectorize)"),
                       ("cv2", "opencv (faces)"), ("PIL", "pillow"), ("numpy", "numpy")):
        try:
            m = importlib.import_module(mod)
            row(label, True, getattr(m, "__version__", "installed"))
        except Exception as e:  # noqa: BLE001
            row(label, False, f"{e.__class__.__name__}: {e} (`uv sync`)")
    bundled = sorted(p.name for p in (ROOT / "assets" / "fonts").glob("*.[ot]tf"))
    row("bundled fonts", bool(bundled), f"{len(bundled)} files in assets/fonts")
    try:
        from . import fonts as F

        fams = F.families()
        row("font index", bool(fams), f"{len(fams)} families (bundled + user + system)")
    except Exception as e:  # noqa: BLE001
        row("font index", False, str(e))
    b = find_browser()
    row("headless browser", bool(b), b or "missing: `da web` (UI/landing screenshots) needs Chrome, Edge, Brave or Chromium",
        required=False)
    apps = adobe_apps()
    row("Adobe Illustrator", bool(apps["illustrator"]), apps["illustrator"] or "not found: .jsx/.svg exports still work, open them elsewhere",
        required=False)
    row("Adobe Photoshop", bool(apps["photoshop"]), apps["photoshop"] or "not found: layered .psd exports still work (Affinity/Photopea open them)",
        required=False)
    from . import affinity as A

    aff = A.installed()
    row("Affinity", bool(aff), aff or "not found (affinity.studio, free): native editable documents via `da affinity open`",
        required=False)
    if aff:
        row("Affinity AI connector", A.reachable(), "on: `da affinity open` builds live" if A.reachable()
            else "off: in Affinity, Settings > AI connector (re-enable after restarting Affinity)", required=False)
    from .colors import cmyk_profile

    prof = cmyk_profile()
    row("CMYK profile", bool(prof), str(prof) if prof else "none: print PDFs use a plain RGB->CMYK formula (set DA_CMYK_ICC)",
        required=False)
    node = shutil.which("node")
    row("node", bool(node), subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip() if node
        else "optional: only the Adobe-script tests use it", required=False)
    mem = memory_dir()
    on_os = (Path.home() / ".memory-os" / "memory") in mem.parents
    row("memory-os", (Path.home() / ".memory-os" / "CLAUDE.md").exists(), "~/.memory-os (`uv run da memory --install`)",
        required=False)
    row("design memory", (mem / "preferences.md").exists(),
        f"{'memory-os global tier' if on_os else 'local fallback'}: {mem} (`uv run da memory --init`)")
    row("project memory", (ROOT / ".claude" / "_memory" / "_index.md").exists(), ".claude/_memory/ (memory-os project tier)",
        required=False)
    hf = bool(os.environ.get("HF_API_KEY_ID") and os.environ.get("HF_API_KEY_SECRET"))
    row("HF_API_KEY_ID/SECRET", hf, "Higgsfield generated images", required=False)
    for k, why in (("PEXELS_API_KEY", "stock photos (Pexels)"), ("UNSPLASH_ACCESS_KEY", "stock photos (Unsplash)")):
        row(k, bool(os.environ.get(k)), why, required=False)
    try:
        importlib.import_module("rembg")
        row("bg extra", True, "background removal", required=False)
    except Exception:  # noqa: BLE001
        row("bg extra", False, "optional: `uv sync --extra bg` for background removal", required=False)
    return ok, rows


def cmd_doctor(a):
    ok, rows = checks()
    if a.json:
        return {"ready": ok, "os": platform.system(), "arch": platform.machine(), "checks": rows}
    lines = [f"designassist doctor ({platform.system()} {platform.machine()})"]
    lines += [f"  [{'ok' if r['ok'] else ('!!' if r['required'] else '--')}] {r['name']}: {r['detail']}" for r in rows]
    lines.append("ready" if ok else "missing required pieces: run setup again")
    print("\n".join(lines))
    if not ok:
        raise SystemExit(1)
    return None


def register(sub) -> None:
    p = sub.add_parser("doctor", help="what is installed and what is missing")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)
