from __future__ import annotations

import json
import struct

import pytest
from PIL import Image, ImageDraw

from designassist import colors as C
from designassist.cli import main
from conftest import make_photo


def _three_colour(path, cols=("#E30613", "#1F4FE0", "#FFD400"), shares=(0.5, 0.3, 0.2)):
    w, h = 300, 100
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    x = 0
    for c, s in zip(cols, shares):
        d.rectangle((x, 0, x + round(w * s) - 1, h), fill=c)
        x += round(w * s)
    im.save(path)
    return path


# --- colour -------------------------------------------------------------------------------------

def test_palette_recovers_colours_and_shares(tmp_path):
    from designassist.colortools import palette

    pal = palette(_three_colour(tmp_path / "p.png"), n=3)
    hexes = [e["hex"] for e in pal]
    assert hexes == ["#E30613", "#1F4FE0", "#FFD400"]  # sorted by share
    assert pal[0]["share"] == pytest.approx(0.5, abs=0.02)
    assert {e["role"] for e in pal} >= {"ink", "paper"}


def test_oklch_roundtrip_and_scale():
    from designassist.colortools import from_oklch, scale, to_oklch

    c = C.parse("#2B59FF")
    assert from_oklch(*to_oklch(c)).hex == "#2B59FF"
    sc = scale("#2B59FF")
    assert sc["500"] == "#2B59FF" and list(sc) == ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]
    Ls = [to_oklch(C.parse(v))[0] for v in sc.values()]
    assert all(a > b for a, b in zip(Ls, Ls[1:]))  # strictly darker each step
    assert Ls[0] > 0.95 and Ls[-1] < 0.35


def test_harmony_and_contrast_report():
    from designassist.colortools import contrast_report, harmony, to_oklch

    tri = harmony("#E30613", "triadic")
    assert len(tri) == 3 and tri[0] == "#E30613"
    hues = [to_oklch(C.parse(h))[2] for h in tri]
    assert abs(((hues[1] - hues[0]) % 360) - 120) < 3
    r = contrast_report("#777777", "#FFFFFF")
    assert r["ratio"] == pytest.approx(4.48, abs=0.01) and r["normal_text"] == "fail" and r["large_text"] == "AA"


def test_color_check_samples_what_is_behind_text(sample, capsys):
    from designassist.colortools import check

    res = check(sample)
    rows = {(r["layer"], r["fg"]): r for r in res["rows"]}
    assert rows[("cta-tx", "#FFFFFF")]["bg_median"] == "#E30613"  # white on the red pill, not on the photo
    assert rows[("title", "#FFD400")]["grade"] != "fail"
    # make the CTA text red on red: must fail
    d = json.loads(sample.path("design.json").read_text(encoding="utf-8"))
    d["artboards"][0]["layers"][3]["layers"][1]["color"] = "#E8202A"
    sample.path("design.json").write_text(json.dumps(d), encoding="utf-8")
    res2 = check(sample, ["post"])
    assert any(r["layer"] == "cta-tx" and r["grade"] == "fail" for r in res2["rows"])


# --- tokens -------------------------------------------------------------------------------------

def _read_ase(data: bytes) -> list[dict]:
    assert data[:4] == b"ASEF"
    major, minor, n = struct.unpack(">HHI", data[4:12])
    assert (major, minor) == (1, 0)
    pos, out = 12, []
    for _ in range(n):
        btype, blen = struct.unpack(">HI", data[pos:pos + 6])
        body = data[pos + 6:pos + 6 + blen]
        pos += 6 + blen
        if btype in (0xC001, 0x0001):
            nlen = struct.unpack(">H", body[:2])[0]
            name = body[2:2 + nlen * 2].decode("utf-16-be").rstrip("\0")
            rest = body[2 + nlen * 2:]
            if btype == 0xC001:
                out.append({"group": name})
                continue
            model = rest[:4].decode()
            k = {"RGB ": 3, "CMYK": 4, "Gray": 1, "LAB ": 3}[model]
            vals = struct.unpack(f">{k}f", rest[4:4 + 4 * k])
            ctype = struct.unpack(">H", rest[4 + 4 * k:6 + 4 * k])[0]
            out.append({"name": name, "model": model, "values": vals, "type": ctype})
        else:
            out.append({"end": True})
    assert pos == len(data)
    return out


def test_tokens_css_tailwind_json_ase(sample):
    from designassist import tokens

    res = tokens.export(sample, ["css", "scss", "tailwind", "json", "figma", "ase"], scales=True)
    css = sample.path("output", "tokens", "tokens.css").read_text(encoding="utf-8")
    assert "--color-primary: #E30613;" in css and "--color-primary-500: #E30613;" in css
    assert '--font-display: "Montserrat"' in css
    tw = sample.path("output", "tokens", "tailwind.tokens.js").read_text(encoding="utf-8")
    assert '"accent"' in tw and "#FFD400" in tw
    js = json.loads(sample.path("output", "tokens", "tokens.json").read_text(encoding="utf-8"))
    assert js["colors"]["primary"]["cmyk"] == [0, 100, 95, 0] and js["colors"]["primary"]["cmyk_authored"]
    sw = _read_ase(sample.path("output", "tokens", "swatches.ase").read_bytes())
    assert sw[0] == {"group": "sample"} and sw[-1] == {"end": True}
    prim = next(s for s in sw if s.get("name") == "primary")
    assert prim["model"] == "CMYK" and prim["values"] == pytest.approx((0, 1, 0.95, 0))
    acc = next(s for s in sw if s.get("name") == "accent")
    assert acc["model"] == "RGB " and acc["values"] == pytest.approx((1, 0xD4 / 255, 0), abs=1e-6)
    assert any(s.get("name") == "accent-950" for s in sw)
    assert set(res["files"]) >= {"output/tokens/swatches.ase", "output/tokens/tokens.css"}


def test_ase_spot_swatch_for_pantone():
    from designassist.tokens import ase_bytes

    sw = _read_ase(ase_bytes("Brand", [{"name": "485 C", "cmyk": (0, 95, 100, 0), "spot": True}]))
    assert sw[1]["type"] == 1 and sw[1]["name"] == "485 C"


# --- fonts ---------------------------------------------------------------------------------------

METADATA = '''name: "Inter"
designer: "Rasmus Andersson"
license: "OFL"
category: "SANS_SERIF"
fonts {
  name: "Inter"
  style: "normal"
  weight: 400
  filename: "Inter[opsz,wght].ttf"
  post_script_name: "Inter-Regular"
}
fonts {
  name: "Inter"
  style: "italic"
  weight: 400
  filename: "Inter-Italic[opsz,wght].ttf"
}
axes {
  tag: "wght"
  min_value: 100.0
  max_value: 900.0
}
'''


def test_google_metadata_parse_and_mocked_download(tmp_path, monkeypatch):
    from designassist import fonts as F

    meta = F.parse_metadata(METADATA)
    assert meta["name"] == "Inter" and meta["license"] == "OFL"
    assert [f["filename"] for f in meta["fonts"]] == ["Inter[opsz,wght].ttf", "Inter-Italic[opsz,wght].ttf"]
    assert meta["axes"] == [{"tag": "wght", "min": 100.0, "max": 900.0}]

    font_bytes = (F.BUNDLED / "Montserrat-Bold.ttf").read_bytes()
    seen = []

    class R:
        def __init__(self, code, text="", content=b""):
            self.status_code, self.text, self.content = code, text, content

    def fake_get(url, timeout=0):
        seen.append(url)
        if url.endswith("/ofl/inter/METADATA.pb"):
            return R(200, METADATA)
        if "/ofl/inter/" in url:
            return R(200, content=b"licence" if url.endswith(".txt") else font_bytes)
        return R(404)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    res = F.google_get("Inter", dest_root=tmp_path / "g")
    assert sorted(res["files"]) == ["Inter-Italic[opsz,wght].ttf", "Inter[opsz,wght].ttf", "OFL.txt"]
    assert any("Inter%5Bopsz%2Cwght%5D.ttf" in u or "Inter%5Bopsz,wght%5D.ttf" in u for u in seen)
    with pytest.raises(SystemExit):
        monkeypatch.setattr(requests, "get", lambda url, timeout=0: R(404))
        F.google_get("No Such Font", dest_root=tmp_path / "g")


def test_font_pairs_and_find(capsys):
    from designassist import fonts as F

    ps = F.pairs("montserrat")
    assert any(p["body"] == "Merriweather" for p in ps)
    main(["fonts", "find", "montser"])
    out = json.loads(capsys.readouterr().out)
    assert out[0]["family"] == "Montserrat"


@pytest.mark.network
def test_google_fonts_live(tmp_path):
    from designassist import fonts as F

    res = F.google_get("Caveat", dest_root=tmp_path)
    assert any(f.endswith(".ttf") for f in res["files"]) and "OFL.txt" in res["files"]


# --- icons ----------------------------------------------------------------------------------------

def test_icon_search_from_cached_tags(monkeypatch, tmp_path):
    from designassist import icons

    monkeypatch.setattr(icons, "DIR", tmp_path)
    (tmp_path / "tags.json").write_text(json.dumps({"heart": ["love", "like"], "heart-off": ["unlike"],
                                                    "star": ["favourite"]}), encoding="utf-8")
    assert [h["name"] for h in icons.search("heart")] == ["heart", "heart-off"]
    assert [h["name"] for h in icons.search("love")] == ["heart"]


# --- stock (mocked) --------------------------------------------------------------------------------

def test_stock_browse_and_download_mocked(sample, monkeypatch, tmp_path):
    from designassist import stock

    thumb = tmp_path / "t.jpg"
    make_photo(thumb, (300, 200))
    data = thumb.read_bytes()
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "test")
    hits = []

    class Resp:
        def __init__(self, js=None, content=b""):
            self._js, self.content, self.status_code = js, content, 200

        def json(self):
            return self._js

        def raise_for_status(self):
            pass

        def iter_content(self, n):
            yield self.content

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_get(url, headers=None, params=None, timeout=0, stream=False):
        hits.append(url)
        if "search/photos" in url:
            assert headers["Authorization"] == "Client-ID test"
            return Resp({"results": [{"id": f"u{i}", "width": 4000, "height": 6000,
                                      "urls": {"small": f"https://img/{i}s", "full": f"https://img/{i}f"},
                                      "links": {"html": f"https://unsplash.com/p/{i}", "download_location": f"https://api/dl/{i}"},
                                      "user": {"name": f"Ana {i}", "links": {"html": "https://unsplash.com/@ana"}},
                                      "alt_description": "café"} for i in range(3)]})
        if url.startswith("https://api/dl/"):
            return Resp({"url": url.replace("api/dl", "img") + "f"})
        return Resp(content=data)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    res = stock.browse(sample, "café da manhã", "unsplash", 3)
    assert res["results"] == 3 and sample.path(res["sheet"]).exists()
    dl = stock.download(sample, "café da manhã", [2], "unsplash")
    assert "https://api/dl/1" in hits  # Unsplash download endpoint triggered
    credits = json.loads(sample.path("work", "credits.json").read_text(encoding="utf-8"))
    assert credits[0]["photographer"] == "Ana 1" and "Unsplash" in credits[0]["licence"]
    assert sample.path(dl["downloaded"][0]["file"]).exists()


def test_stock_missing_key_message(sample, monkeypatch):
    from designassist import stock

    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setattr(stock, "ROOT", sample.dir)  # no .env there
    with pytest.raises(SystemExit, match="PEXELS_API_KEY"):
        stock.api_key("pexels")


# --- higgsfield (parsing only) ---------------------------------------------------------------------

def test_higgsfield_parsers_and_budget(sample, monkeypatch):
    from designassist import higgsfield as H

    page = ('> ## Documentation Index\n> Fetch the complete documentation index at: https://x/llms.txt\n\n'
            '# Recraft V4.1 — Text to image API\n\n> Text to image with Recraft.\n\n'
            '**Endpoint ID:** `recraft/v4.1/text-to-image`\n')
    info = H.parse_workflow(page)
    assert info == {"endpoint": "recraft/v4.1/text-to-image", "name": "Recraft V4.1 — Text to image",
                    "summary": "Text to image with Recraft."}
    assert H.parse_catalog('<a href="/docs/models/soul-v2">x</a><a href="/docs/models/recraft-v4-1">') == ["recraft-v4-1", "soul-v2"]
    assert H.result_urls({"images": [{"url": "a"}], "video": {"url": "b"}}) == ["a", "b"]
    monkeypatch.setenv("HF_API_KEY_ID", "i")
    monkeypatch.setenv("HF_API_KEY_SECRET", "s")
    monkeypatch.setenv("DA_HF_MAX_USD", "1")
    monkeypatch.setattr(H, "estimate", lambda e, a: {"usd": 3.5, "credits": 50})
    with pytest.raises(SystemExit, match="DA_HF_MAX_USD"):
        H.generate(sample, "recraft/v4.1/text-to-image", {"prompt": "x"})


# --- images ----------------------------------------------------------------------------------------

def test_vectorize_synthetic_logo(sample):
    from designassist.imagetools import vectorize

    im = Image.new("RGB", (600, 300), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((30, 30, 270, 270), fill="#E30613")
    d.ellipse((100, 100, 200, 200), fill="white")
    d.rectangle((320, 60, 560, 240), fill="#111111")
    im.save(sample.path("input", "mark.png"))
    res = vectorize(sample, sample.path("input", "mark.png"), colors=3)
    svg = sample.path(res["file"]).read_text(encoding="utf-8")
    assert res["paths"] >= 2 and "<path" in svg and "viewBox" in svg
    assert set(res["colors"]) == {"#E30613", "#111111"}  # exact brand colours, background dropped


def test_crop_aspect_and_info(sample):
    from designassist.imagetools import crop, info

    res = crop(sample, sample.path("input", "photo.jpg"), "9:16", "center", width=540)
    assert res["px"] == [540, 960]
    i = info(sample.path("input", "photo.jpg"))
    assert i["px"] == [1600, 1200] and i["print_size_at_300dpi_mm"] == [135.5, 101.6]


def test_upscale_and_remove_bg_message(sample):
    from designassist import imagetools as T

    res = T.upscale(sample, sample.path("input", "photo.jpg"), 1.5)
    assert res["px"] == [2400, 1800] and "not AI" in res["method"]
    try:
        import rembg  # noqa: F401
    except ImportError:
        with pytest.raises(SystemExit, match="--extra bg"):
            T.remove_bg(sample, sample.path("input", "photo.jpg"))


# --- mockups / board --------------------------------------------------------------------------------

def test_mockup_auto_green_quad(sample):
    from designassist.mockup import find_green_quad, mockup

    scene = Image.new("RGB", (1200, 900), (170, 160, 150))
    quad = [(400, 150), (900, 200), (880, 800), (380, 760)]
    ImageDraw.Draw(scene).polygon(quad, fill=(20, 215, 40))
    scene.save(sample.path("input", "scene.png"))
    found = find_green_quad(scene)
    for (x, y), (fx, fy) in zip(quad, found):
        assert abs(x - fx) <= 3 and abs(y - fy) <= 3
    res = mockup(sample, "post", "input/scene.png", auto=True)
    out = Image.open(sample.path(res["file"])).convert("RGB")
    assert out.size == (1200, 900)
    # no green left inside the quad
    from designassist.mockup import green_mask

    assert green_mask(out).sum() < 50


def test_builtin_mockups(sample):
    from designassist.mockup import BUILTINS, mockup

    for kind in BUILTINS:
        res = mockup(sample, "post", builtin=kind)
        assert sample.path(res["file"]).exists()


def test_board(sample):
    from designassist.board import board

    _three_colour(sample.path("input", "ref1.png"))
    res = board(sample, ["input"], title="Refs", notes="quente e contrastado")
    assert sample.path(res["file"]).exists() and sample.path(res["look"]).exists()
    assert res["images"] == 2 and len(res["palette"]) >= 3
    # a second board with another title is a new file, not an overwrite of the first
    res2 = board(sample, ["input"], title="Logos e paleta")
    assert res2["look"] != res["look"] and res2["file"] != res["file"]
    assert sample.path(res["look"]).exists() and res2["look"].endswith("board-logos-e-paleta.jpg")


def test_woff2_fonts_are_indexed_and_shaped(tmp_path, monkeypatch):
    """Client fonts often come from their website as .woff2: index and use them like a .ttf."""
    from fontTools.ttLib import TTFont

    from designassist import fonts as F
    from designassist import text as T

    src = F.BUNDLED / "Montserrat-Bold.ttf"
    tt = TTFont(str(src))
    tt["name"].setName("Webfont Test", 1, 3, 1, 0x409)
    tt["name"].setName("Webfont Test", 16, 3, 1, 0x409)
    tt.flavor = "woff2"
    d = tmp_path / "webfonts"
    d.mkdir()
    tt.save(str(d / "webfont-test.woff2"))
    monkeypatch.setattr(F, "CACHE", tmp_path / "cache")
    ref = F.resolve("Webfont Test", 700, extra=[d])
    assert ref.path.endswith(".ttf") and "web" in ref.path
    f = T.font(ref)
    assert f.shape("Olá")


def test_extend_continues_a_studio_background_without_seams(sample):
    import numpy as np

    from designassist import imagetools as T

    # a wide studio render: grey sweep (darker at the top) with a dark product in the middle
    w, h = 800, 400
    g = np.tile(np.linspace(170, 210, h)[:, None], (1, w))
    im = np.stack([g, g, g], -1)
    im[150:330, 150:650] = (90, 60, 40)
    Image.fromarray(im.astype("uint8")).save(sample.path("input", "render.jpg"), quality=95)
    res = T.extend(sample, sample.path("input", "render.jpg"), "4:5", scale=1.0, place=(0.5, 0.6), width=800)
    out = np.asarray(Image.open(sample.path(res["file"])).convert("L"), float)
    assert res["px"] == [800, 1000]
    x0, y0, pw, ph = res["photo_box"]
    assert out[y0 + 240, 400] < 100  # the product is kept where it was placed
    # above the photo the sweep continues from the photo's top colour, with no step at the seam
    assert abs(out[y0 - 5, 50:750].mean() - out[y0 + 5, 50:750].mean()) < 4
    assert abs(out[20, 50:750].mean() - 170) < 8
    assert abs(out[-20, 50:750].mean() - 210) < 8


def test_keep_largest_drops_people_and_ghosts_behind_a_product():
    import numpy as np

    from designassist.imagetools import keep_largest

    a = np.zeros((300, 400), np.uint8)
    a[150:280, 20:380] = 255   # the sofa
    a[30:70, 330:370] = 255    # a head behind it (rembg kept it)
    a[100:150, 300:380] = 110  # half-transparent ghost of a person, touching the sofa
    out, dropped = keep_largest(a, haze=190)
    assert out[200, 200] == 255 and out[50, 350] == 0 and out[110, 340] == 0
    assert dropped >= 1
