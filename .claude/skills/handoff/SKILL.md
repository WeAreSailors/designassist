---
name: handoff
description: Package and deliver finished work to a client, printer, media buyer or developer: all formats, clear file names, spec sheet (sizes, colours HEX/RGB/CMYK, fonts and where to get them), zip, and a short delivery message; logs the delivery in memory. Use for "entrega", "manda tudo pro cliente", "organiza os arquivos finais", "zip", "pacote final".
---
# handoff

1. `uv run da qa <p>` clean of errors; final copy proofread (names, prices, dates, phone, @).
2. `uv run da package <p> --zip` → `output/package/` (+ zip): every format the purpose needs and
   `README.txt` (sizes, colours, fonts + licences/links, what each file is for). Add specific targets with
   `uv run da export` first when the client asked for something extra (PSD, AI script, print PDF).
3. File names the receiver understands: `<cliente>_<peça>_<formato>_<tamanho>.png` (rename in the package
   folder if needed); print files say "IMPRESSAO" and the size; versions dated, not "final_final2".
4. Write the delivery message for the user to send (pt-BR, short): what's attached, where each file goes,
   print specs for the shop, what to do if something needs changing.
5. Log it: one dated line in `<memory>/log.md` (client, pieces, formats, notable decisions); client-specific
   learnings into their `preferences.md` (style-profile skill).
