---
name: brief
description: Turn a request into a design brief before designing: objective, audience, channel and formats, copy, mandatory elements, brand, references, deadline; propose 2-3 concepts when the direction is open. Use at the start of every new piece or campaign, when the request is vague ("faz um post pra promo", "preciso de uma logo"), or when the user pastes a client's message/brief.
---
# brief

Goal: know what success looks like before touching design.json. One round of questions, short, only what
you can't infer. Talk in the user's language.

## 1. Read what exists
- `<memory>` preferences and, for a client, `uv run da client show <p>` (preferences + brand kit). A client
  with a brand kit answers colours, fonts and logo already: don't ask again.
- Files in `projects/<p>/input/`: brief docs (.md/.txt/.pdf), photos, logos, references. Look at images.

## 2. Fill the brief (ask for the gaps, in one AskUserQuestion round or a short list)
| Item | Why it matters |
|---|---|
| Objective (sell, announce, inform, recruit, brand awareness) | decides the CTA and hierarchy |
| Audience | tone, type, imagery |
| Channel + formats (feed 4:5, story, carousel, print size, site) | presets (`uv run da presets`) |
| Copy: headline, support text, CTA, legal/price/date | never invent prices, dates, claims, contacts |
| Must appear: logo, product photo, address, @handle, QR | |
| Brand: kit exists? colours/fonts/logo files | otherwise palette + typography skills |
| References / what they like / what they hate | moodboard skill |
| Quantity and deadline | one piece, a series, a campaign set |

Copy missing? Offer to write it (copywriting skill) and mark it as a proposal.

## 3. Concepts (when the direction is open)
Propose 2-3 one-line concepts with a distinct idea each, e.g.:
- "Tipográfico: headline gigante '50% OFF' em amarelo sobre preto, produto pequeno no canto"
- "Foto protagonista: produto em close, faixa diagonal com o preço"
- "Editorial: muito branco, serif elegante, foto recortada"
Let the user pick (or "você escolhe"). For a set, decide the system once (grid, type, colour roles).

## 4. Write it down
Save the brief as `projects/<p>/brief.md` (objective, audience, formats, copy, mandatory, concept chosen).
Create artboards: `uv run da new <p> --client "<Client>" --preset ig-post ig-story` or
`uv run da artboard <p> add --preset <preset> --id <id>`.
