---
name: style-profile
description: Maintain the user's design memory (<memory>/preferences.md, per-client <memory>/clients/<client>/preferences.md and brand kits, <memory>/styles/*.md): type, colour, layout, imagery, copy tone, export habits. Decides whether a note is general or about one client and saves it in the right file. Use when the user states a preference, corrects a recurring choice, says "esse cliente não gosta de...", or asks to learn their (or a client's) style from previous work.
---
# style-profile

`<memory>` = the folder `uv run da memory` prints: the user's PRIVATE memory-os global tier
(`~/.memory-os/memory/designassist/`, shared by all their Claude accounts, never committed), or the gitignored
`memory/` fallback. Missing files: `uv run da memory --init`.

Files:
- `<memory>/preferences.md`: defaults for every piece, one bullet each, newest wins.
- `<memory>/clients/<client>/preferences.md`: one client's taste, tone, approvals, history of what they
  liked/rejected. Overrides the general file on their projects. `uv run da client list | new | set | show`.
- `<memory>/clients/<client>/brand/brand.json` (+ logos, fonts): the client's tokens — edit with
  `uv run da brand set` (brand-kit skill), not by prose in preferences.
- `<memory>/styles/<name>.md`: named looks ("bold social", "editorial"); the user says "usa o estilo editorial".
- `<memory>/log.md`: one dated line per delivered job.

General or client? Decide every time (`uv run da client show <p>` says whose project it is):
- Client: about THIS client — their brand, tone of voice, audience, formats, what they approved/rejected
  ("o cliente não gosta de preto", "a Ana sempre quer o logo grande"). Brand values → brand kit.
- General: about design itself or the user's way of working — "sempre"/"nunca" without the client in mind,
  type habits, export/naming habits, tools.
- Unclear (a colour or layout taste said during one client's job): ask once: "Isso vale só pro <cliente> ou
  pra todos?". Never guess silently. Tell the user where you saved it. A client rule repeated across 2+
  clients: offer to promote it to the general file.

Rules:
- Write when the user expresses a durable preference or corrects the same thing twice. Quote briefly and
  date it: `- Headlines in Montserrat 800, tracking -20 (2026-10-17, "gosto do título bem pesado")`.
- Edit the existing line instead of appending a contradiction.
- Never store API keys or personal data about third parties (a client's brand and taste are fine; their
  documents, phone, address are not).
- Taste goes here; facts about how the designassist CODE works go to `.claude/_memory/` (shared project tier).

Learning from previous work: put the user's/client's past pieces in a project's `input/`, `uv run da board`
them, LOOK, and measure: palette (`da color palette`), fonts (ask or identify), grid/margins, headline sizes
relative to width, photo treatment, logo placement. Write the findings as a style file or into the client's
preferences, and confirm with the user.
