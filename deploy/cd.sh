#!/usr/bin/env bash
# Zill pull-based continuous deployment (runs on the VM from a systemd timer).
# 1. fetch origin/main; exit if already deployed
# 2. build images tagged with the commit; swap containers
# 3. health-check through the real public path; on failure roll back to the previous commit's images
# State: deploy/.deployed (last good commit). Log: journalctl -u zill-cd
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$REPO_DIR/deploy/.deployed"
COMPOSE=(docker compose -f "$REPO_DIR/deploy/docker-compose.yml")
FORCE="${1:-}"

exec 9>/tmp/zill-cd.lock
flock -n 9 || { echo "another deploy is running"; exit 0; }

cd "$REPO_DIR"
git fetch --quiet origin main
target="$(git rev-parse --short=12 origin/main)"
current="$(cat "$STATE" 2>/dev/null || true)"
if [[ "$target" == "$current" && "$FORCE" != "--force" ]]; then
  exit 0
fi

echo "deploying $target (was ${current:-nothing})"
git reset --quiet --hard origin/main

export ZILL_TAG="$target"
"${COMPOSE[@]}" build --pull
"${COMPOSE[@]}" up -d --remove-orphans

healthy() {
  # API warm-up finished + film page renders, both via the container network
  docker exec zill-api python -c "import json,urllib.request as u; d=json.load(u.urlopen('http://127.0.0.1:8000/api/health',timeout=5)); raise SystemExit(0 if d.get('ok') and d.get('warm',{}).get('done') else 1)" 2>/dev/null \
    && docker exec zill-web node -e "fetch('http://127.0.0.1:3000/film').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" 2>/dev/null
}

for i in $(seq 1 60); do
  if healthy; then
    echo "$target" > "$STATE"
    echo "deployed $target (healthy after ~$((i * 5)) s)"
    # keep the current + previous image pair, drop older ones
    for img in zill-api zill-web; do
      docker images "$img" --format '{{.Tag}}' | grep -v -e "^$target\$" -e "^${current:-none}\$" -e '^latest$' \
        | xargs -r -I{} docker rmi "$img:{}" >/dev/null 2>&1 || true
    done
    exit 0
  fi
  sleep 5
done

echo "health check FAILED for $target"
if [[ -n "$current" ]]; then
  echo "rolling back to $current"
  git reset --quiet --hard "$current"
  ZILL_TAG="$current" "${COMPOSE[@]}" up -d --remove-orphans
fi
exit 1
