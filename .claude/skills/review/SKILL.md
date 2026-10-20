---
name: review
description: Apply the user's or client's feedback on a version ("aumenta o logo", "troca a foto", "o cliente achou poluído", "muda o texto pra...", marked-up screenshots) and learn from it. Use whenever the user reacts to a render, mockup or delivered file.
---
# review

1. `uv run da version <p> save <short-label>` before changing anything (rollback: `da version <p> restore v2`).
2. Map each note to layers: `uv run da info <p>` lists artboards and layer ids. Vague notes ("tá poluído",
   "não chamou atenção", "tá sem vida") → translate into concrete moves and say which: remove an element,
   more space, bigger headline, stronger contrast, one accent instead of three, a better photo.
   A marked-up screenshot from the client: LOOK at it and list every mark.
3. Edit design.json; re-render; LOOK; `uv run da qa <p>`. Changes to a master in a set (carousel, ad sizes):
   apply to every artboard of the set, not just the one mentioned.
4. Reply per note: what changed (and anything you couldn't do and why). Show the new render.
5. **Learn**: a lasting taste ("sempre logo maior", "esse cliente odeia degradê") → style-profile skill,
   right away, in the client's file when it's about them, else general; unclear → ask. One-off content
   changes (this headline, this photo) are not preferences.
6. Many rounds on the same thing → stop and align with 2-3 quick variations side by side instead of guessing
   again (`da artboard <p> duplicate`).
