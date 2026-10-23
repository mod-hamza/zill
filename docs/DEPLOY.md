# Deploying Zill

Zill runs on the Contabo VM (`169.58.66.146`, host `n8n-host`) next to n8n, searxng and nocturne-jam,
behind the existing Caddy container. Every push to `main` on GitHub goes live by itself within a few
minutes; nothing else is involved (no GitHub Actions, no deploy keys stored anywhere).

| URL | Notes |
|---|---|
| https://zill.itshamza.me | primary (DNS A record `zill` → `169.58.66.146` at Namecheap; Let's Encrypt cert via Caddy, auto-renewed) |
| https://zill.169-58-66-146.sslip.io | works without DNS (sslip.io resolves the embedded IP) |

## How it works

```
git push origin main
        │
        ▼
VM: systemd timer zill-cd.timer (every 2 min) → /home/hamza/zill/deploy/cd.sh
        │  git fetch; new commit?
        ▼
docker compose build (images tagged with the commit) → up -d
        │
        ▼
health check: API warm-up done + /film renders
        ├─ ok   → record commit in deploy/.deployed, prune old images
        └─ fail → roll back to the previous commit's images
```

- `deploy/Dockerfile.api` — Python 3.11, FastAPI + engine + baked data (`data/`).
- `deploy/Dockerfile.web` — Next.js production build; `/api` is compiled to proxy to `zill-api:8000`.
- `deploy/docker-compose.yml` — containers `zill-api`, `zill-web` on Caddy's network `n8n-stack_default`;
  no host ports.
- `deploy/Caddyfile.snippet` — the site block in `/home/hamza/n8n-stack/Caddyfile`. `/api/*` goes
  straight to the API (agent SSE streams unbuffered), everything else to Next.

## Day to day (on the VM, as root)

```bash
journalctl -u zill-cd -n 50          # what the last deploys did
systemctl list-timers zill-cd.timer  # next check
/home/hamza/zill/deploy/cd.sh --force   # redeploy now (same commit)
docker logs -f zill-api              # API logs
```

The live LLM key goes in `/home/hamza/zill/.env` (`ZILL_LLM_API_KEY=...`, see `.env.example`); then
`cd.sh --force`. The file is git-ignored and never leaves the VM.

## Removing it

```bash
systemctl disable --now zill-cd.timer && rm /etc/systemd/system/zill-cd.*
docker compose -f /home/hamza/zill/deploy/docker-compose.yml down
# delete the zill block from /home/hamza/n8n-stack/Caddyfile, then:
docker exec n8n-stack-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```
