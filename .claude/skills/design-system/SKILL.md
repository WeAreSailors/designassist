---
name: design-system
description: Turn a brand into a usable design system: colour scales and semantic tokens, type scale, spacing/radius/shadow tokens, component sheet (buttons, inputs, cards, badges), exported as CSS variables, Tailwind config, JSON/Tokens Studio and ASE swatches. Use for "design system", "tokens", "guia de componentes", "variáveis CSS da marca", "tailwind config da marca".
---
# design-system

1. Base tokens from the kit (brand-kit skill): `uv run da brand show <slug>`.
2. Colour scales: `uv run da color scale <hex>` for primary/neutral/accent (50-950). Semantic layer on top:
   `bg`, `surface`, `text`, `text-muted`, `border`, `primary`, `primary-hover`, `success`, `warning`,
   `danger` — pick steps that pass contrast (`uv run da color contrast`). Add them to design.json
   `tokens.colors` (or the kit).
3. Type scale (typography skill), spacing scale (4/8 px), radii (e.g. 4/8/16/999), shadows (2-3 levels).
4. Export: `uv run da tokens <p> --to css tailwind json ase --scales` → `output/tokens/`.
5. Component sheet: build it as HTML with the tokens (`uv run da web new <p> components --kind screen`):
   buttons (all states), inputs, select, checkbox, card, badge, alert, nav; screenshot with `da web shot`
   and LOOK. This page is the living spec.
6. Document decisions in `projects/<p>/web/components/README.md` (usage rules, do/don't).
