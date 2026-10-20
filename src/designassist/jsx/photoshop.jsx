// designassist -> Photoshop builder. Expects `DA` (data written by adobe.py) and common.jsx.
// One document per artboard, pixels. Text is native; everything else is a placed smart object.

var __out = { app: "photoshop", documents: [], layers: 0, texts: 0, missing_fonts: [], errors: [], saved: [] };

var __rulers = app.preferences.rulerUnits, __type = app.preferences.typeUnits;
app.preferences.rulerUnits = Units.PIXELS;
app.preferences.typeUnits = TypeUnits.PIXELS;
app.displayDialogs = DialogModes.NO;

var BLENDS = { "multiply": "MULTIPLY", "screen": "SCREEN", "overlay": "OVERLAY", "darken": "DARKEN", "lighten": "LIGHTEN",
  "color-dodge": "COLORDODGE", "color-burn": "COLORBURN", "hard-light": "HARDLIGHT", "soft-light": "SOFTLIGHT",
  "difference": "DIFFERENCE", "exclusion": "EXCLUSION", "hue": "HUE", "saturation": "SATURATION",
  "color": "COLOR", "luminosity": "LUMINOSITY" };
var JUST = { "left": "LEFT", "center": "CENTER", "right": "RIGHT", "justify": "LEFTJUSTIFIED" };

function daSolid(rgb) {
  var c = new SolidColor();
  c.rgb.red = rgb[0]; c.rgb.green = rgb[1]; c.rgb.blue = rgb[2];
  return c;
}

function daPx(v) { return new UnitValue(v, "px"); }

function daCommon(layer, d) {
  layer.name = d.name;
  if (d.opacity !== undefined && d.opacity !== null && d.opacity < 1) layer.opacity = d.opacity * 100;
  if (d.blend && BLENDS[d.blend]) layer.blendMode = BlendMode[BLENDS[d.blend]];
}

function daPlace(doc, file) {
  var desc = new ActionDescriptor();
  desc.putPath(charIDToTypeID("null"), new File(file));
  desc.putEnumerated(charIDToTypeID("FTcs"), charIDToTypeID("QCSt"), charIDToTypeID("Qcsa"));
  var ofs = new ActionDescriptor();
  ofs.putUnitDouble(charIDToTypeID("Hrzn"), charIDToTypeID("#Pxl"), 0);
  ofs.putUnitDouble(charIDToTypeID("Vrtc"), charIDToTypeID("#Pxl"), 0);
  desc.putObject(charIDToTypeID("Ofst"), charIDToTypeID("Ofst"), ofs);
  executeAction(charIDToTypeID("Plc "), desc, DialogModes.NO);
  return doc.activeLayer;
}

function daInto(layer, parent, doc) {
  // new layers land above the ACTIVE layer, which may sit inside a group built before: put each one
  // explicitly on top of its parent (we build bottom to top)
  if (parent) { if (parent.layers[0] != layer) layer.move(parent, ElementPlacement.PLACEATBEGINNING); }
  else if (doc.layers[0] != layer) layer.move(doc.layers[0], ElementPlacement.PLACEBEFORE);
}

function daBuild(doc, d, parent) {
  var layer = null;
  if (d.kind == "image") {
    layer = daPlace(doc, d.file);
    daInto(layer, parent, doc);
    var b = layer.bounds;
    layer.translate(daPx(d.left - b[0].as("px")), daPx(d.top - b[1].as("px")));
    daCommon(layer, d);
  } else if (d.kind == "text") {
    layer = (parent || doc).artLayers.add();
    daInto(layer, parent, doc);
    layer.kind = LayerKind.TEXT;
    var t = layer.textItem;
    if (d.box) {
      t.kind = TextType.PARAGRAPHTEXT;
      t.position = [daPx(d.box[0]), daPx(d.box[1])];
      t.width = daPx(d.box[2]);
      t.height = daPx(d.box[3]);
    } else {
      t.position = [daPx(d.point[0]), daPx(d.point[1])];
    }
    t.contents = d.contents;
    try { t.font = d.font; } catch (e) { __out.missing_fonts.push(d.font); }
    t.size = daPx(d.size);
    t.useAutoLeading = false;
    t.leading = daPx(d.leading);
    t.tracking = d.tracking;
    t.color = daSolid(d.color);
    t.justification = Justification[JUST[d.align] || "LEFT"];
    daCommon(layer, d);
    __out.texts++;
  } else if (d.kind == "group") {
    layer = (parent || doc).layerSets.add();
    daInto(layer, parent, doc);
    for (var i = 0; i < d.layers.length; i++) daTry(__out, d.layers[i].name, (function (s, c) {
      return function () { return daBuild(doc, c, s); }; })(layer, d.layers[i]));
    daCommon(layer, d);
  }
  __out.layers++;
  return layer;
}

for (var n = 0; n < DA.docs.length; n++) {
  var D = DA.docs[n];
  var doc = app.documents.add(daPx(D.w), daPx(D.h), D.dpi, D.id, NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
  var bg = doc.artLayers[0];
  bg.name = "background";
  if (D.background && D.background.solid) {
    doc.selection.selectAll();
    doc.selection.fill(daSolid(D.background.solid));
    doc.selection.deselect();
  } else if (D.background && D.background.file) {
    var bl = daPlace(doc, D.background.file);
    var bb = bl.bounds;
    bl.translate(daPx(-bb[0].as("px")), daPx(-bb[1].as("px")));
    bl.name = "background";
    bg.remove();
  }
  for (var i = 0; i < D.layers.length; i++) daTry(__out, D.layers[i].name, (function (c) {
    return function () { return daBuild(doc, c, null); }; })(D.layers[i]));
  __out.documents.push(D.id);
  if (D.save) {
    daTry(__out, "save " + D.id, function () {
      var o = new PhotoshopSaveOptions();
      o.layers = true; o.embedColorProfile = true;
      doc.saveAs(new File(D.save), o, true);
      __out.saved.push(D.save);
    });
  }
}

app.preferences.rulerUnits = __rulers;
app.preferences.typeUnits = __type;
daJSON(__out);
