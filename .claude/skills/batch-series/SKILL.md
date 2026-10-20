---
name: batch-series
description: Produce many pieces from one template and a table (CSV/JSON/spreadsheet the user pastes): menu items, price lists, product cards, event schedules, team member cards, real-estate listings, quote series. Use for "faz um pra cada produto", "tenho uma planilha com...", "série de posts iguais mudando só o texto", "cardápio".
---
# batch-series

1. Design ONE template artboard with the longest realistic content (the longest name, the biggest price)
   and get it approved. Put placeholders where data goes: `"text": "{{nome}}"`, `"src": "input/{{foto}}"`,
   `"color": "{{cor}}"`. Text boxes that receive data need `w`, `h` and `autofit: true` (and `max_lines`).
2. Data: save the user's table as `projects/<p>/data.csv` (UTF-8, header row = field names) or `data.json`
   (list of objects). Spreadsheet pasted in chat: convert it yourself; ask about blanks.
3. `uv run da batch <p> --template <artboard> --data data.csv --id-field <slug field> --render`
   creates one artboard per row (`<template>-<id>`) and renders a contact sheet.
4. LOOK at the sheet: the longest and shortest rows are where things break (overflow, orphan words, a
   photo with a bad crop). Fix those rows individually in design.json (it's fine to diverge) or adjust the
   template and re-run. `uv run da qa <p>`.
5. Export: `uv run da export <p> --to png` (or `pdf` for a printable menu/catalogue).
Rows with missing data: never invent it; leave the artboard out and list them for the user.
