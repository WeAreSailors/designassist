"""`da stock`: free stock photos (Pexels, Unsplash) — search, look, download, credit.

1. `da stock <p> "café da manhã" [--source pexels|unsplash] [--orientation portrait]`
   searches and writes a numbered contact sheet (work/stock/<source>-<query>/sheet.jpg) to LOOK at.
2. `da stock <p> "café da manhã" --download 2,5` downloads those numbers (full size) into
   work/stock/ and records photographer, page and licence in work/credits.json.

Keys (repo .env or environment): PEXELS_API_KEY, UNSPLASH_ACCESS_KEY. Both licences allow free
commercial use without attribution, but credit is kept for the client and Unsplash's API terms
require the download endpoint to be triggered on every download (done here).
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .project import ROOT, Project, read_json, slug, write_json

LICENCES = {"pexels": "Pexels License (free use, attribution appreciated) https://www.pexels.com/license/",
            "unsplash": "Unsplash License (free use, attribution appreciated) https://unsplash.com/license"}
KEYS = {"pexels": "PEXELS_API_KEY", "unsplash": "UNSPLASH_ACCESS_KEY"}


def api_key(source: str) -> str:
    from dotenv import dotenv_values

    name = KEYS[source]
    v = os.environ.get(name) or (dotenv_values(ROOT / ".env").get(name) if (ROOT / ".env").exists() else None)
    if not v:
        where = "pexels.com/api (free, instant)" if source == "pexels" else "unsplash.com/developers (free Access Key)"
        raise SystemExit(f"{name} is missing: get one at {where} and put it in {ROOT / '.env'} "
                         "(or ask for the setup skill)")
    return v


def _get(url: str, headers: dict, params: dict | None = None) -> dict:
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code in (401, 403):
        raise SystemExit(f"stock search refused (HTTP {r.status_code}): check the API key")
    if r.status_code == 429:
        raise SystemExit("stock API rate limit reached; try again in a while")
    r.raise_for_status()
    return r.json()


def search(source: str, query: str, n: int = 12, orientation: str | None = None) -> list[dict]:
    """Normalised results: {id, width, height, thumb, full, page, photographer, photographer_url, alt, download_location}."""
    if source == "pexels":
        params = {"query": query, "per_page": min(n, 80)}
        if orientation:
            params["orientation"] = orientation
        data = _get("https://api.pexels.com/v1/search", {"Authorization": api_key("pexels")}, params)
        return [{"id": str(p["id"]), "width": p["width"], "height": p["height"], "thumb": p["src"]["medium"],
                 "full": p["src"]["original"], "page": p["url"], "photographer": p.get("photographer"),
                 "photographer_url": p.get("photographer_url"), "alt": p.get("alt") or ""} for p in data.get("photos", [])]
    if source == "unsplash":
        params = {"query": query, "per_page": min(n, 30)}
        if orientation:
            params["orientation"] = {"square": "squarish"}.get(orientation, orientation)
        data = _get("https://api.unsplash.com/search/photos", {"Authorization": f"Client-ID {api_key('unsplash')}"}, params)
        return [{"id": p["id"], "width": p["width"], "height": p["height"], "thumb": p["urls"]["small"],
                 "full": p["urls"]["full"], "page": p["links"]["html"], "photographer": p["user"].get("name"),
                 "photographer_url": p["user"]["links"].get("html"), "alt": p.get("alt_description") or "",
                 "download_location": p["links"].get("download_location")} for p in data.get("results", [])]
    raise SystemExit("source must be pexels or unsplash")


def _fetch(url: str, dst: Path, headers: dict | None = None) -> Path:
    with requests.get(url, headers=headers or {}, stream=True, timeout=120) as r:
        r.raise_for_status()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
    return dst


def folder(project: Project, source: str, query: str) -> Path:
    return project.path("work", "stock", f"{source}-{slug(query)}")


def browse(project: Project, query: str, source: str = "pexels", n: int = 12, orientation: str | None = None) -> dict:
    from .render import contact_sheet

    results = search(source, query, n, orientation)
    if not results:
        return {"query": query, "source": source, "results": 0, "hint": "no results; try English keywords or fewer words"}
    d = folder(project, source, query)
    write_json(d / "results.json", {"query": query, "source": source, "orientation": orientation, "results": results})
    thumbs = [d / "thumbs" / f"{i + 1:02d}.jpg" for i in range(len(results))]
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda rt: _fetch(rt[0]["thumb"], rt[1]), zip(results, thumbs)))
    sheet = contact_sheet(thumbs, d / "sheet.jpg", cell=360, cols=4)
    return {"query": query, "source": source, "results": len(results), "sheet": project.rel(sheet),
            "items": [{"n": i + 1, "size": f"{r['width']}x{r['height']}", "alt": r["alt"][:80],
                       "by": r["photographer"]} for i, r in enumerate(results)],
            "next": f"look at the sheet, then: da stock {project.name} \"{query}\" --source {source} --download 1,4"}


def download(project: Project, query: str, numbers: list[int], source: str = "pexels", n: int = 12,
             orientation: str | None = None) -> dict:
    d = folder(project, source, query)
    saved = read_json(d / "results.json")
    results = saved["results"] if saved else search(source, query, n, orientation)
    credits_file = project.path("work", "credits.json")
    credits = read_json(credits_file, [])
    files = []
    for num in numbers:
        if not 1 <= num <= len(results):
            raise SystemExit(f"--download {num}: there are {len(results)} results")
        r = results[num - 1]
        dst = project.path("work", "stock", f"{source}-{r['id']}.jpg")
        if not dst.exists():
            if source == "unsplash" and r.get("download_location"):
                # required by Unsplash API terms: count the download (returns the file url too)
                info = _get(r["download_location"], {"Authorization": f"Client-ID {api_key('unsplash')}"})
                _fetch(info.get("url") or r["full"], dst)
            else:
                _fetch(r["full"], dst)
        entry = {"file": project.rel(dst), "source": source, "id": r["id"], "photographer": r["photographer"],
                 "photographer_url": r["photographer_url"], "page": r["page"], "licence": LICENCES[source],
                 "query": query}
        if not any(c.get("file") == entry["file"] for c in credits):
            credits.append(entry)
        files.append({"n": num, "file": entry["file"], "size": f"{r['width']}x{r['height']}", "by": r["photographer"]})
    write_json(credits_file, credits)
    return {"downloaded": files, "credits": project.rel(credits_file),
            "use": "as an image layer: {\"type\": \"image\", \"src\": \"<file>\", \"fit\": \"cover\"}"}


def cmd_stock(a):
    pr = Project(a.project)
    if a.download:
        nums = [int(x) for x in a.download.replace(" ", "").split(",") if x]
        return download(pr, a.query, nums, a.source, a.n, a.orientation)
    return browse(pr, a.query, a.source, a.n, a.orientation)


def register(sub) -> None:
    p = sub.add_parser("stock", help="free stock photos (Pexels/Unsplash): contact sheet, then --download N,M")
    p.add_argument("project")
    p.add_argument("query", help="search words (English works best)")
    p.add_argument("--source", choices=["pexels", "unsplash"], default="pexels")
    p.add_argument("--orientation", choices=["portrait", "landscape", "square"])
    p.add_argument("--n", type=int, default=12, help="results to show")
    p.add_argument("--download", help="numbers from the sheet, e.g. 1,3")
    p.set_defaults(func=cmd_stock)
