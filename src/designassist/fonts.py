"""Font discovery and matching.

Search order: brand kit fonts, the project's input/, assets/user-fonts/ (gitignored, includes
`da fonts get` downloads), bundled assets/fonts/, DA_FONT_DIRS, then the system font folders.
The index (family, weight, italic, variable axes, PostScript names) is cached in
.cache/fonts/index.json and refreshed when a file changes.

`resolve()` returns a FontRef: the file plus the variable-axis location to use. Rendering
never asks the OS for fonts; it shapes and outlines glyphs itself (text.py), so a design looks
the same on every machine. Photoshop/Illustrator exports need the font INSTALLED (`installed`),
which `da qa` checks.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .project import CACHE, ROOT

BUNDLED = ROOT / "assets" / "fonts"
USER = ROOT / "assets" / "user-fonts"
WEB_EXT = {".woff", ".woff2"}  # web fonts (a client's site): decompressed to a desktop font on first use
FONT_EXT = {".ttf", ".otf", ".ttc"} | WEB_EXT


def desktop_font(path: Path) -> Path:
    """A .woff/.woff2 as a plain .ttf/.otf in .cache/fonts/web/ (same file for every later call), so the
    text engine, resvg and Affinity/Adobe installs can use it. Other fonts are returned as they are."""
    path = Path(path)
    if path.suffix.lower() not in WEB_EXT:
        return path
    import hashlib

    from fontTools.ttLib import TTFont

    key = hashlib.sha1(f"{path.resolve()}|{path.stat().st_mtime_ns}".encode()).hexdigest()[:10]
    out_dir = CACHE / "fonts" / "web"
    for ext in (".otf", ".ttf"):
        hit = out_dir / f"{path.stem}-{key}{ext}"
        if hit.exists():
            return hit
    tt = TTFont(str(path))  # woff2 needs the brotli module (a dependency)
    ext = ".otf" if "CFF " in tt or "CFF2" in tt else ".ttf"
    tt.flavor = None
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{path.stem}-{key}{ext}"
    tt.save(str(out))
    return out
FALLBACK = ("Montserrat", 400)


def system_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental")]
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", "C:/Windows"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return [windir / "Fonts", local / "Microsoft/Windows/Fonts"]
    return [home / ".fonts", home / ".local/share/fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]


def user_install_dir() -> Path:
    """Where `da fonts install` puts fonts so Photoshop/Illustrator see them."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/Fonts"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Microsoft/Windows/Fonts"
    return home / ".local/share/fonts"


@dataclass
class Face:
    path: str
    index: int
    family: str
    style: str
    weight: int
    italic: bool
    postscript: str
    axes: dict = field(default_factory=dict)  # tag -> [min, default, max]
    instances: list = field(default_factory=list)  # [{style, coords, postscript}]
    installed: bool = False  # lives in a system/user font folder (Adobe apps can use it)
    cff: bool = False

    def weights(self) -> tuple[float, float]:
        if "wght" in self.axes:
            return self.axes["wght"][0], self.axes["wght"][2]
        return self.weight, self.weight


@dataclass(frozen=True)
class FontRef:
    path: str
    index: int
    family: str
    weight: int
    italic: bool
    location: tuple = ()  # (("wght", 700.0),) for variable fonts
    postscript: str = ""
    installed: bool = False
    fallback: bool = False  # requested family was missing

    @property
    def loc(self) -> dict:
        return dict(self.location)


def _name(tt, *ids) -> str:
    for i in ids:
        rec = tt["name"].getDebugName(i)
        if rec:
            return rec
    return ""


def _read_faces(path: Path, installed: bool) -> list[Face]:
    from fontTools.ttLib import TTCollection, TTFont

    fonts = []
    try:
        path = desktop_font(path)
        if path.suffix.lower() == ".ttc":
            fonts = list(enumerate(TTCollection(str(path), lazy=True).fonts))
        else:
            fonts = [(0, TTFont(str(path), lazy=True))]
    except Exception:
        return []
    faces = []
    for idx, tt in fonts:
        try:
            if "name" not in tt or "OS/2" not in tt:
                continue
            os2 = tt["OS/2"]
            fam = _name(tt, 16, 1)
            style = _name(tt, 17, 2) or "Regular"
            italic = bool(os2.fsSelection & 1) or "italic" in style.lower() or "oblique" in style.lower()
            axes, instances = {}, []
            if "fvar" in tt:
                for a in tt["fvar"].axes:
                    axes[a.axisTag] = [a.minValue, a.defaultValue, a.maxValue]
                for inst in tt["fvar"].instances:
                    ps = tt["name"].getDebugName(inst.postscriptNameID) if inst.postscriptNameID not in (0xFFFF, None) else None
                    instances.append({"style": tt["name"].getDebugName(inst.subfamilyNameID) or "",
                                      "coords": dict(inst.coordinates), "postscript": ps})
            faces.append(Face(str(path), idx, fam, style, int(os2.usWeightClass), italic, _name(tt, 6),
                              axes, instances, installed, "CFF " in tt or "CFF2" in tt))
        except Exception:
            continue
    return faces


def search_dirs(extra: list[Path] | None = None) -> list[tuple[Path, bool]]:
    dirs: list[tuple[Path, bool]] = [(Path(p), False) for p in (extra or [])]
    dirs += [(USER, False), (BUNDLED, False)]
    for p in os.environ.get("DA_FONT_DIRS", "").split(os.pathsep):
        if p:
            dirs.append((Path(p).expanduser(), False))
    dirs += [(p, True) for p in system_dirs()]
    return dirs


_INDEX: dict[str, list[Face]] = {}


def _index_dir(d: Path, installed: bool) -> list[Face]:
    key = str(d)
    if key in _INDEX:
        return _INDEX[key]
    files = sorted(p for p in d.rglob("*") if p.suffix.lower() in FONT_EXT and p.is_file()) if d.is_dir() else []
    stamp = [[str(p), p.stat().st_mtime_ns] for p in files]
    cache_file = CACHE / "fonts" / "index.json"
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
    entry = cache.get(key)
    if entry and entry.get("stamp") == stamp:
        faces = [Face(**f) for f in entry["faces"]]
    else:
        faces = [f for p in files for f in _read_faces(p, installed)]
        cache[key] = {"stamp": stamp, "faces": [f.__dict__ for f in faces]}
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache), encoding="utf-8")
    _INDEX[key] = faces
    return faces


def all_faces(extra: list[Path] | None = None, system: bool = True) -> list[Face]:
    out = []
    for d, installed in search_dirs(extra):
        if installed and not system:
            continue
        out += _index_dir(d, installed)
    return out


def families(extra: list[Path] | None = None, system: bool = True) -> dict[str, list[Face]]:
    fam: dict[str, list[Face]] = {}
    for f in all_faces(extra, system):
        fam.setdefault(f.family, []).append(f)
    return fam


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _installed_families() -> set[str]:
    return {_norm(f.family) for d, inst in search_dirs() if inst for f in _index_dir(d, inst)}


def _instance_ps(face: Face, weight: float, italic: bool) -> str:
    best = None
    for inst in face.instances:
        w = inst["coords"].get("wght")
        if w is not None and abs(w - weight) < 1 and inst.get("postscript"):
            best = inst["postscript"]
    if best:
        return best
    if face.axes:
        names = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                 700: "Bold", 800: "ExtraBold", 900: "Black"}
        style = names.get(int(round(weight / 100) * 100), "Regular")
        if italic:
            style = "Italic" if style == "Regular" else style + "Italic"
        return face.family.replace(" ", "") + "-" + style
    return face.postscript


def resolve(family: str, weight: float = 400, italic: bool = False, extra: list[Path] | None = None) -> FontRef:
    """Closest face of `family` (case/space-insensitive) to weight/italic. Raises LookupError."""
    want = _norm(family)
    cands = [f for f in all_faces(extra) if _norm(f.family) == want]
    if not cands:  # "Montserrat Bold" style names
        cands = [f for f in all_faces(extra) if _norm(f.family + f.style) == want]
    if not cands:
        raise LookupError(family)

    def score(f: Face) -> tuple:
        lo, hi = f.weights()
        wdist = 0 if lo <= weight <= hi else min(abs(weight - lo), abs(weight - hi))
        # prefer: right italic, closest weight, a file outside system dirs (bundled/brand = portable)
        return (f.italic != italic, wdist, f.installed, f.path)

    f = min(cands, key=score)
    lo, hi = f.weights()
    w = max(lo, min(hi, weight))
    loc = (("wght", float(w)),) if "wght" in f.axes else ()
    for tag, (mn, dv, mx) in f.axes.items():  # other axes at their defaults; ital=1 when asked
        if tag == "ital":
            loc += (("ital", 1.0 if italic else 0.0),)
    installed = f.installed or _norm(f.family) in _installed_families()
    return FontRef(f.path, f.index, f.family, int(w), f.italic, loc, _instance_ps(f, w, f.italic), installed)


def resolve_or_fallback(family: str, weight: float = 400, italic: bool = False,
                        extra: list[Path] | None = None) -> FontRef:
    try:
        return resolve(family, weight, italic, extra)
    except LookupError:
        r = resolve(FALLBACK[0], weight, italic)
        return FontRef(r.path, r.index, r.family, r.weight, r.italic, r.location, r.postscript, r.installed, True)


def install(paths: list[Path]) -> dict:
    """Copy font files into the user's font folder so Adobe apps can use them. On Windows the
    per-user font is also registered (HKCU), which is what makes it visible without admin rights."""
    import shutil

    dst = user_install_dir()
    dst.mkdir(parents=True, exist_ok=True)
    done = []
    for p in paths:
        p = desktop_font(p)
        target = dst / (p.name.split("-")[0] + p.suffix if p.parent.name == "web" else p.name)
        if not target.exists():
            shutil.copy2(p, target)
            if os.name == "nt":
                import winreg

                face = _read_faces(target, True)
                label = f"{face[0].family} {face[0].style} (TrueType)" if face else p.stem
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts",
                                    0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, label, 0, winreg.REG_SZ, str(target))
        done.append(str(target))
    _INDEX.clear()
    return {"installed": done, "dir": str(dst), "note": "restart Photoshop/Illustrator to see new fonts"}


# --- Google Fonts ------------------------------------------------------------------------------

GOOGLE_RAW = "https://raw.githubusercontent.com/google/fonts/main"
GOOGLE_DIR = USER / "google"
LICENCE_FILES = {"ofl": ["OFL.txt"], "apache": ["LICENSE.txt"], "ufl": ["UFL.txt", "LICENCE.txt"]}


def google_slug(family: str) -> str:
    return "".join(c for c in family.lower() if c.isalnum())


def parse_metadata(text: str) -> dict:
    """The bits of a google/fonts METADATA.pb we need: name, license, category, fonts[] (filename,
    style, weight), axes."""
    import re

    meta = {"name": (re.search(r'^name:\s*"([^"]+)"', text, re.M) or [None, None])[1],
            "license": (re.search(r'^license:\s*"([^"]+)"', text, re.M) or [None, None])[1],
            "category": (re.search(r'^category:\s*"([^"]+)"', text, re.M) or [None, None])[1],
            "designer": (re.search(r'^designer:\s*"([^"]+)"', text, re.M) or [None, None])[1],
            "fonts": [], "axes": []}
    for block in re.findall(r"^fonts \{(.*?)^\}", text, re.M | re.S):
        f = dict(re.findall(r'(\w+):\s*"?([^"\n]+)"?', block))
        meta["fonts"].append({"filename": f.get("filename"), "style": f.get("style", "normal"),
                              "weight": int(f.get("weight", 400)), "postscript": f.get("post_script_name")})
    for block in re.findall(r"^axes \{(.*?)^\}", text, re.M | re.S):
        a = dict(re.findall(r'(\w+):\s*"?([^"\n]+)"?', block))
        meta["axes"].append({"tag": a.get("tag"), "min": float(a.get("min_value", 0)), "max": float(a.get("max_value", 0))})
    return meta


def google_get(family: str, dest_root: Path | None = None) -> dict:
    """Download a Google Fonts family (all its files + licence) from github.com/google/fonts into
    assets/user-fonts/google/<slug>/ (gitignored). Variable files are what google/fonts ships when
    the family has axes."""
    from urllib.parse import quote

    import requests

    slug = google_slug(family)
    meta, licdir = None, None
    for lic in ("ofl", "apache", "ufl"):
        r = requests.get(f"{GOOGLE_RAW}/{lic}/{slug}/METADATA.pb", timeout=30)
        if r.status_code == 200:
            meta, licdir = parse_metadata(r.text), lic
            break
    if meta is None:
        raise SystemExit(f"{family!r} isn't on Google Fonts (looked for ofl|apache|ufl/{slug}); "
                         "check the spelling at fonts.google.com, or drop the font files into assets/user-fonts/")
    dest = (dest_root or GOOGLE_DIR) / slug
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    names = sorted({f["filename"] for f in meta["fonts"] if f["filename"]})
    for name in names + LICENCE_FILES[licdir]:
        target = dest / name
        if target.exists() and target.stat().st_size > 0:
            files.append(target.name)
            continue
        r = requests.get(f"{GOOGLE_RAW}/{licdir}/{slug}/{quote(name)}", timeout=120)
        if r.status_code != 200:
            if name in LICENCE_FILES[licdir]:
                continue
            raise SystemExit(f"download failed: {licdir}/{slug}/{name} (HTTP {r.status_code})")
        target.write_bytes(r.content)
        files.append(target.name)
    _INDEX.clear()
    return {"family": meta["name"] or family, "license": meta["license"], "category": meta["category"],
            "designer": meta["designer"], "dir": str(dest), "files": files,
            "axes": meta["axes"], "styles": sorted({f"{f['weight']} {f['style']}" for f in meta["fonts"]}),
            "next": f"use it as \"font\": \"{meta['name'] or family}\"; `da fonts install \"{meta['name'] or family}\"` "
                    "if Photoshop/Illustrator must see it"}


# --- pairings (curated suggestions, all on Google Fonts) ----------------------------------------

PAIRINGS = [
    ("Montserrat", "Merriweather", "geometric sans headings, sturdy serif text: editorial, institutional"),
    ("Montserrat", "Lora", "friendly sans + calligraphic serif: lifestyle, food"),
    ("Montserrat", "Open Sans", "all-sans, safe for UI and social"),
    ("Playfair Display", "Source Sans 3", "high-contrast serif display + neutral sans: fashion, premium"),
    ("Playfair Display", "Lato", "classic elegant pairing: weddings, beauty"),
    ("Inter", "Inter", "one superfamily: UI, dashboards, SaaS (vary weight/size only)"),
    ("Inter", "Source Serif 4", "modern UI sans + reading serif: blogs, docs"),
    ("Poppins", "Inter", "geometric round headings + neutral UI text: startups, apps"),
    ("Poppins", "Lora", "playful sans + warm serif: education, kids, cafés"),
    ("Oswald", "Roboto", "condensed impact headings + neutral body: sports, events, promos"),
    ("Bebas Neue", "Montserrat", "tall caps display + geometric body: posters, thumbnails"),
    ("Anton", "Inter", "heavy condensed display + clean body: bold social ads"),
    ("Archivo Black", "Archivo", "same-family contrast: brutalist, tech"),
    ("Space Grotesk", "Inter", "quirky grotesk headings + neutral text: tech, crypto, design studios"),
    ("DM Serif Display", "DM Sans", "matched family: modern editorial"),
    ("Fraunces", "Inter", "soft wonky serif + clean sans: brands with personality"),
    ("Cormorant Garamond", "Montserrat", "delicate serif + geometric sans: luxury, jewelry"),
    ("Cinzel", "Lato", "roman caps + humanist sans: classic, institutional, church"),
    ("Libre Baskerville", "Source Sans 3", "bookish serif + neutral sans: law, consulting"),
    ("Raleway", "Merriweather", "thin elegant sans headings + robust serif body"),
    ("Work Sans", "Work Sans", "versatile grotesk alone: agencies, portfolios"),
    ("Manrope", "Manrope", "modern geometric for UI and branding"),
    ("Sora", "Inter", "techy rounded headings + UI text"),
    ("Syne", "Inter", "expressive display + neutral body: art, culture"),
    ("Abril Fatface", "Lato", "fat didone display + light sans: magazine covers"),
    ("Josefin Sans", "Lora", "vintage geometric + warm serif: boutique"),
    ("Nunito", "Nunito Sans", "rounded friendly: health, kids, community"),
    ("Rubik", "Karla", "slightly rounded headings + quirky body: casual brands"),
    ("IBM Plex Sans", "IBM Plex Serif", "corporate superfamily: tech, B2B"),
    ("Caveat", "Montserrat", "handwritten accents + clean sans: personal, small business"),
    ("Pinyon Script", "Cinzel", "script + roman caps: invitations, ceremonies"),
    ("Barlow Condensed", "Barlow", "industrial condensed + body: automotive, logistics"),
]


def pairs(family: str) -> list[dict]:
    want = _norm(family)
    out = []
    for head, body, why in PAIRINGS:
        if _norm(head) == want:
            out.append({"headings": head, "body": body, "why": why})
        elif _norm(body) == want and head != body:
            out.append({"headings": head, "body": body, "why": why})
    return out


# --- CLI -----------------------------------------------------------------------------------


def _fuzzy(query: str, names: list[str], limit: int = 15) -> list[str]:
    import difflib

    q = _norm(query)
    exact = [n for n in names if q in _norm(n)]
    close = difflib.get_close_matches(query, names, n=limit, cutoff=0.5)
    seen, out = set(), []
    for n in sorted(exact, key=len) + (close if not exact else []):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:limit]


def _faces_json(faces: list[Face]) -> list[dict]:
    return [{"style": f.style, "weight": f.weight if "wght" not in f.axes else f"{f.axes['wght'][0]:g}-{f.axes['wght'][2]:g}",
             "italic": f.italic, "variable": bool(f.axes), "installed": f.installed, "file": f.path} for f in faces]


def cmd_fonts(a):
    if a.action == "list":
        if a.family:
            fam = families()
            hits = [k for k in fam if _norm(k) == _norm(a.family)]
            if not hits:
                raise SystemExit(f"no family {a.family!r} (`da fonts find`, `da fonts get`)")
            return {"family": hits[0], "faces": _faces_json(fam[hits[0]])}
        fam = families(system=not a.bundled)
        return {"count": len(fam), "families": sorted(fam) if not a.bundled else
                {k: _faces_json(v) for k, v in sorted(fam.items())}}
    if a.action == "find":
        fam = families()
        hits = _fuzzy(" ".join(a.names), list(fam))
        return [{"family": h, "styles": sorted({f.style for f in fam[h]}), "installed": any(f.installed for f in fam[h]),
                 "variable": any(f.axes for f in fam[h])} for h in hits]
    if a.action == "get":
        return [google_get(n) for n in a.names]
    if a.action == "install":
        files: list[Path] = []
        for n in a.names:
            p = Path(n).expanduser()
            if p.is_file():
                files.append(p)
                continue
            if p.is_dir():
                files += [q for q in p.rglob("*") if q.suffix.lower() in FONT_EXT]
                continue
            faces = [f for f in all_faces(system=False) if _norm(f.family) == _norm(n)]
            if not faces:
                raise SystemExit(f"{n!r}: no such file, and no family of that name outside the system fonts "
                                 f"(get it first: `da fonts get \"{n}\"`)")
            files += sorted({Path(f.path) for f in faces})
        return install(files)
    if a.action == "pair":
        res = pairs(" ".join(a.names))
        return {"family": " ".join(a.names), "suggestions": res or [], "note": (
            "curated suggestions, all on Google Fonts (`da fonts get`)" if res else
            "no curated pairing for this family; pick a contrasting classification (serif + sans, display + text)")}
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("fonts", help="list / find / get (Google Fonts) / install / pair fonts")
    p.add_argument("action", choices=["list", "find", "get", "install", "pair"])
    p.add_argument("names", nargs="*", help="family names, files or a query")
    p.add_argument("--family", help="list: faces of one family")
    p.add_argument("--bundled", action="store_true", help="list: only repo fonts (bundled, user, google)")
    p.set_defaults(func=cmd_fonts)
