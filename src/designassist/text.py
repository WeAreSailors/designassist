"""Text engine: shaping (HarfBuzz), line breaking, autofit, and glyph outlines (fontTools).

One engine for every output, so the PNG preview, the PDF, the outlined SVG and the positions
handed to Photoshop/Illustrator agree. Layout runs in artboard units.

Line box model (same as Figma): each line is `size * line_height` tall and the glyph box
(ascender..descender) is centred in it, so the first baseline is
  top + (line_h - (asc - desc) * size) / 2 + asc * size.
Tracking is in 1/1000 em, added after every glyph except a line's last (Adobe convention).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import fonts as F


# --- fonts ------------------------------------------------------------------------------------

class _Font:
    def __init__(self, ref: F.FontRef):
        import uharfbuzz as hb
        from fontTools.ttLib import TTFont

        self.ref = ref
        blob = hb.Blob.from_file_path(ref.path)
        self.hb = hb.Font(hb.Face(blob, ref.index))
        if ref.location:
            self.hb.set_variations(ref.loc)
        self.tt = TTFont(ref.path, fontNumber=ref.index, lazy=True)
        self.upem = self.tt["head"].unitsPerEm
        self.hb.scale = (self.upem, self.upem)
        os2, hhea = self.tt["OS/2"], self.tt["hhea"]
        if os2.fsSelection & (1 << 7) or not hhea.ascent:  # USE_TYPO_METRICS
            self.asc, self.desc = os2.sTypoAscender, os2.sTypoDescender
        else:
            self.asc, self.desc = hhea.ascent, hhea.descent
        self.cap = getattr(os2, "sCapHeight", 0) or int(self.asc * 0.7)
        self.xh = getattr(os2, "sxHeight", 0) or int(self.asc * 0.5)
        self.order = self.tt.getGlyphOrder()
        self._gs = None
        self.cmap = self.tt.getBestCmap() or {}  # codepoint -> glyph NAME
        self.space_gid = self.tt.getGlyphID(self.cmap[32]) if 32 in self.cmap else -1

    @property
    def glyphset(self):
        if self._gs is None:
            self._gs = self.tt.getGlyphSet(location=self.ref.loc or None) if self.ref.location else self.tt.getGlyphSet()
        return self._gs

    def shape(self, text: str, features: dict | None = None) -> list[tuple[int, int, int, int, int]]:
        """[(glyph id, cluster, x_advance, x_offset, y_offset)] in font units."""
        import uharfbuzz as hb

        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, features or {"kern": True, "liga": True})
        return [(i.codepoint, i.cluster, p.x_advance, p.x_offset, p.y_offset)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]


@lru_cache(maxsize=64)
def font(ref: F.FontRef) -> _Font:
    return _Font(ref)


@lru_cache(maxsize=20000)
def glyph_path(ref: F.FontRef, gid: int) -> str:
    """Glyph outline as SVG path data in font units, y up (flip when placing)."""
    from fontTools.pens.svgPathPen import SVGPathPen

    f = font(ref)
    pen = SVGPathPen(f.glyphset)
    f.glyphset[f.order[gid]].draw(pen)
    return pen.getCommands()


# --- layout model -------------------------------------------------------------------------

@dataclass
class Style:
    ref: F.FontRef
    size: float
    color: object  # colors.Color | None
    tracking: float = 0.0  # 1/1000 em
    highlight: dict | None = None  # accent-only box behind the span
    stroke: dict | None = None
    features: tuple = ()

    @property
    def track(self) -> float:
        return self.tracking / 1000 * self.size


@dataclass
class Glyph:
    gid: int
    x: float  # pen position, artboard units
    y: float  # baseline
    adv: float


@dataclass
class Run:
    text: str
    style: Style
    x: float = 0.0
    width: float = 0.0
    glyphs: list = field(default_factory=list)
    missing: list = field(default_factory=list)  # characters the font has no glyph for


@dataclass
class Line:
    runs: list
    width: float
    baseline: float = 0.0
    x: float = 0.0
    hard: bool = False  # ended by "\n" or end of text (not justified)


@dataclass
class TextLayout:
    lines: list
    size: float  # final base size (after autofit)
    box: tuple  # x, y, w, h actually used
    content_w: float
    content_h: float
    overflow: bool
    truncated: bool
    missing_glyphs: list
    fonts: list  # FontRefs used
    fallback_fonts: list
    styles: tuple = ()  # (base Style, accent Style) at the final size: exporters that rebuild text natively
    text: str = ""  # the text after case transform, with **accent** markup and "\n" breaks

    def to_json(self) -> dict:
        return {"size": round(self.size, 3), "lines": [
            {"text": "".join(r.text for r in ln.runs), "x": round(ln.x, 2), "baseline": round(ln.baseline, 2),
             "width": round(ln.width, 2)} for ln in self.lines],
            "box": [round(v, 2) for v in self.box], "content": [round(self.content_w, 2), round(self.content_h, 2)],
            "overflow": self.overflow, "truncated": self.truncated, "missing_glyphs": self.missing_glyphs,
            "fonts": sorted({f"{r.family} {r.weight}{' italic' if r.italic else ''}" for r in self.fonts}),
            "fallback_fonts": self.fallback_fonts}


# --- markup -------------------------------------------------------------------------------

def apply_case(s: str, case: str | None) -> str:
    if case == "upper":
        return s.upper()
    if case == "lower":
        return s.lower()
    if case == "title":
        return re.sub(r"\w[\w'’]*", lambda m: m.group(0)[:1].upper() + m.group(0)[1:], s)
    return s


def parse_markup(text: str) -> list[tuple[str, bool]]:
    """'Get **50% off** now' -> [('Get ', False), ('50% off', True), (' now', False)]."""
    parts = text.split("**")
    return [(p, i % 2 == 1) for i, p in enumerate(parts) if p]


# --- engine -------------------------------------------------------------------------------

def _shape_piece(text: str, st: Style) -> Run:
    f = font(st.ref)
    feats = {"kern": True, "liga": True, **dict(st.features)}
    sc = st.size / f.upem
    run = Run(text, st)
    x = 0.0
    for gid, cl, adv, xo, yo in f.shape(text, feats):
        if gid == 0 and cl < len(text) and not text[cl].isspace():
            run.missing.append(text[cl])
        run.glyphs.append(Glyph(gid, x + xo * sc, -yo * sc, adv * sc + st.track))
        x += adv * sc + st.track
    run.width = x
    return run


def _tokens(pieces: list[tuple[str, Style]]):
    """Split styled pieces into words and spaces; a word may span several styles."""
    words: list[list[tuple[str, Style]]] = []  # each item: word pieces; separators marked
    cur: list[tuple[str, Style]] = []
    for text, st in pieces:
        for tok in re.split(r"(\n| +)", text):
            if tok == "":
                continue
            if tok == "\n" or tok.startswith(" "):
                if cur:
                    words.append(cur)
                    cur = []
                words.append([(tok, st)])
            else:
                cur.append((tok, st))
    if cur:
        words.append(cur)
    return words


def _layout_lines(pieces: list[tuple[str, Style]], wrap_w: float | None) -> tuple[list[list[Run]], set[int]]:
    """Greedy word wrap. Returns the lines and the indexes of lines ended by a hard break."""
    lines: list[list[Run]] = [[]]
    width = 0.0
    hard_breaks: set[int] = set()
    pending_space: list[Run] = []
    for word in _tokens(pieces):
        tok, st = word[0]
        if tok == "\n":
            hard_breaks.add(len(lines) - 1)
            lines.append([])
            width, pending_space = 0.0, []
            continue
        if tok.startswith(" "):
            if lines[-1]:
                pending_space = [_shape_piece(tok, st)]
            continue
        runs = [_shape_piece(t, s) for t, s in word]
        ww = sum(r.width for r in runs)
        sw = sum(r.width for r in pending_space)
        if wrap_w is not None and lines[-1] and width + sw + ww > wrap_w + 1e-6:
            lines.append(runs)
            width = ww
        else:
            lines[-1].extend(pending_space + runs)
            width += sw + ww
        pending_space = []
    return lines, hard_breaks


def _merge(runs: list[Run]) -> list[Run]:
    """Adjacent runs with the same style become one (fewer elements downstream)."""
    out: list[Run] = []
    for r in runs:
        if out and out[-1].style is r.style:
            prev = out[-1]
            off = prev.width
            prev.glyphs += [Glyph(g.gid, g.x + off, g.y, g.adv) for g in r.glyphs]
            prev.text += r.text
            prev.width += r.width
            prev.missing += r.missing
        else:
            out.append(Run(r.text, r.style, 0, r.width, list(r.glyphs), list(r.missing)))
    return out


def layout(layer: dict, ctx, unit: str = "px", dpi: float = 72, ox: float = 0.0, oy: float = 0.0) -> TextLayout:
    """Lay out a text layer. ctx = design.Context (fonts, colours). Coordinates are absolute
    (ox, oy = parent group origin)."""
    from .design import length

    L = lambda v, d=0.0: length(v, unit, dpi) if v is not None else d  # noqa: E731
    base_size = L(layer.get("size"), 0) or L("24pt" if unit != "px" else 48)
    x, y = ox + L(layer.get("x")), oy + L(layer.get("y"))
    wrap_w = L(layer["w"]) if layer.get("w") else None
    box_h = L(layer["h"]) if layer.get("h") else None
    lh_mult = float(layer.get("line_height", 1.2))
    align = layer.get("align", "left")
    valign = layer.get("valign", "top")
    max_lines = layer.get("max_lines")
    text = apply_case(layer.get("text", ""), layer.get("case"))
    spec = ctx.font_spec(layer)
    accent = layer.get("accent") or {}
    acc_spec = ctx.font_spec({"font": accent.get("font", layer.get("font", "$body")),
                              "weight": accent.get("weight", spec["weight"]),
                              "italic": accent.get("italic", spec["italic"])})
    color = ctx.color(layer.get("color", layer.get("fill", "$ink")))
    acc_color = ctx.color(accent["color"]) if "color" in accent else (
        ctx.color("$accent") if "accent" in ctx.colors else color)
    dirs = ctx.font_dirs()
    fallback = []

    def ref_for(s: dict) -> F.FontRef:
        r = F.resolve_or_fallback(s["family"], float(s["weight"]), bool(s["italic"]), dirs)
        if r.fallback:
            fallback.append(s["family"])
        return r

    base_ref, acc_ref = ref_for(spec), ref_for(acc_spec)
    feats = tuple(sorted((layer.get("features") or {}).items()))

    made: dict = {}

    def attempt(size: float):
        st = Style(base_ref, size, color, float(layer.get("tracking", 0)), None, layer.get("stroke"), feats)
        ast = Style(acc_ref, size * float(accent.get("scale", 1)), acc_color,
                    float(accent.get("tracking", layer.get("tracking", 0))), accent.get("highlight"),
                    accent.get("stroke", layer.get("stroke")), feats)
        made[size] = (st, ast)
        pieces = [(t, ast if is_acc else st) for t, is_acc in parse_markup(text)]
        raw, hard = _layout_lines(pieces, wrap_w)
        lines = [Line(_merge(r), 0.0, hard=(i in hard or i == len(raw) - 1)) for i, r in enumerate(raw)]
        for ln in lines:
            # a line's last glyph carries no tracking (Adobe convention)
            if ln.runs and ln.runs[-1].glyphs:
                last = ln.runs[-1]
                last.width -= last.style.track
            ln.width = sum(r.width for r in ln.runs)
        lh = size * lh_mult
        return lines, lh

    size = base_size
    lines, lh = attempt(size)
    content_h = lh * len(lines)

    def fits(lns, lh_):
        ok_h = box_h is None or lh_ * len(lns) <= box_h + 1e-6
        ok_n = not max_lines or len(lns) <= max_lines
        long_word = wrap_w is not None and any(ln.width > wrap_w + 1e-6 for ln in lns)
        return ok_h and ok_n and not long_word

    if layer.get("autofit") and not fits(lines, lh):
        lo = L(layer.get("min_size"), 0) or base_size * 0.3
        hi = base_size
        best = None
        for _ in range(18):
            mid = (lo + hi) / 2
            lns, lh_ = attempt(mid)
            if fits(lns, lh_):
                best, lo = (mid, lns, lh_), mid
            else:
                hi = mid
            if hi - lo < base_size * 0.005:
                break
        if best:
            size, lines, lh = best
        else:
            size = lo
            lines, lh = attempt(size)

    truncated = False
    if max_lines and len(lines) > max_lines:
        lines, truncated = lines[:max_lines], True
    content_w = max((ln.width for ln in lines), default=0.0)
    content_h = lh * len(lines)
    box_w = wrap_w if wrap_w is not None else content_w
    used_h = box_h if box_h is not None else content_h
    overflow = truncated or (box_h is not None and content_h > box_h + 1e-6) or (
        wrap_w is not None and content_w > wrap_w + 1e-6)

    f0 = font(base_ref)
    asc, desc = f0.asc / f0.upem * size, f0.desc / f0.upem * size
    top = y
    if box_h is not None and valign != "top":
        top = y + (box_h - content_h) * (0.5 if valign == "middle" else 1.0)
    missing: list[str] = []
    for i, ln in enumerate(lines):
        ln.baseline = top + i * lh + (lh - (asc - desc)) / 2 + asc
        if align == "center":
            ln.x = x + (box_w - ln.width) / 2
        elif align == "right":
            ln.x = x + box_w - ln.width
        else:
            ln.x = x
            if layer.get("optical") and ln.runs and ln.runs[0].glyphs:
                # optical alignment: the first glyph's ink, not its side bearing, sits on x
                ln.x -= _lsb(ln.runs[0].style.ref, ln.runs[0].glyphs[0].gid) * ln.runs[0].style.size
        extra_per_space = 0.0
        if align == "justify" and (not ln.hard or layer.get("justify_all")) and wrap_w is not None:
            spaces = sum(r.text.count(" ") for r in ln.runs)
            if spaces:
                extra_per_space = (box_w - ln.width) / spaces
                ln.width = box_w
        pen = ln.x
        for r in ln.runs:
            r.x = pen
            space_gid = font(r.style.ref).space_gid
            shift = 0.0
            for g in r.glyphs:
                g.x += pen + shift
                g.y += ln.baseline
                if extra_per_space and g.gid == space_gid:
                    shift += extra_per_space
            r.width += shift
            pen += r.width
            missing += r.missing
    used_fonts = list({base_ref, acc_ref} if "**" in text else {base_ref})
    return TextLayout(lines, size, (x, y, box_w, used_h), content_w, content_h, overflow, truncated,
                      sorted(set(missing)), used_fonts, sorted(set(fallback)), made.get(size, ()), text)


def ink_box(lay: TextLayout) -> tuple[float, float, float, float] | None:
    """Ink bounds of laid-out text (glyph outlines), in layout units."""
    from fontTools.pens.boundsPen import BoundsPen

    xs, ys = [], []
    for ln in lay.lines:
        for r in ln.runs:
            f = font(r.style.ref)
            sc = r.style.size / f.upem
            for g in r.glyphs:
                bp = BoundsPen(f.glyphset)
                f.glyphset[f.order[g.gid]].draw(bp)
                if bp.bounds:
                    x0, y0, x1, y1 = bp.bounds
                    xs += [g.x + x0 * sc, g.x + x1 * sc]
                    ys += [g.y - y1 * sc, g.y - y0 * sc]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


@lru_cache(maxsize=4096)
def _ink_y(ref: F.FontRef, gid: int) -> tuple[float, float] | None:
    """Vertical ink extent (bottom, top) of a glyph in em, y up; None for empty glyphs."""
    from fontTools.pens.boundsPen import BoundsPen

    f = font(ref)
    bp = BoundsPen(f.glyphset)
    f.glyphset[f.order[gid]].draw(bp)
    return (bp.bounds[1] / f.upem, bp.bounds[3] / f.upem) if bp.bounds else None


def highlight_runs(lay: "TextLayout") -> tuple[list, list]:
    """(every run, runs with an accent highlight): the ink each kind of highlight box must cover."""
    runs = [r for ln in lay.lines for r in ln.runs]
    return runs, [r for r in runs if r.style.highlight]


def highlight_box(spec: dict, x: float, baseline: float, width: float, size: float, ref, runs, L) -> tuple:
    """Box (x, y, w, h) behind one highlighted line or accent run, centred on the capitals (baseline to cap
    height): whatever ink of `runs` pokes out of that band (accents above Ã/É, a Q tail, Ç, descenders) grows
    the box by the same amount on both sides, so the words always sit in the middle of the box. Pass every run
    sharing this highlight so all lines get the same height. Without runs the overhang is 0.18 em.
    pad: numbers are fractions of the font size, strings are lengths ("12px")."""
    pad = spec.get("pad", [0.25, 0.08])
    px = L(pad[0]) if isinstance(pad[0], str) else float(pad[0]) * size
    py = L(pad[1]) if isinstance(pad[1], str) else float(pad[1]) * size
    f = font(ref) if ref else None
    cap = (f.cap / f.upem * size) if f else size * 0.7
    over = None
    for r in runs or ():
        for g in r.glyphs:
            ink = _ink_y(r.style.ref, g.gid)
            if ink:  # g.y is the line's baseline: ignored, runs span lines
                rc = cap * r.style.size / size
                over = max(over or 0.0, ink[1] * r.style.size - rc, -ink[0] * r.style.size)
    over = size * 0.18 if over is None else over
    top, bottom = baseline - cap - over - py, baseline + over + py
    return x - px, top, width + 2 * px, bottom - top


@lru_cache(maxsize=4096)
def _lsb(ref: F.FontRef, gid: int) -> float:
    """Left side bearing of a glyph's ink, in em (0 for empty glyphs)."""
    from fontTools.pens.boundsPen import BoundsPen

    f = font(ref)
    bp = BoundsPen(f.glyphset)
    f.glyphset[f.order[gid]].draw(bp)
    return (bp.bounds[0] / f.upem) if bp.bounds else 0.0


def run_path(run: Run) -> str:
    """SVG path data for a laid-out run, in artboard units."""
    f = font(run.style.ref)
    sc = run.style.size / f.upem
    parts = []
    for g in run.glyphs:
        d = glyph_path(run.style.ref, g.gid)
        if not d:
            continue
        parts.append(_transform_path(d, sc, g.x, g.y))
    return " ".join(parts)


_NUM = re.compile(r"[MLHVCSQTAZmlhvcsqtaz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _transform_path(d: str, sc: float, tx: float, ty: float) -> str:
    """Scale a y-up font-unit path (absolute M/L/C/Q/Z from SVGPathPen) to y-down units at (tx, ty)."""
    out = []
    toks = _NUM.findall(d)
    i, cmd = 0, None
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            out.append(t)
            i += 1
            continue
        if cmd in ("H",):
            out.append(f"{float(t) * sc + tx:.2f}")
            i += 1
        elif cmd in ("V",):
            out.append(f"{-float(t) * sc + ty:.2f}")
            i += 1
        else:
            px, py = float(toks[i]), float(toks[i + 1])
            out.append(f"{px * sc + tx:.2f} {-py * sc + ty:.2f}")
            i += 2
    return " ".join(out)
