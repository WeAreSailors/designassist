---
name: ad-set
description: Adapt one approved design to every size a campaign needs (feed 4:5, story 9:16, square, landscape, Google Display, LinkedIn, banners) with `da resize`, then fix each size by eye. Use for "faz em todos os formatos", "adapta pra story", "pacote de anúncios", "versões pra Meta Ads / Google".
---
# ad-set

1. Get the master approved first (usually `ig-post` or `ad-feed`). Mark layer roles so resizing works:
   `role: background|photo` (re-covers the canvas), and `anchor` (top-left, bottom, center…) on logos/CTAs.
2. Generate: `uv run da resize <p> --from <master> --to ig-story ad-landscape gdn-rect gdn-leader`
   (`uv run da presets` for names). New artboards are `<master>-<preset>`.
3. Render and LOOK at every size. Automatic resizing is a first draft: on extreme ratios (728x90
   leaderboard, 160x600 skyscraper) re-compose by hand: drop the support text, keep logo + headline + CTA,
   change the headline line breaks, move the photo to one side.
4. Platform rules to respect:
   - Meta: little text on the image performs better; stories keep the 14% top / 20% bottom free.
   - Google Display: logo + CTA always visible; file ≤ 150 KB (`--to jpg --quality 80` or png for flat art).
   - LinkedIn: landscape 1200x627 for single image ads.
5. `uv run da qa <p>` (safe zones, tiny text: on 300x250 body text under ~12 px is unreadable), then
   `uv run da export <p> --to png jpg`. Name files clearly for the media buyer (handoff skill).
