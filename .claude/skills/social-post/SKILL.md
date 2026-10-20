---
name: social-post
description: Design single social media pieces: Instagram/Facebook/LinkedIn/X feed posts, stories and status, Reels/TikTok covers, Pinterest pins, announcements, promos, quotes, event posts, testimonials, hiring posts. Use for "faz um post", "arte pro feed", "story de promoção", "post de lançamento", "capa de reels".
---
# social-post

Read first: layout skill (craft + loop), brief skill (have the copy and goal).

## Formats
`uv run da presets --kind social`. Feed: `ig-post` 1080x1350 (4:5, takes the most screen; default),
`ig-square`, `li-post`, `x-post`. Vertical: `ig-story` 1080x1920 (safe zone keeps 250 px top / 340 px bottom
free of text: the app UI covers them), `wa-status`. Pins: `pin`. Covers for Reels: `ig-story` and keep the
centre 1080x1350 readable (the grid crops it to 3:4 → check `ig-grid`).

## Archetypes (pick one, then make it yours)
- **Promo/offer**: big number/offer as headline (accent colour), product photo, CTA pill, price/validity
  small. Price and dates come from the user only.
- **Announcement/launch**: label ("NOVIDADE") + strong headline + one visual; lots of space.
- **Quote/testimonial**: big quote marks or serif, the quote ≤ 25 words, name + role small, photo circle (`mask: "circle"`).
- **Event**: what / when / where hierarchy; date as a graphic block; @handle or link.
- **Tip/educational**: number or icon + short title + 1-2 lines (or make it a carousel).
- **Photo-led**: full-bleed photo (`fit: cover`, `focus: face`), gradient scrim, short headline.

## Build
1. Background (token colour or gradient) → photo (if any) → scrim → shapes → text → logo/CTA.
2. Headline with `autofit` inside a box (`w`, `h`); support text `w` ≈ 70-85% of the width.
3. Logo small (≈ 10-14% of width) in a corner inside `safe`, or centred at the bottom. Use `brand:logo` /
   `brand:logo-white` when the client has a kit; `color` recolours a mono SVG logo.
4. Icons: `uv run da icon search <english words>` → `{"type":"icon","name":...}`.
5. Render, LOOK (also small), `da qa`, iterate.

## Stories specifics
Text inside the safe zone, bigger type (headline 90-140 px), one idea per frame, interactive-sticker space
(leave ~300 px clear if they'll add a poll/link sticker: ask). Sequence of stories = carousel skill logic.

## Deliver
`uv run da export <p> --to png` (feed: png or jpg q90; PNG for flat colour/text). For the client's approval,
show a feed mockup: `uv run da mockup <p> --art <id> --builtin post-feed`.
