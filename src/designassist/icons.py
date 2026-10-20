"""Lucide icons (ISC licence), fetched on demand from jsDelivr and cached in .cache/icons/.
Pinned version so a design renders the same icon next year."""
from __future__ import annotations

import json
from pathlib import Path

import requests

from .project import CACHE

VERSION = "1.50.0"
BASE = f"https://cdn.jsdelivr.net/npm/lucide-static@{VERSION}"
DIR = CACHE / "icons" / f"lucide-{VERSION}"


def icon_file(name: str) -> Path:
    p = DIR / f"{name}.svg"
    if p.exists():
        return p
    r = requests.get(f"{BASE}/icons/{name}.svg", timeout=20)
    if r.status_code == 404:
        hits = search(name, 8)
        raise SystemExit(f"no Lucide icon {name!r}" + (f"; close: {', '.join(h['name'] for h in hits)}" if hits else ""))
    r.raise_for_status()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(r.text, encoding="utf-8")
    return p


def _tags() -> dict:
    p = DIR / "tags.json"
    if not p.exists():
        r = requests.get(f"{BASE}/tags.json", timeout=30)
        r.raise_for_status()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text, encoding="utf-8")
    return json.loads(p.read_text(encoding="utf-8"))


def search(query: str, limit: int = 20) -> list[dict]:
    """Icons whose name or tags match every word of the query (English tags)."""
    words = [w.lower() for w in query.replace("-", " ").split()]
    out = []
    for name, tags in _tags().items():
        hay = name.replace("-", " ") + " " + " ".join(tags)
        if all(w in hay for w in words):
            score = sum(w in name for w in words) * 2 + (name == query)
            out.append({"name": name, "tags": tags[:6], "score": score})
    out.sort(key=lambda h: (-h["score"], len(h["name"])))
    return [{"name": h["name"], "tags": h["tags"]} for h in out[:limit]]


def cmd_icon(a):
    if a.action == "search":
        return search(" ".join(a.terms), a.limit)
    if a.action == "get":
        import shutil

        out = []
        for name in a.terms:
            p = icon_file(name)
            if a.project:
                from .project import Project

                pr = Project(a.project)
                dst = pr.path("work", "icons", p.name)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
                out.append({"name": name, "file": pr.rel(dst), "layer": {"type": "icon", "name": name}})
            else:
                out.append({"name": name, "file": str(p), "layer": {"type": "icon", "name": name}})
        return out
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("icon", help=f"Lucide icons (v{VERSION}): search by keyword, get svg files")
    p.add_argument("action", choices=["search", "get"])
    p.add_argument("terms", nargs="+", help="search words (English) or icon names")
    p.add_argument("--project", help="get: copy into the project's work/icons/")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_icon)
