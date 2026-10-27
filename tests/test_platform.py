from __future__ import annotations

import json

import pytest
from PIL import Image

from designassist import brand as B
from designassist import design as D
from designassist.cli import main
from designassist.project import Project, memory_dir

from conftest import SAMPLE_SVG, make_photo


def run(capsys, *argv):
    main(list(argv))
    return json.loads(capsys.readouterr().out)


def test_memory_init_seeds_templates(isolated, capsys):
    res = run(capsys, "memory", "--init")
    mem = memory_dir()
    assert res["dir"] == str(mem)
    for f in ("preferences.md", "log.md", "styles/example-bold-social.md", "clients/_template/preferences.md"):
        assert (mem / f).exists(), f
    again = run(capsys, "memory", "--init")
    assert again["created"] == []  # never overwrites
    info = run(capsys, "memory")
    assert "preferences.md" in info["files"]


def test_setup_done_marker(isolated, monkeypatch, capsys):
    from designassist import memory_cmd as M

    monkeypatch.setattr(M, "SETUP", isolated / ".designassist" / "setup.json")
    assert run(capsys, "setup-done", "--skipped")["status"] == "skipped"
    assert json.loads(M.SETUP.read_text())["status"] == "skipped"
    run(capsys, "setup-done", "--reset")
    assert not M.SETUP.exists()


def test_client_new_set_show(sample, capsys):
    run(capsys, "memory", "--init")
    res = run(capsys, "client", "new", "Padaria São João")
    assert res["client"] == "padaria-sao-joao"
    prefs = (B.client_dir("padaria-sao-joao") / "preferences.md").read_text(encoding="utf-8")
    assert "Padaria São João" in prefs and "{name}" not in prefs
    run(capsys, "client", "set", "sample", "Padaria São João")
    assert D.load(sample)["brand"] == "padaria-sao-joao"
    show = run(capsys, "client", "show", "sample")
    assert show["client"] == "padaria-sao-joao"
    assert any(p.endswith("brand.json") for p in show["read_in_order"])
    assert [c["client"] for c in run(capsys, "client", "list")] == ["padaria-sao-joao"]


@pytest.fixture
def kit(isolated, tmp_path):
    B.create("Vulcano Motors")
    logo = tmp_path / "logo.svg"
    logo.write_text(SAMPLE_SVG, encoding="utf-8")
    B.add_logo("vulcano-motors", logo, "logo")
    B.set_values("vulcano-motors", colors=["primary=#E30613", "ink=#141414", "paper=#FFFFFF"],
                 cmyk=["primary=0,100,95,0"], pantone=["primary=485 C"], fonts=["display=Montserrat:900"],
                 rules=["logo sempre no canto superior", "nunca texto vermelho no preto"])
    return "vulcano-motors"


def test_brand_set_values(kit):
    k = B.load(kit)
    assert k["colors"]["primary"] == {"hex": "#E30613", "cmyk": [0, 100, 95, 0], "pantone": "485 C"}
    assert k["colors"]["ink"] == "#141414"
    assert k["fonts"]["display"] == {"family": "Montserrat", "weight": 900}
    assert k["logos"]["logo"] == "logo.svg" and (B.brand_dir(kit) / "logo.svg").exists()
    with pytest.raises(SystemExit):
        B.set_values(kit, cmyk=["accent=0,0,0,0"])  # colour not defined yet


def test_logo_pack_files(kit):
    res = B.logo_pack(kit, "logo")
    out = B.brand_dir(kit) / "pack" / "logo"
    files = set(res["files"])
    for f in ("logo.svg", "logo-black.svg", "logo-white.svg", "logo-1024.png", "logo-white-2048.png", "logo.pdf",
              "logo-on-primary.png", "favicon/favicon.ico", "favicon/apple-touch-icon.png", "favicon/icon-512.png",
              "favicon/site.webmanifest"):
        assert f in files, f
    assert "#E30613" not in (out / "logo-white.svg").read_text(encoding="utf-8")
    im = Image.open(out / "logo-1024.png")
    assert im.width == 1024 and im.mode == "RGBA"
    white = Image.open(out / "logo-white-512.png").convert("RGBA")
    opaque = [p for p in white.getdata() if p[3] > 200]
    assert opaque and all(p[0] > 240 and p[1] > 240 and p[2] > 240 for p in opaque[:500])
    assert Image.open(out / "favicon" / "apple-touch-icon.png").size == (180, 180)
    assert json.loads((out / "favicon" / "site.webmanifest").read_text())["theme_color"] == "#E30613"


def test_logo_pack_from_png(kit, tmp_path):
    png = tmp_path / "mark.png"
    im = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
    im.paste((227, 6, 19, 255), (100, 50, 500, 250))
    im.save(png)
    B.add_logo(kit, png, "mark")
    res = B.logo_pack(kit, "mark")
    assert "mark-black-2048.png" in res["files"] and res["notes"]


def test_brand_guide_validates_and_renders(kit):
    from designassist import render

    res = B.guide(kit)
    assert not res["errors"]
    assert res["artboards"] == ["cover", "logo", "colors", "type", "rules"]
    pr = Project(res["project"])
    out = render.render(pr)
    assert len(out["rendered"]) == 5
    problems = [p for r in out["rendered"] for p in r["problems"]]
    assert not problems, problems
    texts = json.dumps(D.load(pr), ensure_ascii=False)
    assert "Pantone 485 C" in texts and "CMYK 0 100 95 0" in texts


def test_keys_mask_and_gitignore(isolated, monkeypatch, capsys):
    from designassist import keys as K

    monkeypatch.setattr(K, "ENV", isolated / ".env")
    for k in list(K.KEYS) + list(K.SETTINGS):
        monkeypatch.delenv(k, raising=False)
    res = K.set_key("PEXELS_API_KEY", "abcdefghijklmnop1234")
    assert res["value"] == "…1234"
    rows = {r["key"]: r for r in K.status()}
    assert rows["PEXELS_API_KEY"]["set"] and rows["PEXELS_API_KEY"]["value"] == "…1234"
    assert "abcdefghijklmnop" not in json.dumps(rows)
    assert not rows["HF_API_KEY_ID"]["set"]
    K.set_key("DA_HF_MAX_USD", "5")
    assert {r["key"]: r for r in K.status()}["DA_HF_MAX_USD"]["value"] == "5"
    assert K.is_gitignored()


def test_resize_post_to_story_and_print(sample, capsys):
    from designassist import resize as R

    res = R.resize(sample, "post", ["ig-story", "card-br"])
    d = D.load(sample)
    story = D.artboard(d, "post-ig-story")
    assert (story["width"], story["height"]) == (1080, 1920)
    photo = D.find_layer(story["layers"], "photo")
    assert photo["x"] == 0 and photo["w"] == 1080 and photo["h"] > 860  # band keeps its share of the taller canvas
    safe = story["safe"]
    ctx = D.context(sample, d)
    from designassist import svg as S

    _, rep = S.artboard_svg(ctx, story)
    for lid in ("title", "cta-tx"):
        assert not rep.texts[lid]["overflow"]
    for l in story["layers"]:
        if l["type"] in ("text", "svg") or l.get("role") == "logo":
            assert l["x"] >= safe[3] - 0.01 and l["y"] >= safe[0] - 0.01
            assert l["x"] + l.get("w", 0) <= 1080 - safe[1] + 0.01
    card = D.artboard(d, "post-card-br")
    assert card["unit"] == "mm"
    ph = D.find_layer(card["layers"], "photo")
    assert ph["x"] == -3 and ph["y"] == -3  # runs into the bleed
    title = D.find_layer(card["layers"], "title")
    assert title["autofit"] and 0 < title["size"] < 20  # mm now
    assert res["made"][1]["size"] == "90x50 mm"



def test_resize_keeps_stacked_lines_and_cutout_framing():
    """Square cover -> story: a headline set as one layer per line must stay a stacked block (the bottom
    lines used to be pinned to the safe edge on top of each other), and a hand-placed cut-out bigger than
    the canvas keeps its aspect instead of being stretched over the story (2026-10-21)."""
    from designassist import resize as R

    line = lambda i, y, size: {"id": f"h{i}", "type": "text", "text": "LINHA", "x": 70, "y": y, "w": 940,  # noqa: E731
                               "h": size, "size": size, "align": "center", "valign": "middle", "role": "headline"}
    src = {"id": "sq", "preset": "ig-square", "width": 1080, "height": 1080, "unit": "px", "dpi": 72,
           "safe": [56, 56, 56, 56], "layers": [
               {"id": "guest", "type": "image", "role": "photo", "src": "x.png", "fit": "fill",
                "x": -772, "y": -209, "w": 2679, "h": 1507},
               line(1, 638, 76), line(2, 734, 118), line(3, 873, 76),
               {"id": "name", "type": "text", "text": "NOME", "x": 140, "y": 968, "w": 800, "size": 32,
                "align": "center", "role": "body"}]}
    story, _ = R.adapt(src, "ig-story", "st")
    L = {l["id"]: l for l in story["layers"]}
    g = L["guest"]
    assert abs(g["w"] / g["h"] - 2679 / 1507) < 0.01  # aspect kept, not stretched to 1080x1920
    assert g["w"] > 1080 and g["x"] < 0
    top, right, bottom, left = story["safe"]
    order = [L[k] for k in ("h1", "h2", "h3", "name")]
    for a, b in zip(order, order[1:]):
        assert b["y"] >= a["y"] + a["h"] - 0.5, (a["id"], b["id"])  # still stacked, no overlap
    assert order[0]["y"] >= top and order[-1]["y"] + 32 * 1.2 <= 1920 - bottom + 0.5


def test_batch_from_csv(sample, capsys):
    d = D.load(sample)
    post = D.artboard(d, "post")
    D.find_layer(post["layers"], "title")["text"] = "{{produto}} por **{{preco}}**"
    D.save(sample, d)
    sample.path("input", "rows.csv").write_text("produto;preco\nPão francês;R$ 0,90\nBolo de milho;R$ 25\nCafé;R$ 6\n",
                                              encoding="utf-8")
    res = run(capsys, "batch", "sample", "--template", "post", "--data", "input/rows.csv", "--id-field", "produto")
    assert res["made"] == ["post-pao-frances", "post-bolo-de-milho", "post-cafe"]
    d = D.load(sample)
    assert D.find_layer(D.artboard(d, "post-cafe")["layers"], "title")["text"] == "Café por **R$ 6**"
    assert D.validate(d, D.context(sample, d))["errors"] == []


def test_qa_clean_sample_has_no_errors(sample):
    from designassist import qa

    res = qa.qa(sample)
    assert res["errors"] == 0, res["issues"]


def test_qa_flags_problems(sample):
    from designassist import qa

    make_photo(sample.path("input", "tiny.jpg"), size=(200, 150))
    d = D.load(sample)
    post = D.artboard(d, "post")
    post["layers"] += [
        {"id": "long", "type": "text", "text": "texto longo demais " * 20, "x": 80, "y": 100, "w": 400, "h": 80, "size": 40,
         "color": "$paper"},
        {"id": "dim", "type": "text", "text": "quase invisível", "x": 500, "y": 1000, "size": 40, "color": "#222222"},
        {"id": "logo2", "type": "svg", "src": "input/logo.svg", "x": 1000, "y": 20, "w": 70, "h": 30, "role": "logo"},
        {"id": "small", "type": "image", "src": "input/tiny.jpg", "x": 100, "y": 300, "w": 600, "h": 450},
    ]
    D.save(sample, d)
    res = qa.qa(sample, ["post"])
    found = {(i["layer"], i["check"]) for i in res["issues"]}
    assert ("long", "overflow") in found
    assert ("dim", "contrast") in found
    assert ("logo2", "safe-zone") in found
    assert ("small", "resolution") in found
    assert not res["ok"]


def test_qa_print_bleed_and_margin(sample):
    from designassist import qa

    d = D.load(sample)
    card = D.artboard(d, "card")
    card["layers"] += [{"id": "band", "type": "rect", "x": 0, "y": 40, "w": 90, "h": 10, "fill": "$ink"},
                       {"id": "edge", "type": "text", "text": "site.com", "x": 1, "y": 44, "size": "7pt", "color": "$paper"}]
    D.save(sample, d)
    found = {(i["layer"], i["check"]) for i in qa.qa(sample, ["card"])["issues"]}
    assert ("band", "bleed") in found and ("edge", "margin") in found


def test_web_new_and_shot(sample, capsys):
    from designassist.doctor import find_browser

    res = run(capsys, "web", "new", "sample", "Landing", "--kind", "landing")
    page = sample.path(res["page"])
    css = sample.path(res["tokens"]).read_text(encoding="utf-8")
    assert "--color-primary: #E30613" in css and "@font-face" in css
    assert any(sample.path("web", "landing", "fonts").iterdir())
    if not find_browser():
        pytest.skip("no headless browser on this machine")
    shot = run(capsys, "web", "shot", "sample", "landing", "--sizes", "800x600")
    f = sample.path(shot["shots"][0]["file"])
    assert Image.open(f).size == (800, 600)
    full = run(capsys, "web", "shot", "sample", "landing", "--sizes", "390x400", "--full-page")
    assert full["shots"][0]["page_height"] > 400
    assert Image.open(sample.path(full["shots"][0]["file"])).size[1] == full["shots"][0]["page_height"]
    assert page.read_text(encoding="utf-8").count("<base") == 0  # the user's page is never modified


def test_doctor_runs(capsys):
    from designassist import doctor

    ok, rows = doctor.checks()
    names = {r["name"] for r in rows}
    assert {"resvg (render)", "headless browser", "Adobe Illustrator", "CMYK profile", "design memory"} <= names
    assert all(r["ok"] for r in rows if r["name"].startswith(("resvg", "harfbuzz", "reportlab")))


def test_qa_alignment_uses_text_ink_not_box(sample):
    """Big type nudged left so its letters line up with the text below must not be flagged."""
    from designassist import design as D
    from designassist import qa
    from designassist import text as T

    d = D.load(sample)
    ab = d["artboards"][0]
    small = {"id": "small", "type": "text", "text": "Legenda", "x": 100, "y": 1000, "size": 30, "color": "$paper"}
    big = {"id": "big", "type": "text", "text": "Dados", "x": 100, "y": 1040, "size": 160, "color": "$paper"}
    ctx = D.context(sample, d)
    gap = T.ink_box(T.layout(big, ctx))[0] - T.ink_box(T.layout(small, ctx))[0]
    big["x"] = 100 - gap  # optical alignment: ink edges equal
    ab["layers"] += [small, big]
    D.save(sample, d)
    res = qa.qa(sample, ["post"], contrast=False)
    flagged = [i for i in res["issues"] if i["check"] == "alignment" and {"big", "small"} & {i["layer"]}]
    assert not flagged, flagged


def test_qa_safe_zone_uses_text_ink_for_optical_type(sample):
    """An `optical` number whose ink starts on the safe edge has its pen origin left of it (side bearing):
    it must not be flagged as outside the safe zone; text whose ink really crosses the edge still is."""
    from designassist import design as D
    from designassist import qa

    d = D.load(sample)
    ab = d["artboards"][0]
    ab["layers"] += [
        {"id": "num", "type": "text", "text": "01", "x": 60, "y": 200, "size": 500, "color": "$paper", "optical": True},
        {"id": "out", "type": "text", "text": "01", "x": 30, "y": 800, "size": 200, "color": "$paper", "optical": True},
    ]
    D.save(sample, d)
    found = {(i["layer"], i["check"]) for i in qa.qa(sample, ["post"], contrast=False)["issues"]}
    assert ("num", "safe-zone") not in found
    assert ("out", "safe-zone") in found


def test_qa_contrast_ignores_film_grain(sample):
    """White text on a solid dark colour stays readable under grain; the specks must not fail it."""
    from designassist import design as D
    from designassist import qa

    d = D.load(sample)
    ab = d["artboards"][0]
    ab["background"] = "#B33A00"  # white on it: ~5.6:1
    ab["layers"] = [
        {"id": "g", "type": "noise", "x": 0, "y": 0, "w": 1080, "h": 1350, "size": 1.1, "opacity": 0.5},
        {"id": "t", "type": "text", "text": "Texto branco", "x": 100, "y": 600, "size": 60, "weight": 700, "color": "#FFFFFF"},
    ]
    D.save(sample, d)
    res = qa.qa(sample, ["post"])
    assert not [i for i in res["issues"] if i["check"] == "contrast"], res["issues"]


def test_qa_flags_a_widow_but_not_hand_broken_lines():
    from designassist.qa import _widow

    # wrapped at 460 px this sentence left "DE SENTAR." alone under a carousel paragraph (2026-10-20)
    lines = [{"text": t, "width": w} for t, w in [("NA LINHA RIPADO, OS VÃOS ENTRE", 455), ("AS RIPAS REVELAM E OCULTAM", 400),
                                                    ("DETALHES, CONVIDANDO O OLHAR", 430), ("A EXPLORAR A PEÇA ANTES MESMO", 452),
                                                    ("DE SENTAR.", 150)]]
    wrapped = {"type": "text", "w": 460, "text": " ".join(l["text"] for l in lines)}
    assert _widow(wrapped, {"lines": lines}) == "DE SENTAR."
    by_hand = dict(wrapped, text="\n".join(l["text"] for l in lines))  # the author chose that break
    assert _widow(by_hand, {"lines": lines}) is None
    balanced = lines[:4] + [{"text": "MESMO DE SENTAR.", "width": 260}]
    assert _widow(dict(wrapped, text="x"), {"lines": balanced}) is None
