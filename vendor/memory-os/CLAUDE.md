# memory-os — full spec

Persistent memory for Claude Code, split in two by **who is allowed to read it**.

|  | GLOBAL tier | PROJECT tier |
|---|---|---|
| where | `~/.memory-os/memory/` | `<repo>/.claude/_memory/` |
| scope | the user, everywhere | one repo |
| audience | **private — him only** | **shared — the whole team** |
| synced by | the machine (never committed) | the repo's own git |
| holds | who he is, how he works, his accounts | how THIS codebase works |

The two never mix. That separation is the point of the system: the project tier is
committed and read by coworkers, so nothing personal may ever land in it.

**Canonical location: `~/.memory-os/`** — deliberately OUTSIDE any Claude config dir,
because the user runs several accounts and each has its own `CLAUDE_CONFIG_DIR`.
Every account dir gets a symlink (`$CLAUDE_CONFIG_DIR/memory-os` → `~/.memory-os`), so
both `~/.memory-os/...` and `~/.claude*/memory-os/...` reach the same files. One copy.

---

## GLOBAL tier — `~/.memory-os/memory/` (private)

Follows the user everywhere: every repo, every session, **every account**.
Never committed anywhere — `.gitignore`d even inside this repo.

- `me.md` — who he is: identity, role, languages, machine, hard constraints.
- `preferences.md` — how he wants Claude to work: style, defaults, pet peeves.
- `accounts.md` — the accounts he switches between; what is account-scoped.
- `journal/log.md` — dated running log across projects. Append-only.
- `_index.md` — one line per file. Read first.

## PROJECT tier — `<repo>/.claude/_memory/` (shared)

Scoped to one repo, versioned with it, **written for a team to read**.

- `_index.md` — one line per file + datestamped highlights. Read first.
- `project.md` — what it is, stack, how to run, constraints.
- `focus.md` — active priorities, deadlines, blockers. Current only.
- `facts.md` — conventions, gotchas, where-things-live.
- `decisions.md` — append-only log of real decisions.
- `people.md` — roles on this project, in professional terms only.

### Never in the project tier

Assume every person with repo access reads these files, forever, including after
the repo goes public. So they must never contain:

- Personal emails, phone numbers, handles, or home addresses. Refer to a person by
  role or first name — the identity mapping stays in the global tier.
- Absolute paths from someone's machine (`/Users/x/…`, `C:\Users\x\…`). Write paths
  relative to the repo root.
- Account logins, org/team IDs, billing or plan detail, dashboard URLs tied to a person.
- Secrets, keys, tokens — in ANY tier. Those live in env vars or a password manager.
  (A key that is public *by design*, like a Supabase publishable key already shipped in
  client JS, is fine — say why it's public on the same line.)
- Anything about the user personally: preferences, schedule, health, opinions of people.

If a fact is genuinely needed to work on the repo but fails the list above, keep the
*technical shape* in the project tier and move the *identifying part* to the global tier.
Example: "deployed to Vercel under the owner's team (team ID in global `accounts.md`)".

Run `memory-os check` before sharing a repo — it greps the project tier for exactly these.

### Onboarding a teammate

`init` commits `.claude/memory-os-check.sh` plus a `SessionStart` hook that runs it. On a
machine without memory-os it prints the install command and injects context saying only the
project tier exists here — so don't go looking for `~/.memory-os/memory/` files that aren't
there. It blocks nothing and installs nothing. Silent once memory-os is present.

## On every session

1. Silently read GLOBAL: `me.md` + `preferences.md`, skim `journal/log.md`.
   Read `accounts.md` too if anything about the active account comes up.
2. Silently read PROJECT: every `*.md` in `.claude/_memory/` — `_index.md` first, then
   the rest. Skip files that are still empty templates.
3. Never announce or list these reads. Just answer like you already know the context.

## Multi-account

The user switches accounts with his own `claude-accounts` CLI, which exports
`CLAUDE_CONFIG_DIR` before launching Claude Code.

- **Every account is the same person, on one profile.** A different account is a different
  billing/login, never a different user. Identity and preferences apply unchanged across
  all of them, and all of them read and write the same global memory.
- **Never infer identity from the signed-in account.** The login email or profile label may
  be someone else's name. `me.md` is the only source of truth for who he is.
- The harness's own per-account, per-project memory is NOT shared between accounts.
  Don't rely on it for anything durable — put durable facts in memory-os.
- Account-scoped facts (logins, which plan, integrations wired on only one) go in
  `accounts.md`, tagged with the account key. Never in `me.md` / `preferences.md`.
- New accounts need no action. Each account's `settings.json` carries a `SessionStart` hook
  running `memory-os session`, and `claude-add` copies `settings.json` into accounts it
  creates — so a new account inherits the hook and self-heals its symlink on first use.
  That hook is also what injects the memory pointer, since claude-accounts deliberately
  does not copy `CLAUDE.md` into a new account.
- `memory-os accounts` regenerates the registry table in `accounts.md` from
  `~/.claude-accounts/profiles.json`, preserving the hand-written login/purpose columns,
  and reports drift in both directions.

## Routing — where a new fact goes

- About the user generally (identity, global style) → GLOBAL `me.md` / `preferences.md`.
- About one account specifically → GLOBAL `accounts.md`, tagged with the account key.
- About one repo (conventions, paths, stack, decisions) → that repo's `.claude/_memory/`.
- Implicit preference inferred from a reaction → GLOBAL `preferences.md`
  (`~` prefix on first signal, drop the `~` on the second).
- Real decision (chosen approach + why) → dated entry appended to PROJECT `decisions.md`.
- Cross-project event worth remembering later → GLOBAL `journal/log.md`.
- **When in doubt about which tier: does a coworker need it to work on this repo, and
  would he be fine with them reading it forever? Both yes → project. Otherwise → global.**

## Keep memory true

- One fact per line. Edit in place — don't stack contradictions.
- Append-only files (`decisions.md`, `journal/log.md`): never edit a past entry.
  Supersede it with a NEW dated entry that says what changed and why.
- When a file changes substantially, update its `_index.md` hook in the same pass.
- Convert dates to absolute `YYYY-MM-DD`. `~` prefix = uncertain, confirm before relying on it.
- Prune what went stale. A finished goal leaves `focus.md`; it doesn't rot there.

## Commands

- `memory-os init` — add the project tier to the repo in the current directory
  (`--no-hook` skips the session-start install notice).
- `memory-os check` — scan a project tier for personal data before sharing.
- `memory-os link` — (re)symlink the store into every Claude account config dir.
- `memory-os status` — where the store is, which accounts see it, what this repo has.
- `memory-os update` — pull the latest system files (never touches your memory).
