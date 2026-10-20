"""Affinity (by Canva, 3.2+) live control through its local AI connector.

Affinity serves its JavaScript scripting SDK as an MCP endpoint at http://localhost:6767/sse while
**Settings > AI connector** is on (the user has to switch it on in the app; it can't be enabled from
outside, and it dies with the app). Transport: GET /sse -> an `endpoint` event with a session POST
URL -> JSON-RPC POSTs there, replies arrive as SSE `message` events.

What the endpoint allows (Affinity 3.2.3):
- `execute_script {script}`: runs JS inside Affinity; ONLY console.log output comes back.
- The session must read the `preamble` doc topic before execute_script is accepted.
- Scripts may touch the filesystem only under the user's Desktop (`app.userDesktopPath`), so images
  are staged in ~/Desktop/designassist-affinity/ for the build and the .af is saved there, then moved.
- `render_spread {document_session_uuid, spread_index}`: JPEG of a spread (max 1024 px).

The build itself (design.json -> native Affinity document) is generated in affinity_build.py.
"""
from __future__ import annotations

import base64
import http.client
import json
import queue
import threading
import time
import urllib.parse
from pathlib import Path

HOST, PORT = "localhost", 6767
VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
NOT_RUNNING = ("Affinity's AI connector isn't reachable at http://localhost:6767/sse. Open Affinity and "
               "switch on Settings > AI connector (it can only be enabled inside the app), then retry.")


class AffinityError(RuntimeError):
    pass


class Client:
    """Minimal MCP-over-SSE client (stdlib only). One instance = one session."""

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout
        self.events: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.pending: dict[int, "queue.Queue[dict]"] = {}
        self.next_id = 1
        self.post_path: str | None = None
        self.server: dict = {}
        self._conn: http.client.HTTPConnection | None = None
        self._preamble = False

    # --- transport ------------------------------------------------------------------------
    def connect(self) -> "Client":
        last = None
        for host in (HOST, "::1", "127.0.0.1"):
            try:
                conn = http.client.HTTPConnection(host, PORT, timeout=5)
                conn.request("GET", "/sse", headers={"Accept": "text/event-stream"})
                resp = conn.getresponse()
                if resp.status != 200:
                    raise AffinityError(f"SSE connect failed: HTTP {resp.status}")
                self._conn, self._host = conn, host
                break
            except (OSError, AffinityError) as e:
                last = e
        else:
            raise AffinityError(f"{NOT_RUNNING} ({last})")
        self._conn.sock.settimeout(None)  # the stream idles between replies; only connect has a timeout
        threading.Thread(target=self._read, args=(resp,), daemon=True).start()
        deadline = time.time() + 10
        while self.post_path is None:
            if time.time() > deadline:
                raise AffinityError("no endpoint event from Affinity")
            time.sleep(0.02)
        err = None
        for v in VERSIONS:
            try:
                self.server = self.request("initialize", {"protocolVersion": v, "capabilities": {},
                                                          "clientInfo": {"name": "designassist", "version": "0.1"}})
                err = None
                break
            except AffinityError as e:
                err = e
                if "protocol" not in str(e).lower():
                    raise
        if err:
            raise err
        self.notify("notifications/initialized")
        return self

    def _read(self, resp) -> None:
        buf = b""
        while True:
            try:
                chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(1)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk.replace(b"\r", b"")
            while b"\n\n" in buf:
                raw, buf = buf.split(b"\n\n", 1)
                self._event(raw.decode("utf-8", "replace"))

    def _event(self, raw: str) -> None:
        event, data = "message", []
        for line in raw.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        payload = "\n".join(data)
        if event == "endpoint":
            u = urllib.parse.urlparse(payload)
            if u.netloc and u.hostname not in ("localhost", "127.0.0.1", "::1"):
                return  # never POST scripts to another host
            self.post_path = (u.path or "/") + (f"?{u.query}" if u.query else "")
            return
        if event != "message" or not payload:
            return
        try:
            msg = json.loads(payload)
        except ValueError:
            return
        q = self.pending.get(msg.get("id")) if isinstance(msg, dict) else None
        if q is not None:
            q.put(msg)

    def _post(self, body: dict) -> None:
        conn = http.client.HTTPConnection(self._host, PORT, timeout=30)
        conn.request("POST", self.post_path, body=json.dumps(body).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        r.read()
        conn.close()
        if r.status not in (200, 202, 204):
            raise AffinityError(f"POST {body.get('method')} failed: HTTP {r.status} (session expired? retry)")

    def request(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        rid = self.next_id
        self.next_id += 1
        q: "queue.Queue[dict]" = queue.Queue()
        self.pending[rid] = q
        try:
            self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
            try:
                msg = q.get(timeout=timeout or self.timeout)
            except queue.Empty:
                raise AffinityError(f"{method}: no answer from Affinity in {timeout or self.timeout:.0f}s")
        finally:
            self.pending.pop(rid, None)
        if msg.get("error"):
            e = msg["error"]
            raise AffinityError(f"{method}: {e.get('message')} {json.dumps(e.get('data')) if e.get('data') else ''}".strip())
        return msg.get("result", {})

    def notify(self, method: str, params: dict | None = None) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass

    # --- tools ----------------------------------------------------------------------------
    def tool(self, name: str, args: dict | None = None, timeout: float | None = None) -> dict:
        return self.request("tools/call", {"name": name, "arguments": args or {}}, timeout)

    def text(self, name: str, args: dict | None = None, timeout: float | None = None) -> str:
        res = self.tool(name, args, timeout)
        out = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        if res.get("isError"):
            raise AffinityError(out or f"{name} failed")
        return out

    def preamble(self) -> str:
        # Affinity occasionally answers "File not found" while it's busy (e.g. rescanning fonts just
        # installed): retry a few times before giving up
        for attempt in range(4):
            try:
                txt = self.text("read_sdk_documentation_topic", {"filename": "preamble"})
                break
            except AffinityError:
                if attempt == 3:
                    raise
                time.sleep(1.5)
        self._preamble = True
        return txt

    def run(self, script: str, timeout: float | None = None) -> str:
        """Execute JS in Affinity; returns everything it console.logged."""
        if not self._preamble:
            self.preamble()
        out = self.text("execute_script", {"script": script}, timeout)
        if out.lstrip().startswith("ERROR"):
            raise AffinityError(out.strip())
        return out

    def run_json(self, script: str, timeout: float | None = None):
        """Run a script that logs one line `@@DA@@<json>`; returns the parsed json."""
        out = self.run(script, timeout)
        for line in reversed(out.splitlines()):
            if line.startswith("@@DA@@"):
                return json.loads(line[6:])
        raise AffinityError("script finished without a result line:\n" + out[-2000:])

    def render(self, out: Path, spread: int = 0, uuid: str | None = None) -> Path:
        if uuid is None:
            uuid = self.run_json(f"{JS_HEAD}\nconsole.log('@@DA@@' + JSON.stringify(app.documents.current.sessionUuid));")
        res = self.tool("render_spread", {"document_session_uuid": uuid, "spread_index": spread})
        for c in res.get("content", []):
            if c.get("type") == "image":
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(base64.b64decode(c["data"]))
                return out
        raise AffinityError("render_spread returned no image: " + json.dumps(res)[:400])


    def export(self, uuid: str, path: Path, preset: str, artboard_id: str | None = None) -> Path:
        """Export a document (or one artboard) with an Affinity export preset ("PNG", "PDF/X-4",
        "PDF (press ready)", "PSD (preserve editability)", "Canva Design"...). `path` must be under the
        Desktop (Affinity's script sandbox)."""
        area = "FileExportArea.createForWholeDocument()"
        pick = ""
        if artboard_id:
            pick = (f" const ab = d.currentSpread.children.toArray().find(n => {{ try {{ return n.userDescription === {json.dumps(artboard_id)}; }} catch (e) {{ return false; }} }});"
                    " if (!ab) throw new Error('artboard not found');")
            area = "(ab.artboardInterface ? FileExportArea.createForArtboard(ab.artboardInterface) : FileExportArea.createForSelection(ab.selfSelection))"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.run_json(
            f"{JS_HEAD}\nconst {{ FileExportOptions, FileExportArea }} = require('/document');"
            f" const d = app.documents.all.find(x => x.sessionUuid === {json.dumps(uuid)});"
            f" if (!d) throw new Error('document not open');{pick}"
            f" d.export({json.dumps(path.as_posix())}, FileExportOptions.createWithPresetName({json.dumps(preset)}), {area}, null);"
            " console.log('@@DA@@1');", 300)
        if not path.exists():
            raise AffinityError(f"Affinity reported no error but {path.name} wasn't written")
        return path


JS_HEAD = "const { app } = require('/application');"


def session(timeout: float = 120.0) -> Client:
    return Client(timeout).connect()


def reachable() -> bool:
    try:
        c = http.client.HTTPConnection(HOST, PORT, timeout=1.5)
        c.request("GET", "/sse", headers={"Accept": "text/event-stream"})
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except OSError:
        return False


def installed() -> str | None:
    import os
    import sys

    if sys.platform == "darwin":
        p = Path("/Applications/Affinity.app")
        if p.exists():
            import plistlib

            info = plistlib.loads((p / "Contents/Info.plist").read_bytes())
            return f"{p} ({info.get('CFBundleShortVersionString')})"
        return None
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("LOCALAPPDATA", "")):
            for name in ("Affinity/Affinity/Affinity.exe", "Affinity/Affinity.exe"):
                if base and (Path(base) / name).exists():
                    return str(Path(base) / name)
        return None
    return None


def close_script(uuids: list[str], discard: bool = False) -> str:
    """Close only these documents (by session uuid). Unsaved changes are kept unless discard: a dirty
    document is saved first when it has a path, else left open and reported."""
    return (f"{JS_HEAD}\nconst mine = {json.dumps(uuids)}; const discard = {json.dumps(bool(discard))};"
            " const res = {closed: [], kept: []};"
            " for (const d of [...app.documents.all]) { if (!mine.includes(d.sessionUuid)) continue;"
            "   if (d.isDirty && !discard) { if (d.path) { d.save(); } else { res.kept.push(d.title); continue; } }"
            "   res.closed.push(d.title); d.close(); }"
            " console.log('@@DA@@' + JSON.stringify(res));")


def desktop_stage() -> Path:
    """Folder Affinity scripts may read/write (Desktop only)."""
    d = Path.home() / "Desktop" / "designassist-affinity"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- CLI --------------------------------------------------------------------------------------

def cmd_affinity(a):
    if a.action == "status":
        res = {"installed": installed(), "connector": reachable()}
        if res["connector"]:
            c = session(30)
            try:
                res["server"] = c.server.get("serverInfo")
                res["environment"] = c.run_json(
                    f"{JS_HEAD}\nlet env={{}}; try {{ const {{ Environment }} = require('/environment');"
                    " env = {permissions: Environment.permissions, roots: Environment.fileSystemRoots,"
                    " sdk: Environment.sdkVersionStr}; } catch (e) { env = {error: String(e)}; }"
                    " env.documents = app.documents.all.map(d => d.title); env.desktop = app.userDesktopPath;"
                    " console.log('@@DA@@' + JSON.stringify(env));")
            finally:
                c.close()
        else:
            res["next"] = NOT_RUNNING
        return res
    if a.action == "run":
        import sys

        code = sys.stdin.read() if a.target in (None, "-") else Path(a.target).read_text(encoding="utf-8")
        c = session(a.timeout)
        try:
            return c.run(code, a.timeout)
        finally:
            c.close()
    if a.action == "docs":
        c = session(60)
        try:
            c.preamble()
            if not a.target:
                return c.text("list_sdk_documentation")
            if a.target == "dump":
                from .project import CACHE

                d = CACHE / "affinity" / "sdk-docs"
                d.mkdir(parents=True, exist_ok=True)
                names = [n.strip() for n in c.text("list_sdk_documentation").replace("\n", ",").split(",") if n.strip()]
                saved = []
                for n in names:
                    try:
                        txt = c.text("read_sdk_documentation_topic", {"filename": n})
                    except AffinityError:
                        continue
                    (d / n.replace("/", "__")).write_text(txt, encoding="utf-8")
                    saved.append(n)
                return {"dir": str(d), "topics": len(saved)}
            return c.text("read_sdk_documentation_topic", {"filename": a.target})
        finally:
            c.close()
    if a.action == "render":
        from .project import Project

        out = Path(a.out) if a.out else (Project(a.target).path("work", "affinity", "render.jpg") if a.target
                                         else Path("affinity-render.jpg"))
        c = session(60)
        try:
            return {"file": str(c.render(out, a.spread))}
        finally:
            c.close()
    if a.action in ("open", "script"):
        from . import affinity_build as B
        from .project import Project

        if not a.target:
            raise SystemExit("da affinity open <project>")
        return B.build(Project(a.target), a.artboard, live=a.action == "open", save=not a.no_save)
    if a.action == "close":
        from .project import Project, read_json

        if not a.target:
            raise SystemExit("da affinity close <project>: closes the documents `da affinity open` built for it")
        pr = Project(a.target)
        built = read_json(pr.path("output", "affinity", f"{pr.name}-affinity-built.json"), {}) or {}
        uuids = [d["uuid"] for d in built.get("docs", [])]
        if not uuids:
            return {"closed": 0, "note": "no Affinity build recorded for this project"}
        if a.discard and not a.force:
            # never drop edits the user made in Affinity: diff against the build snapshot first
            from . import affinity_build as B

            try:
                edits = B.pull(pr, dry_run=True)["changes"]
            except SystemExit:
                edits = []  # documents not open any more: nothing to lose
            if edits:
                raise SystemExit("the Affinity documents have edits not in design.json: "
                                 + "; ".join(e["layer"] + " " + ", ".join(k for k in e if k != "layer") for e in edits)
                                 + ". Run `da affinity pull " + pr.name + "` first (or --force to drop them)")
        c = session(60)
        try:
            return c.run_json(close_script(uuids, a.discard))
        finally:
            c.close()
    if a.action == "export":
        from . import affinity_build as B
        from .project import Project

        if not a.target:
            raise SystemExit("da affinity export <project> --preset png|pdf|print|pdfx4|psd|svg|canva|<Affinity preset name>")
        return B.export(Project(a.target), a.preset, a.artboard)
    if a.action in ("read", "pull"):
        from . import affinity_build as B
        from .project import Project

        if a.action == "read":
            return B.read_current()
        return B.pull(Project(a.target), dry_run=a.dry_run)
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("affinity", help="Affinity (Canva) live: status, open a design natively, render, read/pull edits, run JS")
    p.add_argument("action", choices=["status", "open", "script", "render", "read", "pull", "export", "close", "run", "docs"])
    p.add_argument("target", nargs="?", help="project (open/script/render/pull), a .js file (run), a doc topic or 'dump' (docs)")
    p.add_argument("--artboard", nargs="*")
    p.add_argument("--spread", type=int, default=0)
    p.add_argument("--out")
    p.add_argument("--no-save", action="store_true", help="open: leave the document unsaved in Affinity")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--discard", action="store_true", help="close: drop unsaved changes in those documents "
                   "(refused while they hold edits `pull` would bring back)")
    p.add_argument("--force", action="store_true", help="close --discard: drop them even when they hold edits")
    p.add_argument("--preset", default="png", help="export: png jpg pdf print pdfx4 psd svg canva webp tiff-cmyk, or any Affinity preset name")
    p.add_argument("--timeout", type=float, default=180.0)
    def run(a):
        # a connector that is off (Affinity restarted / updated) is the common case: say so, no traceback
        try:
            return cmd_affinity(a)
        except AffinityError as e:
            raise SystemExit(f"da affinity {a.action}: {e}") from None

    p.set_defaults(func=run)
