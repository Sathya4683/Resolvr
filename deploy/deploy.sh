#!/usr/bin/env bash
#runs on the server: pull the latest code and restart whatever changed
#used by setup.sh the first time and by the github action on every push to main
set -euo pipefail

BRANCH="${1:-main}"
cd "$(dirname "$0")/.."

#the server never has local edits, so just match the remote branch (.env is gitignored, it stays)
git fetch --quiet origin "$BRANCH"
git checkout --quiet "$BRANCH" 2>/dev/null || git checkout --quiet -b "$BRANCH" "origin/$BRANCH"
git reset --quiet --hard "origin/$BRANCH"
echo "deploying $(git log -1 --format='%h %s')"

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
#old images pile up after every rebuild and the disk is only 40gb
docker image prune -f >/dev/null

docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format "table {{.Service}}\t{{.Status}}"
