// designassist: dump the ACTIVE Illustrator document (artboards, every page item) as JSON.
// Read-only: changes nothing. Expects common.jsx.

function daColorOut(c) {
  if (!c) return null;
  var t = c.typename;
  if (t == "RGBColor") return { rgb: [c.red, c.green, c.blue] };
  if (t == "CMYKColor") return { cmyk: [c.cyan, c.magenta, c.yellow, c.black] };
  if (t == "GrayColor") return { gray: c.gray };
  if (t == "SpotColor") { var s = daColorOut(c.spot.color) || {}; s.spot = c.spot.name; s.tint = c.tint; return s; }
  if (t == "NoColor") return null;
  return { type: t };
}

(function () {
  var out = { app: "illustrator", document: null, mode: null, artboards: [], items: [], errors: [] };
  if (app.documents.length == 0) { out.errors.push("no open document"); return daJSON(out); }
  app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;
  var doc = app.activeDocument;
  out.document = doc.name;
  out.mode = doc.documentColorSpace == DocumentColorSpace.CMYK ? "CMYK" : "RGB";
  for (var a = 0; a < doc.artboards.length; a++) {
    out.artboards.push({ name: doc.artboards[a].name, rect: doc.artboards[a].artboardRect });
  }
  for (var i = 0; i < doc.pageItems.length; i++) {
    var it = doc.pageItems[i];
    var o = { name: it.name, type: it.typename, bounds: it.geometricBounds, opacity: it.opacity,
              hidden: it.hidden, layer: it.layer ? it.layer.name : null,
              parent: it.parent && it.parent.typename == "GroupItem" ? it.parent.name : null };
    try {
      if (it.typename == "PathItem") {
        o.filled = it.filled; o.fill = it.filled ? daColorOut(it.fillColor) : null;
        o.stroked = it.stroked; o.stroke = it.stroked ? daColorOut(it.strokeColor) : null;
      } else if (it.typename == "TextFrame") {
        var ca = it.textRange.characterAttributes;
        o.contents = it.contents;
        o.kind = String(it.kind);
        try { o.font = ca.textFont.name; } catch (e) { o.font = null; }
        o.size = ca.size;
        o.fill = daColorOut(ca.fillColor);
        if (it.kind == TextType.AREATEXT) {
          o.area = it.textPath.geometricBounds;
        }
      }
    } catch (e) { out.errors.push(it.name + ": " + e); }
    out.items.push(o);
  }
  return daJSON(out);
})();
