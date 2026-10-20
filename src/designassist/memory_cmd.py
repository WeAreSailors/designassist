"""`da memory`, `da setup-done` and `da client`: where the user's design memory lives, the
first-run marker, and per-client folders (preferences + brand kit) in that memory."""
from __future__ import annotations

import json
from datetime import datetime

from .project import ROOT, Project

SETUP = ROOT / ".designassist" / "setup.json"


def cmd_memory(a):
    from . import project as P

    if a.install:
        return P.install_memory_os()
    if a.init:
        return P.init_memory()
    d = P.memory_dir()
    on_os = d.parent == P.Path.home() / ".memory-os" / "memory"
    return {"dir": str(d), "exists": d.is_dir(), "tier": "memory-os global (private)" if on_os else (
        "local fallback (gitignored)" if d == P.LOCAL_MEMORY else "DA_MEMORY_DIR"),
        "files": sorted(p.relative_to(d).as_posix() for p in d.rglob("*.md")) if d.is_dir() else [],
        "next": None if (d / "preferences.md").exists() else "uv run da memory --init"}


def setup_done(skipped: bool = False, reset: bool = False) -> dict:
    if reset:
        SETUP.unlink(missing_ok=True)
        return {"reset": True, "note": "the guided setup starts again on the next Claude Code session"}
    SETUP.parent.mkdir(parents=True, exist_ok=True)
    data = {"status": "skipped" if skipped else "done", "at": datetime.now().isoformat(timespec="seconds")}
    SETUP.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def cmd_setup_done(a):
    return setup_done(a.skipped, a.reset)


def cmd_client(a):
    from . import brand as B
    from . import design as D

    if a.action == "list":
        return [{"client": s, "name": (B.load(s) or {}).get("name", s), "brand": B.load(s) is not None}
                for s in B.all_clients()]
    if a.action == "new":
        if not a.args:
            raise SystemExit('usage: da client new "<Client Name>"')
        return B.create(a.args[0])
    if a.action == "set":
        if len(a.args) != 2:
            raise SystemExit('usage: da client set <project> "<Client Name>"')
        pr = Project(a.args[0])
        res = B.create(a.args[1])
        pr.update_settings(client=a.args[1])
        if D.path(pr).exists():
            d = D.load(pr)
            d["brand"] = res["client"]
            D.save(pr, d)
        return {"project": pr.name, **res}
    if a.action == "show":
        if not a.args:
            raise SystemExit("usage: da client show <project>")
        return B.show(Project(a.args[0]))
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("memory", help="where your design memory lives; --init seeds it, --install sets up memory-os")
    p.add_argument("--init", action="store_true", help="seed/migrate the design memory from memory.template/")
    p.add_argument("--install", action="store_true", help="install memory-os from vendor/memory-os (no download)")
    p.set_defaults(func=cmd_memory)

    p = sub.add_parser("setup-done", help="mark the guided first-run setup as finished (or skipped / reset)")
    p.add_argument("--skipped", action="store_true")
    p.add_argument("--reset", action="store_true")
    p.set_defaults(func=cmd_setup_done)

    p = sub.add_parser("client", help="clients: list | new <Name> | set <project> <Name> | show <project>")
    p.add_argument("action", choices=["list", "new", "set", "show"])
    p.add_argument("args", nargs="*")
    p.set_defaults(func=cmd_client)
