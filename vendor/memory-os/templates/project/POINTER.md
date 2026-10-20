## Project memory (memory-os)

This repo carries its own memory in `.claude/_memory/`. Every session working here MUST
read it: start with `_index.md`, then `project.md`, `focus.md`, `facts.md`, `people.md`,
`decisions.md`. Skip files that are still empty templates. Don't announce the reads —
just answer like you already know the context.

Keep it true as you work: one fact per line, dates absolute (`YYYY-MM-DD`), `~` = uncertain,
`decisions.md` is append-only (supersede with a new entry, never edit a past one), and
update the `_index.md` hook whenever a file changes substantially.

**This tier is committed and read by everyone with repo access.** Never write personal
data into it — no personal emails, no absolute paths from someone's machine, no account
logins, org/team IDs, or secrets. Anything personal belongs in the author's private global
memory instead. Full spec: `~/.memory-os/CLAUDE.md` (install: github.com/edunascimentt/memory-os).
