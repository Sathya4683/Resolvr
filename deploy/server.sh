#!/usr/bin/env bash
#start / stop the demo server so it only costs money while i'm showing it
#usage: ./deploy/server.sh start | stop | status | destroy
set -euo pipefail

cd "$(dirname "$0")"
TF="terraform -chdir=terraform"
ID="$($TF output -raw instance_id)"
IP="$($TF output -raw public_ip)"
HOST="$($TF output -raw app_host)"
REGION="$($TF output -raw region)"

case "${1:-status}" in
  start)
    aws ec2 start-instances --region "$REGION" --instance-ids "$ID" >/dev/null
    echo "starting $ID..."
    aws ec2 wait instance-running --region "$REGION" --instance-ids "$ID"
    #docker brings the containers back by itself, this also pulls anything pushed while it was off
    until ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5 \
      "ubuntu@$IP" "cd ~/resolvr && ./deploy/deploy.sh main"; do sleep 5; done
    echo "up at https://$HOST (give the api a minute to load the models)"
    ;;
  stop)
    aws ec2 stop-instances --region "$REGION" --instance-ids "$ID" >/dev/null
    echo "stopping $ID, data stays on the disk"
    ;;
  status)
    aws ec2 describe-instances --region "$REGION" --instance-ids "$ID" \
      --query "Reservations[0].Instances[0].State.Name" --output text
    echo "https://$HOST"
    ;;
  destroy)
    #deletes the server, the disk (db included) and the ip
    $TF destroy
    ;;
  *)
    echo "usage: $0 start | stop | status | destroy"
    exit 1
    ;;
esac
