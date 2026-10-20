# Facts (this project)

> Durable project facts: conventions, endpoints, gotchas, where-things-live.
> One fact per line. Uncertain = `~` prefix.
>
> SHARED — written for the whole team. NO secrets/keys/tokens (env or a password manager),
> no personal emails, and no absolute paths from anyone's machine: write paths relative to
> the repo root. A key that is public BY DESIGN (already shipped in client code) is fine —
> say why it's public on the same line.

<!-- Example shape:
- API base: https://api.example.com/v2. Staging swaps `api` → `api-staging`.
- Migrations run on deploy, not on boot. Don't add boot-time migrate.
- `utils/legacy.py` is dead — slated for delete, don't extend it.
- ~ rate limit is 100 req/min per key (confirm with infra).
-->
