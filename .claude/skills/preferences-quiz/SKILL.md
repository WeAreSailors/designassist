---
name: preferences-quiz
description: Short questionnaire that learns how this user designs (kind of work, tools, platforms, type and colour taste, layout style, imagery, copy tone, export habits) and writes the answers to their private design memory. Use for "questionário de preferências", "me pergunta como eu trabalho", "aprende meu estilo", a new teammate's first job, or when preferences.md is still the empty template. Re-runnable per section ("muda minhas preferências de tipografia").
---
# preferences-quiz

Goal: in 3-5 minutes `<memory>/preferences.md` holds real defaults, so the first piece already looks like
theirs. `<memory>` = the folder `uv run da memory` prints. Write rules come from the style-profile skill.

Talk in the user's language. AskUserQuestion: at most 4 questions per call, 2-4 options each (the tool adds
"Other"), most common first. Never a wall of questions in chat. API keys are NOT part of this quiz.

## 0. Start
1. `uv run da memory` (missing files: `uv run da memory --init`); read `preferences.md` and `styles/`.
2. Summarise in 2-3 lines what is set and what is empty.
3. Mode: **Quick** (kind of work, tools, visual style) / **Full** (rounds 1-6) / **One section**. In Full
   mode skip what's already answered.

## 1. Work and tools
- Main work (multi): social media for clients / visual identity / UI-web / print.
- Where files must open: Illustrator / Photoshop / Canva / just final files (Other: Affinity, Figma).
- Who receives: clients directly / an agency / print shops / developers.
- Language of the copy: Portuguese / English / Spanish.

## 2. Social defaults
- Default feed format: 4:5 (1080x1350) / 1:1 / both.
- Always also deliver: story version / none / all ad sizes.
- Logo placement default: top-left / bottom-centre / bottom-right / varies by client.
- Captions (legendas) for posts: I write them / write a proposal / never.

## 3. Type
- Style: modern sans (Inter, Montserrat) / geometric (Poppins, Futura-like) / editorial serif / mixed serif+sans.
- Headlines: heavy and tight / medium and airy / all caps.
- Favourite fonts (free text, they must be installed or on Google Fonts) → `## Type`.

## 4. Colour and layout
- Palette taste: vibrant / muted-earthy / monochrome+one accent / brand-dependent.
- Layout: minimal with lots of space / bold and dense / editorial grids / playful-organic.
- Shapes: sharp corners / rounded / pills+circles. Shadows: none / soft / hard offset.
- Gradients: never / subtle / bold.

## 5. Imagery
- Source preference order: client photos / stock (Pexels, Unsplash) / AI-generated (+ their per-image
  budget → `DA_HF_MAX_USD` in `.env`, not memory).
- Photo treatment: natural / warm / B&W / duotone in brand colours.
- Illustrations/icons: line icons / filled / none.

## 6. Free text (plain chat, each skippable)
- Things they never want ("nunca Comic Sans", "nada de emoji na arte", "sem degradê arco-íris") → `## Never`.
- Their own brand (if they design for themselves: colours, fonts, @) → `## My brand`. A CLIENT's brand goes
  to the brand kit (brand-kit skill).
- Export habits (naming, always send PDF + PNG, print shop they use and its specs) → `## Delivery`.

## Writing
- Edit lines in place in `<memory>/preferences.md`; never append a contradiction. Missing sections: add them
  following `memory.template/preferences.md`.
- Format: `- <preference> (<YYYY-MM-DD>, quiz: "<their answer>")`.
- Never write keys, client data they didn't offer, or anything to `.claude/_memory/` (shared tier).
- A second set of defaults for another kind of job (e.g. "posts de restaurante" vs "corporativo"): offer a
  named style `<memory>/styles/<name>.md` (shape of `styles/example-bold-social.md`).

## Finish
Show before → after (changed lines only), where the file lives, and that they can change anything by just
saying it ("prefiro cantos retos"). If this ran from designassist-setup, return to its next step.
