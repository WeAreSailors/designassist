// designassist -> Illustrator builder. Expects `DA` (data written by adobe.py) and common.jsx.
// Coordinates in DA are already Illustrator document points (y up, artboard tops at 0).

var __out = { app: "illustrator", document: null, artboards: [], items: 0, texts: 0, missing_fonts: [], errors: [],
              lines: {}, saved: null };

app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM;

var __spots = {};
var __fontCache = {};
var BLENDS = { "multiply": "MULTIPLY", "screen": "SCREEN", "overlay": "OVERLAY", "darken": "DARKEN", "lighten": "LIGHTEN",
  "color-dodge": "COLORDODGE", "color-burn": "COLORBURN", "hard-light": "HARDLIGHT", "soft-light": "SOFTLIGHT",
  "difference": "DIFFERENCE", "exclusion": "EXCLUSION", "hue": "HUE", "saturation": "SATURATIONBLEND",
  "color": "COLORBLEND", "luminosity": "LUMINOSITY" };
var JUST = { "left": "LEFT", "center": "CENTER", "right": "RIGHT", "justify": "FULLJUSTIFYLASTLINELEFT" };

function daColor(c) {
  if (!c) return new NoColor();
  if (c.spot && __spots[c.spot]) {
    var s = new SpotColor(); s.spot = __spots[c.spot]; s.tint = 100; return s;
  }
  if (DA.doc.mode == "CMYK") {
    var k = new CMYKColor(); k.cyan = c.cmyk[0]; k.magenta = c.cmyk[1]; k.yellow = c.cmyk[2]; k.black = c.cmyk[3]; return k;
  }
  var r = new RGBColor(); r.red = c.rgb[0]; r.green = c.rgb[1]; r.blue = c.rgb[2]; return r;
}

function daFont(ps) {
  if (__fontCache[ps] !== undefined) return __fontCache[ps];
  var f = null;
  try { f = app.textFonts.getByName(ps); } catch (e) { f = null; }
  if (!f) {
    var seen = false;
    for (var i = 0; i < __out.missing_fonts.length; i++) if (__out.missing_fonts[i] == ps) seen = true;
    if (!seen) __out.missing_fonts.push(ps);
  }
  __fontCache[ps] = f;
  return f;
}

function daShadow(it, sh) {
  // Effect > Stylize > Drop Shadow (black, darkness mode: Illustrator's XML has no settable colour here)
  it.applyEffect('<LiveEffect name="Adobe Drop Shadow"><Dict data="R horz ' + sh.x + ' R vert ' + sh.y +
    ' R blur ' + sh.blur + ' R opac ' + sh.opacity + ' I blnd 1 I csrc 0 B pair 1 I usePSLBlur 1 R dark 100 R dist ' +
    Math.round(Math.sqrt(sh.x * sh.x + sh.y * sh.y)) + '"/></LiveEffect>');
}

function daCommon(it, d) {
  if (d.shadow) daTry(__out, d.name + " shadow", function () { daShadow(it, d.shadow); });
  if (d.opacity !== undefined && d.opacity !== null && d.opacity < 1) it.opacity = d.opacity * 100;
  if (d.blend && BLENDS[d.blend]) it.blendingMode = BlendModes[BLENDS[d.blend]];
  if (d.rotation) it.rotate(-d.rotation);
  it.name = d.name;
}

function daPaint(p, d) {
  if (d.fill) { p.filled = true; p.fillColor = daColor(d.fill); } else { p.filled = false; }
  if (d.stroke) {
    p.stroked = true; p.strokeWidth = d.stroke.width; p.strokeColor = daColor(d.stroke.color);
    if (d.stroke.dash) p.strokeDashes = d.stroke.dash;
  } else { p.stroked = false; }
}

function daFind(container, name) {
  for (var i = 0; i < container.pageItems.length; i++) {
    var it = container.pageItems[i];
    if (it.name.replace(/[\s_]/g, "") == name) return it;
    if (it.typename == "GroupItem") { var hit = daFind(it, name); if (hit) return hit; }
  }
  return null;
}

function daUnname(container, name) {
  // the SVG importer names inner items after svg ids; keep the layer id unique to the outer group
  for (var i = 0; i < container.pageItems.length; i++) {
    var it = container.pageItems[i];
    if (it.name == name) it.name = "";
    if (it.typename == "GroupItem") daUnname(it, name);
  }
}

function daCharAttrs(ca, d, r) {
  var f = daFont(r.font);
  if (f) ca.textFont = f;
  ca.size = r.size;
  ca.autoLeading = false;
  ca.leading = d.leading;
  ca.tracking = r.tracking;
  ca.fillColor = daColor(r.color);
  if (r.stroke) { ca.strokeColor = daColor(r.stroke.color); ca.strokeWeight = r.stroke.width; }
}

function daText(container, d) {
  var tf;
  if (d.area) {
    var path = container.pathItems.rectangle(d.top, d.left, d.w, d.h);
    tf = container.textFrames.areaText(path);
  } else {
    tf = container.textFrames.pointText([d.anchor[0], d.anchor[1]]);
  }
  tf.contents = d.contents;
  daCharAttrs(tf.textRange.characterAttributes, d, d.base);
  tf.textRange.paragraphAttributes.justification = Justification[JUST[d.align] || "LEFT"];
  for (var i = 0; i < d.ranges.length; i++) {
    var r = d.ranges[i];
    for (var c = r.start; c < r.start + r.len && c < tf.characters.length; c++) {
      daCharAttrs(tf.characters[c].characterAttributes, d, r);
    }
  }
  if (d.area) {
    tf.firstBaseline = FirstBaselineType.BASELINEFIXED;
    tf.firstBaselineMin = d.first_baseline;
  }
  daCommon(tf, d);
  __out.texts++;
  var n = 0;
  try { n = tf.lines.length; } catch (e) { n = -1; }
  __out.lines[d.name] = { expected: d.lines, got: n };
  return tf;
}

function daBuild(container, d) {
  var it = null;
  if (d.kind == "rect") {
    it = d.radius ? container.pathItems.roundedRectangle(d.top, d.left, d.w, d.h, d.radius, d.radius)
                  : container.pathItems.rectangle(d.top, d.left, d.w, d.h);
    daPaint(it, d); daCommon(it, d);
  } else if (d.kind == "ellipse") {
    it = container.pathItems.ellipse(d.top, d.left, d.w, d.h);
    daPaint(it, d); daCommon(it, d);
  } else if (d.kind == "line") {
    it = container.pathItems.add();
    it.setEntirePath(d.points);
    it.closed = false;
    daPaint(it, d); daCommon(it, d);
  } else if (d.kind == "text") {
    it = daText(container, d);
  } else if (d.kind == "image") {
    var pl = container.placedItems.add();
    pl.file = new File(d.file);
    pl.width = d.w; pl.height = d.h;
    pl.position = [d.left, d.top];
    if (d.rotation) pl.rotate(-d.rotation);
    if (d.embed) {
      pl.embed();
      it = container.pageItems[0];
    } else {
      it = pl;
    }
    daCommon(it, { name: d.name, opacity: d.opacity, blend: d.blend });
  } else if (d.kind == "svg") {
    it = container.groupItems.createFromFile(new File(d.file));
    it.position = [d.left, d.top];
    var frame = daFind(it, "daframe");
    if (frame) frame.remove();
    daUnname(it, d.name);
    it.name = d.name;
    if (d.blend && BLENDS[d.blend]) it.blendingMode = BlendModes[BLENDS[d.blend]];
    if (d.shadow) daTry(__out, d.name + " shadow", function () { daShadow(it, d.shadow); });
  } else if (d.kind == "group") {
    it = container.groupItems.add();
    for (var i = 0; i < d.items.length; i++) daTry(__out, d.items[i].name, (function (g, c) {
      return function () { return daBuild(g, c); }; })(it, d.items[i]));
    if (d.clip) {
      var cp = it.pathItems.rectangle(d.clip.top, d.clip.left, d.clip.w, d.clip.h);
      cp.filled = false; cp.stroked = false;
      it.clipped = true;
    }
    daCommon(it, d);
  }
  __out.items++;
  return it;
}

(function () {
  var first = DA.artboards[0];
  var doc = null;
  try {
    var pre = new DocumentPreset();
    pre.title = DA.doc.name;
    pre.colorMode = DA.doc.mode == "CMYK" ? DocumentColorSpace.CMYK : DocumentColorSpace.RGB;
    pre.width = first.rect[2] - first.rect[0];
    pre.height = first.rect[1] - first.rect[3];
    pre.units = DA.doc.mode == "CMYK" ? RulerUnits.Millimeters : RulerUnits.Pixels;
    if (DA.doc.bleed) { pre.documentBleedLink = true; pre.documentBleedOffsetRect = [DA.doc.bleed, DA.doc.bleed, DA.doc.bleed, DA.doc.bleed]; }
    doc = app.documents.addDocument(DA.doc.mode == "CMYK" ? "Print" : "Web", pre, false);
  } catch (e) {
    __out.errors.push("preset document: " + e);
    doc = app.documents.add(DA.doc.mode == "CMYK" ? DocumentColorSpace.CMYK : DocumentColorSpace.RGB,
                            first.rect[2] - first.rect[0], first.rect[1] - first.rect[3]);
  }
  __out.document = doc.name;

  // swatches
  daTry(__out, "swatches", function () {
    var grp = doc.swatchGroups.add();
    grp.name = DA.doc.swatch_group;
    for (var i = 0; i < DA.doc.swatches.length; i++) {
      var s = DA.doc.swatches[i];
      if (s.spot) {
        var sp = doc.spots.add();
        sp.name = s.spot;
        sp.colorType = ColorModel.SPOT;
        var cm = new CMYKColor(); cm.cyan = s.cmyk[0]; cm.magenta = s.cmyk[1]; cm.yellow = s.cmyk[2]; cm.black = s.cmyk[3];
        sp.color = cm;
        __spots[s.spot] = sp;
        grp.addSpot(sp);
      } else {
        var sw = doc.swatches.add();
        sw.name = s.name;
        sw.color = daColor({ rgb: s.rgb, cmyk: s.cmyk });
        grp.addSwatch(sw);
      }
    }
  });

  // artboards + one layer each (the default layer becomes the first)
  for (var a = 0; a < DA.artboards.length; a++) {
    var ab = DA.artboards[a];
    var board;
    if (a == 0) { board = doc.artboards[0]; board.artboardRect = ab.rect; } else { board = doc.artboards.add(ab.rect); }
    board.name = ab.id;
    var layer = a == 0 ? doc.layers[0] : doc.layers.add();
    layer.name = ab.id;
    for (var i = 0; i < ab.items.length; i++) daTry(__out, ab.items[i].name, (function (L, c) {
      return function () { return daBuild(L, c); }; })(layer, ab.items[i]));
    __out.artboards.push(ab.id);
  }
  // layers panel top-to-bottom = last artboard first; put them back in artboard order
  for (var m = 0; m < DA.artboards.length; m++) {
    daTry(__out, "order", function () { doc.layers.getByName(DA.artboards[m].id).zOrder(ZOrderMethod.SENDTOBACK); });
  }
  doc.selection = null;
  if (DA.save) {
    daTry(__out, "save", function () {
      var opt = new IllustratorSaveOptions();
      opt.pdfCompatible = true;
      doc.saveAs(new File(DA.save), opt);
      __out.saved = DA.save;
    });
  }
})();

daJSON(__out);
