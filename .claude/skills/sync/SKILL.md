---
name: sync
description: Sync this designassist checkout with the team on GitHub, both ways. Pulls what colleagues pushed (code, skills, project memory) and installs any new dependencies, then commits everything new here (tools, skills, tests, .claude/_memory) and pushes it so the others get it. Use for "commita e dá push", "sobe tudo", "sincroniza o repo", "puxa as novidades", "atualiza o designassist", "git push/pull", or at the end of a session that changed the repo.
---
# sync

Two-way sync: **pull first, then push**. Colleagues update from `main`, so finished work must land on
`origin/main`. Run every step from the repo root.

What travels and what doesn't:
- Travels (committed): `src/`, `.claude/skills/`, `tests/`, `memory.template/`, docs, `vendor/`, and the
  shared project memory `.claude/_memory/`.
- Never travels: `projects/` (client files and designs), `.env` and `.designassist/` (keys), the private
  design memory and brand kits (`uv run da memory` folder, `~/.memory-os/`), `memory/`, `assets/user-fonts/`
  (downloaded or licensed fonts). They are gitignored; never `git add -f` them. A lesson that would help
  colleagues (a tool gotcha, not someone's taste or a client's brand) goes into `.claude/_memory/facts.md`
  first, written without personal data.

## 1. Look
```
git fetch origin --prune
git status --short
git branch --show-current
git log --oneline @{u}..HEAD; git log --oneline HEAD..@{u}
git log --oneline HEAD..origin/main
```
Nothing local and nothing new: say "already in sync" and stop. A rebase/merge in progress: finish or abort
it first.

## 2. Check before committing (only with local changes)
- Read `git diff` and the untracked files. Open each new file you didn't write in this session.
- Secrets: `git diff HEAD | grep -nE "sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|(api|secret|access)[_-]?key\s*[:=]\s*['\"][^'\"]{12,}"`
  plus new untracked files. Any hit: stop, show file and line (never the value). Client images, PSD/AI,
  fonts (`.ttf/.otf`) outside `assets/fonts/`: stop and ask.
- Shared memory: `bash vendor/memory-os/bin/memory-os check`; fix what it reports.
- Code changed: `uv run pytest -q -m "not network"`. Red: fix it or tell the user; never push red to `main`.

## 3. Commit
`git add -A`, `git status --short` to confirm nothing ignored-on-purpose slipped in. Split unrelated changes
into a few commits. Style: `feat: ...`, `fix: ...`, `docs: ...`, `chore(memory): ...`, short body, ending with
the attribution lines the session gives for commits.

## 4. Pull
```
git pull --rebase origin <current-branch>
git merge origin/main            # on a feature branch, when main moved
```
`.claude/_memory/facts.md`, `decisions.md`, `people.md` use `merge=union`: afterwards dedupe lines and keep the
newer fact (decisions.md: never edit an old entry). Other conflicts: keep both sides' intent; ask the user when
unsure. `uv.lock`: take theirs, then `uv lock`.

## 5. Install what the pull brought
`git diff --name-only <before> HEAD`: `pyproject.toml`/`uv.lock` → `uv sync`; `vendor/memory-os/` →
`uv run da memory --install`; `memory.template/` → `uv run da memory --init`. Then `uv run da doctor`.

## 6. Push
`git push origin HEAD` (new branch: `-u`). From a feature branch to main: `git merge-base --is-ancestor
origin/main HEAD` then `git push origin HEAD:main` (fast-forward, never `--force`). If the user prefers review:
`gh pr create --base main` (body ends with the session's PR attribution line); ask once and save the answer to
`<memory>/preferences.md`. Rejected push: back to step 4.

## 7. Report
What came in (by author), what you pushed (commit subjects), what you installed, anything left undone.
