#!/usr/bin/env bash
#runs on the server: check out a version of the code and restart whatever changed
#  ./deploy/deploy.sh            latest main
#  ./deploy/deploy.sh <sha|tag>  that exact version (rollback)
#used by setup.sh the first time, server.sh start, and the github action on every push to main
set -euo pipefail

#everything sits inside a function so bash reads the whole file before the checkout below changes it
main() {
  local ref="${1:-main}"
  cd "$(dirname "$0")/.."

  git fetch --quiet --tags origin
  #a branch name means its latest commit on github, anything else (sha, tag) is used as is
  if git show-ref --quiet --verify "refs/remotes/origin/$ref"; then
    ref="origin/$ref"
  fi
  #the server never has local edits, .env is gitignored so it stays
  git checkout --quiet --force --detach "$ref"
  echo "deploying $(git log -1 --format='%h %s')"

  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
  #old images pile up after every rebuild and the disk is only 40gb
  docker image prune -f >/dev/null

  docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format "table {{.Service}}\t{{.Status}}"
}

main "$@"
