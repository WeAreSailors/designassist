// designassist -> Affinity builder. Runs inside Affinity (3.2+) through its AI connector.
// Prepended by affinity_build.py with:  const DA = {...};   (documents, artboards, ops in px)
// Everything is in document pixels (Affinity node coordinates are pixels at the document dpi,
// whatever the display unit). Output: one line "@@DA@@" + JSON on console.log.
'use strict';
const { app } = require('/application');
const { Document, NewDocumentOptions } = require('/document');
const { UnitType } = require('/units');
const N = require('/nodes');
const { AddChildNodesCommandBuilder, DocumentCommand } = require('/commands');
const SH = require('/shapes');
const G = require('/geometry');
const C = require('/colours');
const F = require('/fills');
const LS = require('/linestyle');
const { Bitmap } = require('/rasterobject');
const { StoryBuilder } = require('/storybuilder');
const SD = require('/storydelta');
const D = SD.StoryDelta;
const { FontFamily } = require('/fonts');

const result = { docs: [], warnings: [], nodes: 0 };
const warn = (m) => result.warnings.push(m);

function colour(rgba) {
  return C.Colour.createRGBA8({ r: rgba[0], g: rgba[1], b: rgba[2], alpha: Math.round((rgba[3] == null ? 1 : rgba[3]) * 255) });
}

function lineT(x1, y1, x2, y2) {
  // Gradient fill transforms map the unit line (0,0)-(1,0) onto spread coordinates; operations
  // are applied in call order (scale, then rotate, then translate).
  const L = Math.max(1e-6, Math.hypot(x2 - x1, y2 - y1)), a = Math.atan2(y2 - y1, x2 - x1);
  const t = G.Transform.createIdentity(); t.scale(L, L); t.rotate(a); t.translate(x1, y1);
  return t;
}

function fillDesc(f) {
  if (!f) return F.FillDescriptor.createNone();
  if (f.rgba) return F.FillDescriptor.createSolid(colour(f.rgba));
  const g = f.gradient;
  const stops = g.stops.map(s => ({ position: s[0], colour: colour(s[1]) }));
  if (g.radial) {
    const gf = F.GradientFill.create(C.Gradient.create(stops), F.GradientFillType.Radial);
    // elliptical like SVG's objectBoundingBox radial: unit circle scaled by (rx, ry), then moved to the centre
    const t = G.Transform.createIdentity(); t.scale(g.rx, g.ry); t.translate(g.cx, g.cy);
    return F.FillDescriptor.create(gf, true, t, F.BlendMode.Normal, false);
  }
  const gf = F.GradientFill.create(C.Gradient.create(stops), F.GradientFillType.Linear);
  return F.FillDescriptor.create(gf, true, lineT(g.x1, g.y1, g.x2, g.y2), F.BlendMode.Normal, false);
}

function lineStyle(s) {
  // node definitions take a LineStyleDescriptor (style + arrows/alignment), not a bare LineStyle
  const ls = LS.LineStyle.createDefaultWithWeight(s ? s.width : 0);
  if (s && s.cap && LS.LineCap[s.cap] !== undefined) ls.cap = LS.LineCap[s.cap];
  if (s && s.join && LS.LineJoin[s.join] !== undefined) ls.join = LS.LineJoin[s.join];
  return LS.LineStyleDescriptor.create(ls);
}

let doc = null;
const targets = {};  // artboard id / group id -> node

function insert(def, parentId, kind) {
  const b = AddChildNodesCommandBuilder.create();
  if (kind) b[kind](def); else b.addNode(def);
  b.setInsertionTarget(parentId && targets[parentId] ? targets[parentId] : doc.currentSpread);
  doc.executeCommand(b.createCommand(true, N.NodeChildType.Main));
  const n = doc.selection.nodes.toArray()[0];
  result.nodes++;
  return n;
}

function transformNode(n, t) { doc.applyTransform(t, n.selfSelection, null); }

function finish(n, op) {
  try { n.userDescription = op.id; } catch (e) { warn(op.id + ': name: ' + e); }
  if (op.opacity != null && op.opacity < 1) doc.setOpacity(op.opacity, n.selfSelection);
  if (op.blend) {
    const key = Object.keys(F.BlendMode).find(k => k.toLowerCase() === op.blend) ||
      F.BlendMode.keys.find(k => k.toLowerCase() === op.blend);
    if (key) doc.setBlendMode(F.BlendMode[key], false, n.selfSelection); else warn(op.id + ': blend ' + op.blend + ' not in Affinity');
  }
  if (op.shadow) {
    try {
      const s = op.shadow, sel = n.selfSelection;
      doc.setOuterShadowLayerEffectColour(sel, colour([s.rgba[0], s.rgba[1], s.rgba[2], 1]), 0, true);
      doc.setOuterShadowLayerEffectOpacity(sel, 0, s.rgba[3], true);
      doc.setOuterShadowLayerEffectRadius(sel, 0, s.blur, true);
      doc.setOuterShadowLayerEffectOffsetAngle(sel, Math.hypot(s.dx, s.dy), Math.atan2(s.dy, s.dx), 0, true);
    } catch (e) { warn(op.id + ': shadow: ' + e); }
  }
  if (op.blur) {
    try { doc.setGaussianBlurLayerEffectRadius(n.selfSelection, op.blur, true); } catch (e) { warn(op.id + ': blur: ' + e); }
  }
  if (op.rotation) {
    const t = G.Transform.createIdentity(); t.translate(-op.cx, -op.cy); t.rotate(op.rotation * Math.PI / 180); t.translate(op.cx, op.cy);
    transformNode(n, t);
  }
}

function rectShape(op) {
  const s = SH.ShapeRectangle.create();
  const r = op.radius || [0, 0, 0, 0];
  if (r.some(v => v > 0)) {
    s.setAbsoluteSizes(true, op.w, op.h);
    const corners = [s.topLeft, s.topRight, s.bottomRight, s.bottomLeft];
    corners.forEach((c, i) => { if (r[i] > 0) { c.cornerType = SH.ShapeCornerType.Round; c.setRadius(r[i], op.w, op.h); } });
  }
  return s;
}

function curveFrom(subpaths) {
  const pc = G.PolyCurve.create();
  for (const sp of subpaths) {
    const cb = G.CurveBuilder.create();
    let started = false, segments = 0;
    for (const s of sp) {
      if (s[0] === 'M') { cb.beginXY(s[1], s[2]); started = true; }
      else if (s[0] === 'L') { cb.lineToXY(s[1], s[2]); segments++; }
      else if (s[0] === 'C') { cb.addBezierXY(s[1], s[2], s[3], s[4], s[5], s[6]); segments++; }
      else if (s[0] === 'Z') cb.close();
    }
    // a lone moveto ("Z M x y" at the end of PDF-extracted paths) makes createCurve fail with INVALID_OP
    if (started && segments) pc.addCurve(cb.createCurve());
  }
  return pc;
}

function curveNode(sh, parentId, name) {
  const brush = fillDesc(sh.fill_desc || (sh.fill ? { rgba: sh.fill } : null));
  const pen = fillDesc(sh.stroke ? { rgba: sh.stroke } : null);
  const style = lineStyle(sh.stroke ? { width: sh.stroke_width, cap: cap(sh.linecap), join: join(sh.linejoin) } : null);
  // the JS wrapper's parameter order changed between releases (3.3.1: lineFill before lineStyle)
  const def = PEN_FIRST ? N.PolyCurveNodeDefinition.create(curveFrom(sh.subpaths), brush, pen, style, F.FillDescriptor.createNone())
                        : N.PolyCurveNodeDefinition.create(curveFrom(sh.subpaths), brush, style, pen, F.FillDescriptor.createNone());
  const n = insert(def, parentId, 'addPolyCurveNode');
  try { n.userDescription = name; } catch (e) { }
  return n;
}
const PEN_FIRST = (() => {
  const src = String(N.PolyCurveNodeDefinition.create);
  const m = src.match(/create\s*\(([^)]*)\)/);
  const args = m ? m[1].split(',').map(a => a.trim()) : [];
  return args.indexOf('lineFill') !== -1 && args.indexOf('lineFill') < args.indexOf('lineStyle');
})();
const cap = (c) => ({ butt: 'Butt', round: 'Round', square: 'Square' })[c] || 'Butt';
const join = (j) => ({ miter: 'Miter', round: 'Round', bevel: 'Bevel' })[j] || 'Miter';

function textNode(op) {
  const sb = StoryBuilder.create();
  sb.setToFrameTextDefaultStyle(doc.dpi);
  const para = [D.createLeadingType(SD.ParagraphLeadingType.ExactlyAbsolute),
    D.createParagraphDouble(SD.ParagraphAttDoubleType.AbsoluteLeading, op.leading),
    D.createAlignX(SD.ParagraphAlignXType[op.align] || SD.ParagraphAlignXType.Left),
    // "\n" becomes a paragraph break: the default frame style adds space around paragraphs
    D.createParagraphDouble(SD.ParagraphAttDoubleType.SpaceBefore, 0),
    D.createParagraphDouble(SD.ParagraphAttDoubleType.SpaceAfter, 0)];
  sb.applyParagraphDelta(D.createComposite(para));
  op.paragraphs.forEach((runs, pi) => {
    for (const r of runs) {
      const g = [D.createPostscriptName(FONT[r.ps] || r.ps), D.createGlyphDouble(SD.GlyphAttDoubleType.Height, r.size),
        D.createGlyphDouble(SD.GlyphAttDoubleType.CharacterSpacing, r.tracking),
        D.createBrushFill(fillDesc({ rgba: r.rgba }))];
      if (r.stroke) {
        g.push(D.createPenFill(fillDesc({ rgba: r.stroke.rgba })));
        try { g.push(D.createGlyphLineStyleDescriptor(lineStyle({ width: r.stroke.width, join: 'Round' }))); }
        catch (e) { warn(op.id + ': text stroke: ' + e); }
      }
      sb.applyGlyphDelta(D.createComposite(g));
      sb.addText(r.text);
    }
    if (pi < op.paragraphs.length - 1) sb.addParagraphBreak();
  });
  const n = insert(N.FrameTextNodeDefinition.createFromStoryBuilder(new G.Rectangle(op.x, op.y, op.w, op.h), sb), op.parent);
  // Affinity places the first baseline differently from our engine: move the frame so the ink
  // top lands where the preview has it (x already matches).
  const v = n.getExactSpreadVisibleBox(false, false);
  const dy = op.ink[1] - v.y;
  const dx = op.align === 'Left' ? op.ink[0] - v.x : 0;  // optical alignment / side bearings
  if (Math.abs(dy) > 0.01 || Math.abs(dx) > 0.01) transformNode(n, G.Transform.createTranslate(dx, dy));
  const v2 = n.getExactSpreadVisibleBox(false, false);
  return { node: n, ink: [v2.x, v2.y, v2.x + v2.width, v2.y + v2.height], dy: dy };
}

function imageNode(op) {
  const bm = Bitmap.loadFromFile(op.file);
  const def = N.ImageNodeDefinition.create(C.RasterFormat.RGBA8);
  def.setBitmap(bm);
  const n = insert(def, op.parent, 'addImageNode');
  const b = n.spreadBaseBox;
  const t = G.Transform.createIdentity();
  t.translate(-b.x, -b.y); t.scale(op.w / b.width, op.h / b.height); t.translate(op.x, op.y);
  transformNode(n, t);
  return n;
}

function build(spec) {
  const o = NewDocumentOptions.createDefault();
  o.units = spec.units === 'mm' ? UnitType.Millimetre : (spec.units === 'in' ? UnitType.Inch : UnitType.Pixel);
  o.dpi = spec.dpi;
  // width/height in the document unit
  o.width = spec.doc_w; o.height = spec.doc_h;
  if (spec.bleed) o.bleed = { left: spec.bleed, top: spec.bleed, right: spec.bleed, bottom: spec.bleed };
  o.createArtboard = !!spec.artboards;
  doc = Document.create(o);
  for (const k of Object.keys(targets)) delete targets[k];
  if (spec.artboards) {
    spec.artboards.forEach((ab, i) => {
      if (i > 0) {
        const def = N.ShapeNodeDefinition.createDefault();
        def.shape = SH.ShapeRectangle.create();
        def.setBoundingRectangle(new G.Rectangle(ab.x, ab.y, ab.w, ab.h));
        doc.executeCommand(DocumentCommand.createAddArtboard(def));
      }
    });
    const kids = doc.currentSpread.children.toArray().filter(n => n.isShapeNode);
    spec.artboards.forEach(ab => {
      const hit = kids.find(n => { const b = n.spreadBaseBox; return Math.abs(b.x - ab.x) < 0.5 && Math.abs(b.y - ab.y) < 0.5; });
      if (!hit) { warn('artboard ' + ab.id + ' not found after creation'); return; }
      targets[ab.id] = hit;
      try { hit.userDescription = ab.id; } catch (e) { }
    });
  }
  const texts = {};
  for (const op of spec.ops) {
    try {
      let n;
      if (op.op === 'rect' || op.op === 'ellipse') {
        const shape = op.op === 'rect' ? rectShape(op) : SH.ShapeEllipse.create();
        n = insert(N.ShapeNodeDefinition.create(shape, new G.Rectangle(op.x, op.y, op.w, op.h), fillDesc(op.fill),
          fillDesc(op.stroke ? { rgba: op.stroke.rgba } : null), lineStyle(op.stroke), null), op.parent, 'addShapeNode');
      } else if (op.op === 'group') {
        n = insert(N.ContainerNodeDefinition.create(op.id), op.parent, 'addContainerNode');
        targets[op.id] = n;
      } else if (op.op === 'curves') {
        if (op.shapes.length === 1) n = curveNode(op.shapes[0], op.parent, op.id);
        else {
          n = insert(N.ContainerNodeDefinition.create(op.id), op.parent, 'addContainerNode');
          targets[op.id] = n;
          op.shapes.forEach((sh, i) => curveNode(sh, op.id, op.id + '-' + (i + 1)));
        }
      } else if (op.op === 'image') {
        n = imageNode(op);
      } else if (op.op === 'text') {
        const t = textNode(op);
        n = t.node;
        texts[op.ab ? op.ab + '/' + op.id : op.id] = { ink: t.ink, dy: t.dy };
      } else { warn('unknown op ' + op.op); continue; }
      finish(n, op);
    } catch (e) {
      warn(op.id + ': ' + e);
    }
  }
  let saved = null;
  if (spec.save) {
    // never save over a file that is open in another document (the user's edited copy): -v2, -v3...
    let target = spec.save;
    try {
      const busy = new Set(app.documents.all.filter(o => o.sessionUuid !== doc.sessionUuid).map(o => String(o.path || '')));
      for (let v = 2; busy.has(target) && v < 50; v++) target = spec.save.replace(/\.af$/, '-v' + v + '.af');
    } catch (e) { }
    try { doc.saveAs(target); saved = target; } catch (e) { warn('save: ' + e); }
  }
  let snap = {};
  try { snap = daSnapshot(doc); } catch (e) { warn('snapshot: ' + e); }
  result.docs.push({ name: spec.name, uuid: doc.sessionUuid, saved: saved, texts: texts, snapshot: snap,
                     spreads: doc.spreads ? doc.spreads.length || 1 : 1 });
}

// Map the PostScript names we ask for onto what Affinity has. Variable fonts without instance
// PostScript names show up as "<default>_<Style>" (Outfit-Thin_ExtraBold, Inter-Regular_Bold).
const FONT = {};
try {
  const have = new Set(), byFamily = {};
  for (const fam of FontFamily.all) for (const f of fam.fonts) {
    have.add(f.postscriptName);
    (byFamily[fam.name.toLowerCase()] = byFamily[fam.name.toLowerCase()] || []).push(f.postscriptName);
  }
  const norm = (s) => s.toLowerCase().replace(/[\s_-]/g, '');
  result.missing_fonts = [];
  for (const ps of DA.fonts) {
    if (have.has(ps)) { FONT[ps] = ps; continue; }
    const req = (DA.font_requests || {})[ps] || {};
    const list = byFamily[(req.family || '').toLowerCase()] || [];
    const style = norm(req.style || 'Regular');
    let hit = list.find(p => norm(p.split(/[_]/).pop()) === style || norm(p.split('-').pop()) === style);
    if (!hit && style === 'regular') hit = list.find(p => !p.includes('_'));
    if (hit) FONT[ps] = hit; else { FONT[ps] = ps; result.missing_fonts.push(ps); }
  }
  result.fonts_used = FONT;
} catch (e) { warn('font check: ' + e); }

for (const spec of DA.docs) build(spec);
console.log('@@DA@@' + JSON.stringify(result));
