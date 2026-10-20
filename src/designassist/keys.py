"""keys: API keys in .env. Status (masked), validation against free endpoints, and writing.

Values are never printed: only "set / valid / invalid" plus the last 4 characters.
Validation never spends credits: account or listing endpoints only.
"""
from __future__ import annotations

import os
import platform
import sys
import uuid

from .project import ROOT

ENV = ROOT / ".env"

KEYS = {
    "HF_API_KEY_ID": {"for": "Higgsfield generated images (with HF_API_KEY_SECRET)", "where": "https://console.higgsfield.ai"},
    "HF_API_KEY_SECRET": {"for": "Higgsfield (pair of HF_API_KEY_ID)", "where": "https://console.higgsfield.ai"},
    "PEXELS_API_KEY": {"for": "free stock photos", "where": "https://www.pexels.com/api/"},
    "UNSPLASH_ACCESS_KEY": {"for": "free stock photos (Unsplash Access Key)", "where": "https://unsplash.com/oauth/applications"},
}
# plain settings that live in .env too; shown unmasked, never validated against a service
SETTINGS = {
    "DA_HF_MAX_USD": {"for": "Higgsfield generations above this many USD need --yes (default 2)", "where": ".env"},
    "DA_CMYK_ICC": {"for": "CMYK profile (.icc) for print PDFs; empty = auto-detect", "where": ".env"},
}


def _values() -> dict[str, tuple[str | None, str]]:
    """name -> (value, source). .env wins over the process environment, like python-dotenv does here."""
    from dotenv import dotenv_values

    file = dotenv_values(ENV) if ENV.exists() else {}
    out = {}
    for k in {**KEYS, **SETTINGS}:
        if file.get(k):
            out[k] = (file[k], ".env")
        elif os.environ.get(k):
            out[k] = (os.environ[k], "environment")
        else:
            out[k] = (None, "-")
    return out


def _mask(v: str | None) -> str:
    return "" if not v else ("…" + v[-4:] if len(v) > 8 else "set")


def _check(name: str, v: str, vals: dict) -> tuple[bool | None, str]:
    import requests

    try:
        if name in ("HF_API_KEY_ID", "HF_API_KEY_SECRET"):
            kid, sec = vals["HF_API_KEY_ID"][0], vals["HF_API_KEY_SECRET"][0]
            if not (kid and sec):
                return None, "needs both HF_API_KEY_ID and HF_API_KEY_SECRET"
            # status of a request that can't exist: 404 = credentials accepted, 401 = rejected. Free.
            r = requests.get(f"https://api.higgsfield.ai/requests/{uuid.uuid4()}/status",
                             headers={"Authorization": f"Key {kid}:{sec}"}, timeout=20)
            if r.status_code == 404:
                return True, "credentials accepted"
            return False, f"HTTP {r.status_code}: {r.text[:120]}"
        if name == "PEXELS_API_KEY":
            r = requests.get("https://api.pexels.com/v1/search", params={"query": "city", "per_page": 1},
                             headers={"Authorization": v}, timeout=20)
            return (True, "search OK") if r.status_code == 200 else (False, f"HTTP {r.status_code}")
        if name == "UNSPLASH_ACCESS_KEY":
            r = requests.get("https://api.unsplash.com/search/photos", params={"query": "city", "per_page": 1},
                             headers={"Authorization": f"Client-ID {v}", "Accept-Version": "v1"}, timeout=20)
            if r.status_code == 200:
                return True, f"search OK ({r.headers.get('X-Ratelimit-Remaining', '?')} requests left this hour)"
            return False, f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return None, f"network error: {e.__class__.__name__}"
    return None, "no check"


def status(check: bool = False, only: list[str] | None = None) -> list[dict]:
    vals = _values()
    rows = []
    for k, meta in KEYS.items():
        if only and k not in only:
            continue
        v, src = vals[k]
        row = {"key": k, "set": bool(v), "source": src, "value": _mask(v), "for": meta["for"], "get_it_at": meta["where"]}
        if check and v:
            ok, note = _check(k, v, vals)
            row.update(valid=ok, note=note)
        rows.append(row)
    for k, meta in SETTINGS.items():
        if only and k not in only:
            continue
        v, src = vals[k]
        rows.append({"key": k, "set": bool(v), "source": src, "value": v or "", "for": meta["for"], "setting": True})
    return rows


def set_key(name: str, value: str) -> dict:
    """Write/replace one key in .env, keeping every other line and comment. Never echoes the value."""
    if name not in KEYS and name not in SETTINGS and not name.isupper():
        raise SystemExit(f"unknown key {name!r}; known: {', '.join([*KEYS, *SETTINGS])}")
    value = value.strip().strip('"').strip("'")
    if not value or "\n" in value:
        raise SystemExit("empty or multi-line value")
    if not ENV.exists():
        example = ROOT / ".env.example"
        ENV.write_text(example.read_text(encoding="utf-8") if example.exists() else "", encoding="utf-8")
    lines = ENV.read_text(encoding="utf-8").splitlines()
    done = False
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == name:
            lines[i] = f"{name}={value}"
            done = True
    if not done:
        lines.append(f"{name}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if platform.system() != "Windows":
        os.chmod(ENV, 0o600)  # keys: owner-only
    os.environ[name] = value
    return {"key": name, "written_to": ".env", "value": value if name in SETTINGS else _mask(value)}


def is_gitignored() -> bool:
    gi = ROOT / ".gitignore"
    return gi.exists() and any(l.strip() in (".env", "/.env") for l in gi.read_text(encoding="utf-8").splitlines())


def cmd_keys(a):
    if a.action == "set":
        if not a.name:
            raise SystemExit("usage: printf '%s' '<value>' | da keys set NAME")
        if sys.stdin.isatty():
            raise SystemExit("pipe the value on stdin (it never goes on the command line): printf '%s' '<value>' | da keys set NAME")
        res = set_key(a.name, sys.stdin.read())
        res["gitignored"] = is_gitignored()
        return res
    return {"gitignored": is_gitignored(), "env_file": ".env" if ENV.exists() else "missing (setup copies .env.example)",
            "keys": status(a.check, a.only)}


def register(sub) -> None:
    p = sub.add_parser("keys", help="API keys: status (masked), --check validates free; `keys set NAME` reads stdin")
    p.add_argument("action", nargs="?", choices=["status", "set"], default="status")
    p.add_argument("name", nargs="?")
    p.add_argument("--check", action="store_true", help="validate against free endpoints")
    p.add_argument("--only", nargs="*")
    p.set_defaults(func=cmd_keys)
