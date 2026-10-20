"""UI / web work: HTML pages built by the agent, screenshotted with a headless Chromium.

projects/<p>/web/<name>/index.html   the page (plain HTML + CSS; no CDN, so it renders offline)
projects/<p>/web/<name>/tokens.css   CSS variables + @font-face from the design tokens / brand kit
projects/<p>/web/<name>/fonts/       copies of the font files the tokens use
output/web/<name>-<W>x<H>.png        `da web shot`

Full-page shots take two passes: the page is loaded once (through a copy with a <base> tag
and a measuring script, written to work/, so the user's files are never touched) to read its
height, then captured at that height.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .project import Project

DEFAULT_SIZES = "1440x900,390x844"


def _browser() -> str:
    from .doctor import find_browser

    b = find_browser()
    if not b:
        raise SystemExit("no Chromium-family browser found (Chrome, Edge, Brave, Chromium); install one or set DA_BROWSER")
    return b


def _run(browser: str, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    headless = "--headless" if "headless-shell" in Path(browser).name else "--headless=new"
    with tempfile.TemporaryDirectory(prefix="da-chrome-") as prof:  # never touch the user's browser profile
        cmd = [browser, headless, "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
               "--disable-extensions", "--mute-audio", f"--user-data-dir={prof}", "--run-all-compositor-stages-before-draw",
               "--virtual-time-budget=4000", *args]
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise SystemExit(f"{Path(browser).name} headless did not finish in {timeout}s. Point DA_BROWSER at Chrome/Edge/"
                             "Chromium, or install a headless shell: `npx playwright install chromium-headless-shell`")


# --dump-dom prints right after load (timers only run inside --virtual-time-budget), so measure synchronously
MEASURE = ("<script>(function(){function m(){var h=Math.max(document.documentElement.scrollHeight,"
           "document.body?document.body.scrollHeight:0);document.documentElement.setAttribute('data-da-height',"
           "String(Math.ceil(h)));}m();addEventListener('load',m);if(document.fonts){document.fonts.ready.then(m);}})();</script>")


def _staged(html: Path, work: Path, measure: bool) -> Path:
    """Copy of the page in work/ with a <base> pointing back at its folder (relative assets keep working)."""
    src = html.read_text(encoding="utf-8")
    base = f'<base href="{html.parent.resolve().as_uri()}/">'
    if re.search(r"<head[^>]*>", src, re.I):
        src = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + base, src, count=1, flags=re.I)
    else:
        src = base + src
    if measure:
        src = re.sub(r"(</body>)", MEASURE + r"\1", src, count=1, flags=re.I) if re.search(r"</body>", src, re.I) else src + MEASURE
    work.mkdir(parents=True, exist_ok=True)
    out = work / f".shot-{html.parent.name}-{html.stem}{'-m' if measure else ''}.html"
    out.write_text(src, encoding="utf-8")
    return out


def page_height(browser: str, page: Path, width: int, height: int) -> int:
    r = _run(browser, [f"--window-size={width},{height}", "--dump-dom", page.as_uri()])
    m = re.search(r'data-da-height="(\d+)"', r.stdout)
    return int(m.group(1)) if m else height


def _absolute_refs(page: Path) -> list[str]:
    """Root-relative asset paths ("/fonts/x.css") a file:// load can't resolve."""
    try:
        text = page.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return sorted(set(re.findall(r'(?:src|href)="(/[^/"][^"]*)"', text)))[:5]


def _serve(root: Path):
    """A throwaway local http server for `root` (port picked by the OS). Returns (base_url, stop)."""
    import functools
    import http.server
    import threading

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def stop():
        srv.shutdown()
        srv.server_close()
    return f"http://127.0.0.1:{srv.server_address[1]}", stop


def shot(project: Project, html: str, sizes: str = DEFAULT_SIZES, full_page: bool = False, out: str | None = None,
         scale: float = 1.0, root: str | None = None) -> dict:
    from PIL import Image

    if re.match(r"https?://", html):  # a served page (absolute asset paths, a dev server, a live site)
        return _shot_url(project, html, sizes, out, scale)
    if root:
        # a site page with root-relative assets: serve the site's public folder and shoot the URL
        base = Path(root).expanduser().resolve()
        page = Path(html).expanduser()
        page = (page if page.is_absolute() else (base / html if (base / html).exists() else project.path(html))).resolve()
        try:
            rel = page.relative_to(base).as_posix()
        except ValueError:
            raise SystemExit(f"{page} isn't inside --root {base}") from None
        url, stop = _serve(base)
        try:
            res = _shot_url(project, f"{url}/{rel}", sizes, out, scale)
        finally:
            stop()
        res["page"] = str(page)
        return res
    page = Path(html)
    if not page.is_absolute():
        page = project.path(html) if project.path(html).exists() else (project.path("web", html, "index.html")
                                                                        if project.path("web", html, "index.html").exists() else page.resolve())
    if page.is_dir():
        page = page / "index.html"
    if not page.exists():
        raise SystemExit(f"page not found: {html}")
    browser = _browser()
    work = project.path("work", "web")
    out_dir = project.path(out) if out else project.path("output", "web")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = page.parent.name if page.name == "index.html" else page.stem
    results = []
    staged = _staged(page, work, False)
    measured = _staged(page, work, True) if full_page else None
    for s in sizes.split(","):
        w, h = (int(v) for v in s.lower().strip().split("x"))
        H = max(h, page_height(browser, measured, w, h)) if measured else h
        f = out_dir / f"{name}-{w}x{h}{'-full' if full_page else ''}{f'@{scale:g}x' if scale != 1 else ''}.png"
        f.unlink(missing_ok=True)
        r = _run(browser, [f"--window-size={w},{H}", f"--force-device-scale-factor={scale:g}", f"--screenshot={f}",
                           staged.as_uri()])
        if not f.exists():
            raise SystemExit(f"screenshot failed ({Path(browser).name}): {(r.stderr or r.stdout).strip()[-400:]}")
        want = (round(w * scale), round(H * scale))
        with Image.open(f) as im:
            got = im.size
            if got != want and got[0] >= want[0] and got[1] >= want[1]:
                im.crop((0, 0, *want)).save(f)
                got = want
        results.append({"size": f"{w}x{h}", "file": project.rel(f), "px": list(got), "page_height": H})
    for t in (staged, measured):
        if t:
            t.unlink(missing_ok=True)
    res = {"page": project.rel(page), "browser": Path(browser).name, "shots": results}
    refs = _absolute_refs(page)
    if refs:
        res["warning"] = (f"the page loads root-relative assets ({', '.join(refs)}): from a file they're missing (blank or "
                          "unstyled shot). Pass --root <the site's public folder>.")
    return res


def _shot_url(project: Project, url: str, sizes: str, out: str | None, scale: float) -> dict:
    """Viewport screenshots of a URL (full-page measuring needs a local file we can inject into)."""
    from PIL import Image
    from urllib.parse import urlparse

    browser = _browser()
    out_dir = project.path(out) if out else project.path("output", "web")
    out_dir.mkdir(parents=True, exist_ok=True)
    u = urlparse(url)
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", (Path(u.path).stem or u.netloc)).strip("-") or "page"
    results = []
    for s in sizes.split(","):
        w, h = (int(v) for v in s.lower().strip().split("x"))
        f = out_dir / f"{name}-{w}x{h}{f'@{scale:g}x' if scale != 1 else ''}.png"
        f.unlink(missing_ok=True)
        r = _run(browser, [f"--window-size={w},{h}", f"--force-device-scale-factor={scale:g}", f"--screenshot={f}", url])
        if not f.exists():
            raise SystemExit(f"screenshot failed ({Path(browser).name}): {(r.stderr or r.stdout).strip()[-400:]}")
        with Image.open(f) as im:
            got = im.size
        results.append({"size": f"{w}x{h}", "file": project.rel(f), "px": list(got)})
    return {"page": url, "browser": Path(browser).name, "shots": results}


# --- tokens.css ------------------------------------------------------------------------------

def tokens_css(project: Project, dest: Path) -> str:
    """CSS variables for every colour/font token, @font-face for the font files (copied to dest/fonts)."""
    from . import colors as C
    from . import design as D
    from . import fonts as F

    d = D.load(project) if D.path(project).exists() else D.empty(project.name, project.settings.get("client"))
    ctx = D.context(project, d)
    lines = [":root {"]
    for k in ctx.colors:
        try:
            c = C.parse(f"${k}", ctx.colors)
        except C.ColorError:
            continue
        if c is None:
            continue
        val = c.hex if c.a == 1 else f"rgba({c.r}, {c.g}, {c.b}, {c.a:.3g})"
        lines.append(f"  --color-{k}: {val};")
    faces, seen = [], set()
    (dest / "fonts").mkdir(parents=True, exist_ok=True)
    for k, spec in ctx.fonts.items():
        spec = spec if isinstance(spec, dict) else {"family": spec}
        fam = spec.get("family", "Montserrat")
        w = int(spec.get("weight", 400))
        ref = F.resolve_or_fallback(fam, w, bool(spec.get("italic")), ctx.font_dirs())
        generic = "serif" if any(s in ref.family.lower() for s in ("serif", "cinzel", "garamond", "playfair")) and "sans" not in ref.family.lower() else "sans-serif"
        lines.append(f'  --font-{k}: "{ref.family}", system-ui, {generic};')
        lines.append(f"  --weight-{k}: {w};")
        key = (ref.path, ref.weight if not ref.location else "var")
        if key in seen:
            continue
        seen.add(key)
        src = Path(ref.path)
        target = dest / "fonts" / src.name
        if not target.exists():
            shutil.copy2(src, target)
        fmt = {".otf": "opentype", ".ttf": "truetype", ".ttc": "collection"}.get(src.suffix.lower(), "truetype")
        weight = "100 900" if ref.location else str(ref.weight)
        faces.append(f'@font-face {{ font-family: "{ref.family}"; src: url("fonts/{src.name}") format("{fmt}"); '
                     f'font-weight: {weight}; font-style: {"italic" if ref.italic else "normal"}; font-display: swap; }}')
    lines += ["  --radius: 14px;", "  --space: 8px;", "}"]
    css = "/* generated by `da web tokens` from design.json tokens / brand kit; edit tokens, not this file */\n"
    css += "\n".join(faces) + "\n" + "\n".join(lines) + "\n"
    (dest / "tokens.css").write_text(css, encoding="utf-8")
    return css


TEMPLATES = {
    "landing": """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="tokens.css">
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ font-family: var(--font-body); color: var(--color-ink); background: var(--color-paper); line-height: 1.5; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 0 24px; }}
  header {{ display: flex; justify-content: space-between; align-items: center; padding: 24px 0; }}
  .brand {{ font-family: var(--font-display); font-weight: var(--weight-display); font-size: 22px; }}
  nav a {{ color: inherit; text-decoration: none; margin-left: 28px; }}
  .hero {{ padding: 96px 0 120px; display: grid; gap: 28px; max-width: 760px; }}
  h1 {{ font-family: var(--font-display); font-weight: var(--weight-display); font-size: clamp(40px, 6vw, 76px); line-height: 1.02; letter-spacing: -0.02em; }}
  .lead {{ font-size: 20px; color: var(--color-muted); max-width: 560px; }}
  .btn {{ display: inline-block; background: var(--color-primary); color: var(--color-paper); padding: 16px 28px; border-radius: 999px; font-weight: 700; text-decoration: none; }}
  .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 24px; padding: 0 0 120px; }}
  .card {{ padding: 32px; border-radius: var(--radius); background: color-mix(in srgb, var(--color-primary) 6%, var(--color-paper)); }}
  .card h3 {{ font-family: var(--font-display); margin-bottom: 8px; }}
  footer {{ padding: 40px 0; color: var(--color-muted); font-size: 14px; }}
</style>
</head>
<body>
<div class="wrap">
  <header><div class="brand">{title}</div><nav><a href="#features">Recursos</a><a href="#contato">Contato</a></nav></header>
  <section class="hero">
    <h1>Headline clara sobre o benefício principal</h1>
    <p class="lead">Uma frase que explica o que é, para quem é e por que importa.</p>
    <p><a class="btn" href="#contato">Chamada para ação</a></p>
  </section>
  <section class="features" id="features">
    <div class="card"><h3>Benefício 1</h3><p>Descrição curta e concreta.</p></div>
    <div class="card"><h3>Benefício 2</h3><p>Descrição curta e concreta.</p></div>
    <div class="card"><h3>Benefício 3</h3><p>Descrição curta e concreta.</p></div>
  </section>
  <footer id="contato">© {title}</footer>
</div>
</body>
</html>
""",
    "screen": """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="tokens.css">
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ font-family: var(--font-body); color: var(--color-ink); background: var(--color-paper); min-height: 100vh; }}
  .bar {{ display: flex; align-items: center; justify-content: space-between; padding: 56px 20px 16px; }}
  .bar h1 {{ font-family: var(--font-display); font-weight: var(--weight-display); font-size: 28px; }}
  .avatar {{ width: 40px; height: 40px; border-radius: 50%; background: var(--color-primary); }}
  .list {{ padding: 8px 20px; display: grid; gap: 12px; }}
  .item {{ padding: 18px; border-radius: var(--radius); background: color-mix(in srgb, var(--color-ink) 5%, var(--color-paper)); display: flex; justify-content: space-between; }}
  .tab {{ position: fixed; bottom: 0; left: 0; right: 0; display: flex; justify-content: space-around; padding: 14px 0 34px; border-top: 1px solid color-mix(in srgb, var(--color-ink) 10%, transparent); background: var(--color-paper); }}
  .tab span.on {{ color: var(--color-primary); font-weight: 700; }}
</style>
</head>
<body>
  <div class="bar"><h1>{title}</h1><div class="avatar"></div></div>
  <div class="list">
    <div class="item"><span>Item 1</span><strong>R$ 49</strong></div>
    <div class="item"><span>Item 2</span><strong>R$ 89</strong></div>
    <div class="item"><span>Item 3</span><strong>R$ 129</strong></div>
  </div>
  <nav class="tab"><span class="on">Início</span><span>Buscar</span><span>Perfil</span></nav>
</body>
</html>
""",
    "email": """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="tokens.css">
<!-- email clients ignore <link> and CSS variables: before sending, inline the final values (the agent does this) -->
</head>
<body style="margin:0;background:#f2f2f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 0;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:var(--color-paper);font-family:var(--font-body);color:var(--color-ink);">
    <tr><td style="padding:32px;font-family:var(--font-display);font-weight:var(--weight-display);font-size:24px;">{title}</td></tr>
    <tr><td style="padding:0 32px 16px;font-size:34px;line-height:1.1;font-family:var(--font-display);font-weight:var(--weight-display);">Headline do e-mail</td></tr>
    <tr><td style="padding:0 32px 24px;font-size:16px;line-height:1.6;">Texto curto com a mensagem principal.</td></tr>
    <tr><td style="padding:0 32px 40px;"><a href="#" style="background:var(--color-primary);color:var(--color-paper);padding:14px 24px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;">Chamada para ação</a></td></tr>
  </table>
</td></tr></table>
</body>
</html>
""",
}


def new(project: Project, name: str, kind: str = "landing") -> dict:
    from .project import slug

    dest = project.path("web", slug(name))
    if (dest / "index.html").exists():
        raise SystemExit(f"{project.rel(dest / 'index.html')} exists; edit it (or pick another name)")
    dest.mkdir(parents=True, exist_ok=True)
    tokens_css(project, dest)
    lang = project.settings.get("language") or "pt-BR"
    (dest / "index.html").write_text(TEMPLATES[kind].format(title=name, lang=lang), encoding="utf-8")
    size = {"landing": "1440x900,390x844", "screen": "390x844", "email": "600x900"}[kind]
    return {"page": project.rel(dest / "index.html"), "tokens": project.rel(dest / "tokens.css"),
            "next": f"edit the page, then `uv run da web shot {project.name} {slug(name)} --sizes {size} --full-page`"}


def cmd_web(a):
    pr = Project(a.project)
    if a.action == "shot":
        if not a.page:
            raise SystemExit("usage: da web shot <project> <page.html | web name>")
        return shot(pr, a.page, a.sizes, a.full_page, a.out, a.scale, a.root)
    if a.action == "new":
        if not a.page:
            raise SystemExit("usage: da web new <project> <name> [--kind landing|screen|email]")
        return new(pr, a.page, a.kind)
    if a.action == "tokens":
        from .project import slug

        if not a.page:
            raise SystemExit("usage: da web tokens <project> <web name>")
        dest = pr.path("web", slug(a.page))
        dest.mkdir(parents=True, exist_ok=True)
        tokens_css(pr, dest)
        return {"tokens": pr.rel(dest / "tokens.css")}
    raise SystemExit(a.action)


def register(sub) -> None:
    p = sub.add_parser("web", help="UI/web: new <p> <name> | tokens <p> <name> | shot <p> <page> (headless Chromium)")
    p.add_argument("action", choices=["new", "tokens", "shot"])
    p.add_argument("project")
    p.add_argument("page", nargs="?", help="web page name (web/<name>/index.html) or an .html path")
    p.add_argument("--kind", choices=list(TEMPLATES), default="landing")
    p.add_argument("--sizes", default=DEFAULT_SIZES, help="viewport sizes, e.g. 1440x900,390x844")
    p.add_argument("--full-page", action="store_true", help="capture the whole page height")
    p.add_argument("--scale", type=float, default=1.0, help="device scale factor (2 = retina)")
    p.add_argument("--out", help="output folder, project-relative (default output/web)")
    p.add_argument("--root", help="shot: serve this folder (a site's public/) so root-relative assets (/css/x.css) load")
    p.set_defaults(func=cmd_web)
