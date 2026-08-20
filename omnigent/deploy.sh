#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source "$SCRIPT_DIR/trial-target.env"
PROJECT=${GOOGLE_CLOUD_PROJECT:-${OMNIGENT_TRIAL_PROJECT:-$PROJECT_DEFAULT}}
ZONE=${OMNIGENT_TRIAL_ZONE:-$ZONE_DEFAULT}
INSTANCE=${OMNIGENT_TRIAL_INSTANCE:-$INSTANCE_DEFAULT}
VERSION=${OMNIGENT_VERSION:-v0.10.0}

required_files=(
  bootstrap-vm.sh
  trial-target.env
  configure-vm.sh
  trial-compose.yaml
  runner-config.yaml
  pi-trial.yaml
  pi-models.json
  pi-with-safety.sh
)
for file in "${required_files[@]}"; do
  test -f "$SCRIPT_DIR/$file"
done

if ! gcloud compute instances describe "$INSTANCE" \
  --project="$PROJECT" --zone="$ZONE" >/dev/null 2>&1; then
  gcloud compute instances create "$INSTANCE" \
    --project="$PROJECT" \
    --zone="$ZONE" \
    --machine-type=e2-medium \
    --image-family=ubuntu-2404-lts-amd64 \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --boot-disk-type=pd-balanced \
    --network=default \
    --no-address \
    --metadata-from-file="startup-script=$SCRIPT_DIR/bootstrap-vm.sh" \
    --labels=purpose=omnigent-trial
fi

status=$(gcloud compute instances describe "$INSTANCE" \
  --project="$PROJECT" --zone="$ZONE" --format='value(status)')
if [ "$status" != RUNNING ]; then
  gcloud compute instances start "$INSTANCE" --project="$PROJECT" --zone="$ZONE"
fi

external_ip=$(gcloud compute instances describe "$INSTANCE" \
  --project="$PROJECT" --zone="$ZONE" \
  --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
if [ -z "$external_ip" ]; then
  gcloud compute instances add-access-config "$INSTANCE" \
    --project="$PROJECT" --zone="$ZONE"
fi

for attempt in $(seq 1 90); do
  if gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" \
    --quiet --command='sudo test -s /opt/omnigent-trial/secrets/postgres-password && sudo systemctl is-active --quiet omnigent-trial-auto-stop.timer' \
    >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 90 ]; then
    echo "VM Bootstrap 未完成" >&2
    exit 1
  fi
  sleep 5
done

gcloud compute scp \
  "$SCRIPT_DIR/configure-vm.sh" \
  "$SCRIPT_DIR/trial-compose.yaml" \
  "$SCRIPT_DIR/runner-config.yaml" \
  "$SCRIPT_DIR/pi-trial.yaml" \
  "$SCRIPT_DIR/pi-models.json" \
  "$SCRIPT_DIR/pi-with-safety.sh" \
  "$INSTANCE:/tmp/" \
  --project="$PROJECT" --zone="$ZONE"

gcloud compute ssh "$INSTANCE" --project="$PROJECT" --zone="$ZONE" \
  --command="sudo env OMNIGENT_VERSION='$VERSION' bash /tmp/configure-vm.sh"

echo "WebUI 隧道: $SCRIPT_DIR/connect.sh"
