# memory-os

Two-tier persistent memory for [Claude Code](https://claude.com/claude-code), split by
**who is allowed to read it**.

|  | **Global tier** | **Project tier** |
|---|---|---|
| where | `~/.memory-os/memory/` | `<repo>/.claude/_memory/` |
| scope | you, everywhere | one repo |
| audience | private — you only | shared — the whole team |
| travels by | your machine (never committed) | the repo's own git |
| holds | who you are, how you work, your accounts | how this codebase works |

Claude reads both at the start of a session and answers like it already knows the context.
Because the project tier is committed, your teammates get the same memory when they clone —
without ever seeing anything personal about you.

## Install

```bash
git clone https://github.com/edunascimentt/memory-os.git ~/.memory-os
~/.memory-os/install.sh
```

Needs `bash` and `git`; `python3` for the JSON-merging bits (`init`'s hook, `accounts`).
On Windows use WSL or Git Bash — the installer creates symlinks, which plain Windows
restricts to Developer Mode or an elevated shell.

That seeds your private `memory/`, puts the `memory-os` command on your PATH, and links the
store into every Claude account config dir it finds. Re-run it any time — it's idempotent
and never overwrites memory you've already written.

Then say who you are:

```bash
$EDITOR ~/.memory-os/memory/me.md
```

## Add it to a project

```bash
cd <repo>
memory-os init
```

Creates `.claude/_memory/` from the templates and appends a pointer block to the repo's
`CLAUDE.md` so every session picks it up. Existing files are never overwritten. Fill in
`project.md` first — it orients every other answer about that repo. Commit it like any
other file; your teammates just clone and have it.

## When a teammate opens the repo

`init` also commits a `SessionStart` hook. When someone clones the repo and starts a
Claude Code session, it checks whether *their* machine has memory-os and, if it doesn't,
prints a short notice with the install command — and tells Claude that only the project
tier exists here, so it doesn't go hunting for a global tier that isn't there.

Nothing is blocked and nothing is installed for them; the project memory works on its own.
Once they install, the notice stops appearing.

The check lives in `.claude/memory-os-check.sh` — about 30 lines that test for a file and
print a message. Worth knowing: a committed hook is code that runs on your teammates'
machines at session start, so keep that file readable and review it in PRs like any other
script. To opt out, run `memory-os init --no-hook`, or delete the script plus the
`SessionStart` entry in `.claude/settings.json`.

## Before you share a repo

```bash
memory-os check
```

Greps the shared tier for emails, absolute home paths, and credential-shaped strings.
It catches patterns, not judgment — org IDs, dashboard URLs and client names still need
your eyes on `facts.md` and `people.md`.

## Commands

| | |
|---|---|
| `memory-os init [dir]` | add the shared project tier to a repo (`--no-hook` to skip the notice) |
| `memory-os check [dir]` | scan the project tier for personal data |
| `memory-os accounts` | list your Claude accounts, sync `memory/accounts.md` |
| `memory-os link` | symlink the store into every Claude account config dir |
| `memory-os wire-accounts` | add the SessionStart hook to every account's settings |
| `memory-os unwire-accounts` | remove it again — run before deleting `~/.memory-os` |
| `memory-os status` | store location, active account, linked accounts, this repo's tier |
| `memory-os update` | `git pull` the system files — never touches your memory |
| `memory-os session` | hook payload — self-heals the link, points the model at memory |

## Multiple accounts

If you run Claude Code from more than one account (different logins, one person),
each account gets its own `CLAUDE_CONFIG_DIR` and would otherwise get its own amnesia.
memory-os lives outside all of them at `~/.memory-os/` and is symlinked into each, so
every account reads and writes **one** memory and treats you as **one** person.

It integrates with [claude-accounts](https://github.com/edunascimentt/claude-accounts),
which switches accounts by exporting `CLAUDE_CONFIG_DIR`:

- **The registry is the source of truth.** `link`, `status` and `accounts` read
  `~/.claude-accounts/profiles.json` and report drift both ways — a profile whose directory
  is gone, a directory nobody registered. Without claude-accounts it falls back to globbing
  `~/.claude*`, so memory-os still works standalone.
- **`memory-os accounts`** lists your accounts, marks the active one, and regenerates the
  registry table in `memory/accounts.md`. The `login` and `purpose` columns you fill by hand
  survive every sync.
- **New accounts wire themselves.** `install.sh` adds a `SessionStart` hook to each account's
  `settings.json`, and `claude-add` copies `settings.json` into every account it creates — so
  a new account inherits the hook, and its first session self-heals its own symlink. Nothing
  to remember after adding an account.
- **The hook also carries the memory pointer.** claude-accounts deliberately does *not* copy
  `CLAUDE.md` into a new account (it would drag your personal instructions along), so a fresh
  account has nothing telling Claude where your memory lives. The hook injects that as session
  context instead: where the global tier is, which account is active, and that every account
  is the same person.

Run `memory-os wire-accounts` to (re)install the hook, `memory-os link` to (re)create the
symlinks. Both are idempotent.

Account-specific facts — which login, which plan — go in `memory/accounts.md`, never in
`me.md`, and never in a project tier.

## Layout

```
~/.memory-os/
├── CLAUDE.md              the spec Claude reads
├── install.sh
├── bin/memory-os
├── templates/
│   ├── global/            scaffold for the private tier
│   └── project/           scaffold for the shared tier + the CLAUDE.md pointer
└── memory/                YOUR private global memory — gitignored, never pushed
```

The `memory/` directory is in `.gitignore`. Cloning this repo gives you the system, not
somebody's memories. If you want your private tier backed up, put it in a **separate
private** repo — don't un-ignore it here.

## Uninstall

```bash
memory-os unwire-accounts        # FIRST — strips the hook from each account's settings
rm ~/.local/bin/memory-os
rm ~/.claude*/memory-os          # symlinks only
rm -rf ~/.memory-os              # this deletes your global memory too
```

Order matters: `unwire-accounts` needs the CLI to still exist. Skip it and every session
in every account keeps firing a hook that points at a binary that's gone — harmless, since
the command is guarded, but it lingers in your settings.

Project tiers live inside their own repos and are unaffected. To drop one, delete that
repo's `.claude/_memory/`, `.claude/memory-os-check.sh`, and the `SessionStart` entry in
its `.claude/settings.json`.

## License

MIT
