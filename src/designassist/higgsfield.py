"""higgsfield: generated images (photos, illustrations, vector-style art, edits, upscales) through the
Higgsfield API (docs.higgsfield.ai). Ported from editassist, focused on images.

The API is one asynchronous lifecycle shared by every model:
  POST https://api.higgsfield.ai/<endpoint id>      -> {request_id, status_url, ...}
  GET  status_url                                   -> queued | in_progress | completed | failed | nsfw | canceled
  completed -> images[].url | video.url (kept >= 7 days; we download immediately)

Each model has its own input schema, and Higgsfield's docs say the model page is the source of truth,
so this module does not hardcode parameters: `models` reads the catalog from the docs, `schema` prints a
model page's endpoint id + usage notes + JSON schema for the agent to read, then `generate` estimates,
submits, polls, downloads into work/generated/ and logs the result.

Credentials (.env): HF_API_KEY_ID + HF_API_KEY_SECRET (console.higgsfield.ai), or HF_KEY="id:secret".
Budget: estimates above DA_HF_MAX_USD (default $2) need --yes.
"""
from __future__ import annotations

import json
import mimetypes
import os
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .project import CACHE as _CACHE
from .project import ROOT, Project, read_json, write_json

API = "https://api.higgsfield.ai"
DOCS = "https://docs.higgsfield.ai"
CACHE = _CACHE / "higgsfield"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}
UPLOAD_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif"}


def _env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if (ROOT / ".env").exists():
        from dotenv import dotenv_values

        return dotenv_values(ROOT / ".env").get(name) or None
    return None


def _auth() -> dict:
    kid, secret = _env("HF_API_KEY_ID"), _env("HF_API_KEY_SECRET")
    key = _env("HF_KEY") or ""
    if not (kid and secret) and key.count(":") == 1:
        kid, secret = key.split(":")
    if not (kid and secret):
        raise SystemExit(f"Higgsfield credentials missing: set HF_API_KEY_ID and HF_API_KEY_SECRET in "
                         f"{ROOT / '.env'} (create them at console.higgsfield.ai)")
    return {"Authorization": f"Key {kid}:{secret}"}


def max_usd() -> float:
    return float(_env("DA_HF_MAX_USD") or "2")


def _check(r: requests.Response, what: str) -> dict:
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:300]
        hint = {401: "check HF_API_KEY_ID / HF_API_KEY_SECRET", 403: "not enough credits",
                404: "model or request not available to this account", 422: "parameters don't match the model schema "
                "(run `da hf schema <endpoint>`)", 423: "model temporarily blocked, try later",
                503: "model disabled or not ready, try later"}.get(r.status_code, "")
        cid = r.headers.get("X-Correlation-ID", "")
        raise SystemExit(f"Higgsfield {what} failed: HTTP {r.status_code} {detail}"
                         + (f" ({hint})" if hint else "") + (f" [correlation {cid}]" if cid else ""))
    return r.json() if r.content else {}


# --- catalog from the docs -------------------------------------------------------------------

def _doc(path: str, max_age: float = 7 * 86400) -> str:
    """Fetch a docs page as markdown, cached for a week (docs change; models come and go)."""
    path = path.removesuffix(".md").strip("/")
    f = CACHE / "docs" / (path.replace("/", "__") + ".md")
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        return f.read_text(encoding="utf-8")
    r = requests.get(f"{DOCS}/{path}.md", timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"docs page not found: {DOCS}/{path}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text, encoding="utf-8")
    return r.text


def parse_catalog(page: str) -> list[str]:
    return sorted(set(re.findall(r'href="/docs/models/([a-z0-9.-]+)"', page)))


def parse_model_page(page: str, fam: str) -> list[str]:
    return sorted(set(re.findall(rf"/docs/models/{re.escape(fam)}/([a-z0-9-]+)", page)))


def parse_workflow(page: str) -> dict:
    eid = re.search(r"\*\*Endpoint ID:\*\*\s*`([^`]+)`", page)
    name = re.search(r"^# (.+?)(?: API)?$", page, re.M)
    after = page[name.end():] if name else page  # the page opens with a docs-index blockquote; skip it
    desc = re.search(r"^> (?!## )(.+)$", after, re.M)
    return {"endpoint": eid[1] if eid else None, "name": name[1] if name else None, "summary": desc[1] if desc else ""}


def models(refresh: bool = False, kind: str | None = "image", search: str | None = None) -> list[dict]:
    cache = CACHE / "models.json"
    if cache.exists() and not refresh and time.time() - cache.stat().st_mtime < 7 * 86400:
        items = read_json(cache)
        if any("llms.txt" in i.get("summary", "") for i in items):  # catalog cached by an older parser
            for i in items:
                if "llms.txt" in i.get("summary", ""):
                    try:
                        i["summary"] = parse_workflow(_doc(i["doc"], 30 * 86400))["summary"]
                    except SystemExit:
                        i["summary"] = ""
            write_json(cache, items)
    else:
        age = 0 if refresh else 7 * 86400
        families = []
        for cat, k in (("docs/models/image-generation", "image"), ("docs/models/video-generation", "video")):
            for fam in parse_catalog(_doc(cat, age)):
                families.append((fam, k))

        def workflows(fk):
            fam, k = fk
            page = _doc(f"docs/models/{fam}", age)
            title = (re.search(r"^# (.+)$", page, re.M) or [None, fam])[1]
            return [(fam, title, k, w) for w in parse_model_page(page, fam)]

        with ThreadPoolExecutor(8) as ex:
            flows = [w for ws in ex.map(workflows, families) for w in ws]

        def entry(f):
            fam, title, k, wf = f
            info = parse_workflow(_doc(f"docs/models/{fam}/{wf}", age))
            return {"endpoint": info["endpoint"], "name": info["name"] or f"{title} {wf}", "kind": k,
                    "doc": f"docs/models/{fam}/{wf}", "summary": info["summary"]}

        with ThreadPoolExecutor(8) as ex:
            items = [e for e in ex.map(entry, flows) if e["endpoint"]]
        write_json(cache, items)
    if kind:
        items = [i for i in items if i["kind"] == kind]
    if search:
        q = search.lower()
        items = [i for i in items if q in (i["endpoint"] + " " + i["name"] + " " + i["summary"]).lower()]
    return items


def _find(endpoint_or_doc: str) -> dict:
    key = endpoint_or_doc.strip("/").removesuffix(".md")
    for m in models(kind=None):
        if key in (m["endpoint"], m["doc"], m["doc"].removeprefix("docs/models/")):
            return m
    raise SystemExit(f"unknown model {endpoint_or_doc!r}: run `da hf models` (or `--refresh`)")


def schema(endpoint_or_doc: str) -> str:
    """Endpoint id, usage notes and the complete JSON input schema of one model, for the agent to read."""
    m = _find(endpoint_or_doc)
    page = _doc(m["doc"])
    notes = re.search(r"## Usage notes\n(.*?)\n## ", page, re.S)
    js = re.search(r'<Accordion title="Complete JSON schema">\s*```json[^\n]*\n(.*?)```', page, re.S)
    body = js[1] if js else "(no JSON schema block; read the page)"
    try:
        body = json.dumps(json.loads(body), indent=1)
    except ValueError:
        pass
    return (f"{m['name']}\nendpoint: {m['endpoint']}\ndocs: {DOCS}/{m['doc']}\n\n"
            f"usage notes:\n{notes[1].strip() if notes else '(none)'}\n\ninput schema:\n{body}")


# --- generation ------------------------------------------------------------------------------

def upload(path: Path) -> str:
    """Local file -> public URL usable in image_url / image_urls fields."""
    ctype = UPLOAD_TYPES.get(path.suffix.lower())
    if not ctype:
        raise SystemExit(f"{path.name}: Higgsfield accepts {sorted(UPLOAD_TYPES)} for uploads")
    up = _check(requests.post(f"{API}/files/generate-upload-url", headers=_auth(),
                              json={"content_type": ctype}, timeout=60), "upload url")
    with open(path, "rb") as fh:  # presigned storage URL: send its headers, never our credentials
        r = requests.put(up["upload_url"], data=fh, headers=up.get("upload_headers") or {"Content-Type": ctype},
                         timeout=600)
    if r.status_code >= 300:
        raise SystemExit(f"upload of {path.name} failed: HTTP {r.status_code}")
    return up["public_url"]


def _prepare(project: Project | None, args: dict, files: list[str]) -> dict:
    """`--file image_url=output/preview/post.png` uploads a local file into that field; list fields
    (e.g. image_urls) take repeated --file entries."""
    args = dict(args)
    for spec in files or []:
        if "=" not in spec:
            raise SystemExit(f"--file expects field=path, got {spec!r}")
        field, p = spec.split("=", 1)
        path = project.abs(p) if project else Path(p).resolve()
        if not path.exists():
            path = Path(p).resolve()
        if not path.exists():
            raise SystemExit(f"file not found: {p}")
        url = upload(path)
        if field.endswith("_urls") or isinstance(args.get(field), list):
            args.setdefault(field, []).append(url)
        else:
            args[field] = url
    return args


def estimate(endpoint: str, args: dict) -> dict:
    return _check(requests.post(f"{API}/estimate/{endpoint.strip('/')}", headers=_auth(), json=args, timeout=60),
                  "estimate")


def generate(project: Project, endpoint: str, args: dict, files: list[str] | None = None,
             yes: bool = False, timeout_min: float = 20, name: str | None = None) -> dict:
    endpoint = endpoint.strip("/")
    args = _prepare(project, args, files or [])
    est = {}
    try:
        est = estimate(endpoint, args)
    except SystemExit as e:  # estimate is advisory; a bad schema will fail again on submit with detail
        if "HTTP 4" in str(e) and "422" not in str(e) and "404" not in str(e):
            raise
        est = {"error": str(e)}
    cap = max_usd()
    usd = float(est.get("usd") or 0)
    if usd > cap and not yes:
        raise SystemExit(f"estimated ${usd:.2f} ({est.get('credits')} credits) is above DA_HF_MAX_USD=${cap:.2f}. "
                         "Confirm with the user, then re-run with --yes.")
    log = project.path("work", "generated", "requests.jsonl")
    log.parent.mkdir(parents=True, exist_ok=True)
    idem = str(uuid.uuid4())
    sub = None
    for attempt in range(3):  # same Idempotency-Key on retry: a timeout never double-charges
        try:
            r = requests.post(f"{API}/{endpoint}", headers={**_auth(), "Idempotency-Key": idem}, json=args, timeout=120)
            if r.status_code >= 500 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            sub = _check(r, "submit")
            break
        except requests.RequestException:
            if attempt == 2:
                raise SystemExit("Higgsfield submit: network error after 3 attempts")
            time.sleep(2 * (attempt + 1))
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"request_id": sub["request_id"], "endpoint": endpoint, "args": args,
                             "estimate": est, "name": name, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    print(f"submitted {sub['request_id']} ({endpoint}), est {est.get('credits', '?')} credits / ${est.get('usd', '?')}",
          flush=True)
    return fetch(project, sub["request_id"], sub.get("status_url"), timeout_min, name, endpoint, args)


def result_urls(res: dict) -> list[str]:
    urls = [i["url"] for i in res.get("images") or [] if i.get("url")]
    for k in ("image", "video"):
        if isinstance(res.get(k), dict) and res[k].get("url"):
            urls.append(res[k]["url"])
    return urls


def fetch(project: Project, request_id: str, status_url: str | None = None, timeout_min: float = 20,
          name: str | None = None, endpoint: str = "", args: dict | None = None) -> dict:
    """Poll until terminal (2 s -> 10 s backoff with jitter), then download into work/generated/.
    Also the resume path: `da hf fetch <p> <request_id>` after a timeout or a closed terminal."""
    status_url = status_url or f"{API}/requests/{request_id}/status"
    if not endpoint:  # resumed: recover endpoint/name/args from the request log
        for line in (project.path("work", "generated", "requests.jsonl").read_text(encoding="utf-8").splitlines()
                     if project.path("work", "generated", "requests.jsonl").exists() else []):
            rec = json.loads(line)
            if rec.get("request_id") == request_id:
                endpoint, args, name = rec.get("endpoint", ""), rec.get("args"), name or rec.get("name")
    delay, deadline = 2.0, time.time() + timeout_min * 60
    while True:
        try:
            res = _check(requests.get(status_url, headers=_auth(), timeout=30), "status")
        except requests.RequestException:
            res = {"status": "network-retry"}
        if res.get("status") in TERMINAL:
            break
        if time.time() > deadline:
            raise SystemExit(f"still {res.get('status')} after {timeout_min} min. Resume later with "
                             f"`da hf fetch {project.name} {request_id}`")
        time.sleep(delay + random.uniform(0, 0.5))
        delay = min(delay * 1.5, 10.0)
    if res["status"] != "completed":
        return {"request_id": request_id, "status": res["status"], "error": res.get("error"),
                "charged": False if res["status"] in ("failed", "nsfw", "canceled") else None}
    out = []
    base = re.sub(r"[^\w-]+", "_", name or endpoint.replace("/", "_") or "hf").strip("_")[:40]
    index_file = project.path("work", "generated", "index.json")
    index = read_json(index_file, [])
    for i, u in enumerate(result_urls(res)):
        ext = Path(u.split("?")[0]).suffix or mimetypes.guess_extension(
            requests.head(u, timeout=30).headers.get("Content-Type", "")) or ".bin"
        dst = project.path("work", "generated", f"{base}_{request_id[:8]}_{i}{ext}")
        with requests.get(u, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dst, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        info = {"file": project.rel(dst), "source": "higgsfield", "endpoint": endpoint, "request_id": request_id,
                "prompt": (args or {}).get("prompt")}
        try:
            from PIL import Image

            with Image.open(dst) as im:
                info["size"] = f"{im.width}x{im.height}"
        except Exception:
            pass
        index.append(info)
        out.append(info)
    write_json(index_file, index)
    return {"request_id": request_id, "status": "completed", "files": out,
            "next": "LOOK at each file before placing it; regenerate only with a changed prompt"}


# --- CLI -----------------------------------------------------------------------------------

def _js(v: str) -> dict:
    p = Path(v)
    if v.strip().endswith(".json") and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(v)


def cmd_hf(a):
    if a.hf == "models":
        items = models(a.refresh, None if a.kind == "all" else a.kind, a.search)
        return [{"endpoint": i["endpoint"], "name": i["name"], "kind": i["kind"], "summary": i["summary"][:120]}
                for i in items]
    if a.hf == "schema":
        return schema(a.endpoint)
    if a.hf == "estimate":
        return estimate(a.endpoint, _js(a.args))
    if a.hf == "generate":
        return generate(Project(a.project), a.endpoint, _js(a.args), a.file, a.yes, a.timeout, a.name)
    if a.hf == "fetch":
        return fetch(Project(a.project), a.request_id, timeout_min=a.timeout)
    raise SystemExit(a.hf)


def register(sub) -> None:
    p = sub.add_parser("hf", help="Higgsfield: generated images (models, schema, estimate, generate, fetch)")
    hs = p.add_subparsers(dest="hf", required=True)
    q = hs.add_parser("models", help="catalog from docs.higgsfield.ai (cached 7 days)")
    q.add_argument("--kind", choices=["image", "video", "all"], default="image")
    q.add_argument("--search")
    q.add_argument("--refresh", action="store_true")
    q = hs.add_parser("schema", help="endpoint id, usage notes and JSON input schema of one model")
    q.add_argument("endpoint")
    q = hs.add_parser("estimate", help="credit / USD estimate for a request")
    q.add_argument("endpoint")
    q.add_argument("--args", default="{}", help="json string or .json file")
    q = hs.add_parser("generate", help="estimate, submit, wait, download into work/generated/")
    q.add_argument("project")
    q.add_argument("endpoint")
    q.add_argument("--args", default="{}", help="json string or .json file (model input fields)")
    q.add_argument("--file", action="append", default=[], help="field=local/path: upload and set that field")
    q.add_argument("--name", help="base name for the downloaded files")
    q.add_argument("--yes", action="store_true", help="allow estimates above DA_HF_MAX_USD")
    q.add_argument("--timeout", type=float, default=20, help="minutes to wait")
    q = hs.add_parser("fetch", help="resume a submitted request: wait, download")
    q.add_argument("project")
    q.add_argument("request_id")
    q.add_argument("--timeout", type=float, default=20)
    for sp in hs.choices.values():
        sp.set_defaults(func=cmd_hf)
