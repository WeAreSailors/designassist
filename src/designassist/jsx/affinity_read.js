// designassist: read named layers of Affinity documents back (boxes, text, solid fills).
// Used after a build (snapshot of what was created) and by `da affinity read/pull`.
// Standalone use: prepend `const DA_READ = {uuids: [...]}` (empty = the current document).
// Keys are "<artboard>/<layer>" inside an artboard (layer ids repeat across artboards: every thumb has a
// "guest"), the bare name elsewhere (print documents have no artboard node).
function daSnapshot(doc) {
  const out = {};
  const walk = (n, scope) => {
    for (const c of n.children) {
      let id = null, isAb = false;
      try { id = c.userDescription; } catch (e) { }
      try { isAb = !!(c.artboardInterface && c.artboardInterface.isArtboardEnabled); } catch (e) { }
      const key = id ? (isAb || !scope ? id : scope + '/' + id) : null;
      if (key) {
        const b = c.spreadBaseBox;
        const rec = { kind: String(c).replace('[object ', '').replace(']', ''), box: [b.x, b.y, b.width, b.height] };
        try { if (c.isTextNode) rec.text = c.getText(); } catch (e) { }
        try {  // text colour = the first glyph's brush fill (frames have no brushFillDescriptor of their own)
          if (c.isTextNode) {
            const k = c.storyInterface.story.getGlyphAtts(0).brushFill.fill.colour.rgba8;
            rec.text_fill = [k.r, k.g, k.b, k.alpha / 255];
          }
        } catch (e) { }
        try {
          const fd = c.brushFillDescriptor;
          if (fd && fd.fill && fd.fill.colour) { const k = fd.fill.colour.rgba8; rec.fill = [k.r, k.g, k.b, k.alpha / 255]; }
        } catch (e) { }
        try { rec.opacity = c.globalOpacity; } catch (e) { }
        out[key] = rec;
      }
      walk(c, isAb && id ? id : scope);
    }
  };
  for (const s of doc.spreads ? doc.spreads.toArray ? doc.spreads.toArray() : [...doc.spreads] : [doc.currentSpread]) walk(s, null);
  return out;
}

if (typeof DA_READ !== 'undefined') {
  const { app } = require('/application');
  const docs = DA_READ.uuids && DA_READ.uuids.length
    ? app.documents.all.filter(d => DA_READ.uuids.includes(d.sessionUuid)) : [app.documents.current].filter(Boolean);
  const res = { docs: docs.map(d => ({ uuid: d.sessionUuid, title: d.title, path: d.path, layers: daSnapshot(d) })),
                open: app.documents.all.map(d => ({ uuid: d.sessionUuid, title: d.title })) };
  console.log('@@DA@@' + JSON.stringify(res));
}
