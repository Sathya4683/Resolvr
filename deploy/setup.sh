#!/usr/bin/env bash
#one command deploy, run from the laptop:
#creates the ec2 box (terraform), clones the repo on it, copies .env, starts the stack
#and gives the github action what it needs to redeploy on every push to main.
#safe to run again, every step skips what's already done.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
BRANCH="${BRANCH:-main}"
TF="terraform -chdir=terraform"

for tool in terraform aws gh ssh openssl; do
  command -v "$tool" >/dev/null || { echo "missing $tool"; exit 1; }
done
[ -f "$ROOT/.env" ] || { echo "no .env in the repo root, copy .env.example and fill it in first"; exit 1; }
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

echo "==> creating the server"
$TF init -input=false >/dev/null
$TF apply -auto-approve -input=false
IP="$($TF output -raw public_ip)"
HOST="$($TF output -raw app_host)"

#the box gets a fresh host key when recreated, so don't pin it
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5)
remote() { ssh "${SSH_OPTS[@]}" "ubuntu@$IP" "$@"; }

echo "==> waiting for $IP to boot and install docker"
until remote true 2>/dev/null; do sleep 5; done
remote "cloud-init status --wait >/dev/null; docker --version"

echo "==> ssh key for the github action"
mkdir -p .keys
[ -f .keys/gh_deploy ] || ssh-keygen -t ed25519 -N "" -C "resolvr-github-actions" -f .keys/gh_deploy -q
PUB="$(cat .keys/gh_deploy.pub)"
remote "grep -qxF '$PUB' ~/.ssh/authorized_keys || echo '$PUB' >> ~/.ssh/authorized_keys"

echo "==> letting the server pull the (private) repo"
remote "test -f ~/.ssh/id_ed25519 || ssh-keygen -t ed25519 -N '' -C resolvr-ec2 -f ~/.ssh/id_ed25519 -q
        grep -qs github.com ~/.ssh/known_hosts || ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null"
remote "cat ~/.ssh/id_ed25519.pub" > .keys/server.pub
#read-only deploy key, errors out if it's already added which is fine
gh repo deploy-key add .keys/server.pub --repo "$REPO" --title "resolvr-ec2" 2>/dev/null || echo "(deploy key already there)"
remote "test -d ~/resolvr || git clone --quiet git@github.com:$REPO.git ~/resolvr"

echo "==> .env for the server"
#keep secrets from the last run: people stay logged in, and grafana only reads its password once
JWT="$(remote "grep -s '^JWT_SECRET=' ~/resolvr/.env | cut -d= -f2-" || true)"
[ -n "$JWT" ] || JWT="$(openssl rand -hex 32)"
GF_PASS="$(remote "grep -s '^GRAFANA_ADMIN_PASSWORD=' ~/resolvr/.env | cut -d= -f2-" || true)"
[ -n "$GF_PASS" ] || GF_PASS="$(grep -s '^GRAFANA_ADMIN_PASSWORD=' "$ROOT/.env" | cut -d= -f2- || true)"
#grafana is public on the server, never leave it on admin/admin
if [ -z "$GF_PASS" ] || [ "$GF_PASS" = "admin" ]; then GF_PASS="$(openssl rand -hex 8)"; fi

ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
grep -vE '^(ENVIRONMENT|APP_HOST|FRONTEND_URL|CORS_ORIGINS|JWT_SECRET|GRAFANA_ADMIN_PASSWORD)=' "$ROOT/.env" > "$ENV_FILE"
cat >> "$ENV_FILE" <<EOF

#set by deploy/setup.sh
ENVIRONMENT=prod
APP_HOST=$HOST
FRONTEND_URL=https://$HOST
CORS_ORIGINS=https://$HOST
JWT_SECRET=$JWT
GRAFANA_ADMIN_PASSWORD=$GF_PASS
EOF
scp -q "${SSH_OPTS[@]}" "$ENV_FILE" "ubuntu@$IP:resolvr/.env"

echo "==> starting the app (first time builds images + downloads the models, ~5-10 min)"
remote "cd ~/resolvr && ./deploy/deploy.sh $BRANCH"

echo "==> github secrets for auto deploy"
gh secret set EC2_HOST --repo "$REPO" --body "$IP"
gh secret set EC2_SSH_KEY --repo "$REPO" < .keys/gh_deploy

cat <<EOF

done!
  app      https://$HOST
  api docs https://$HOST/docs
  grafana  https://grafana.$HOST   (admin / $GF_PASS)
  ssh      ssh ubuntu@$IP
  logs     ssh ubuntu@$IP 'cd resolvr && docker compose logs -f api worker'

stop it after the demo:  ./deploy/server.sh stop
EOF
