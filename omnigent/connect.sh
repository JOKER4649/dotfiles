#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source "$SCRIPT_DIR/trial-target.env"
PROJECT=${GOOGLE_CLOUD_PROJECT:-${OMNIGENT_TRIAL_PROJECT:-$PROJECT_DEFAULT}}
ZONE=${OMNIGENT_TRIAL_ZONE:-$ZONE_DEFAULT}
INSTANCE=${OMNIGENT_TRIAL_INSTANCE:-$INSTANCE_DEFAULT}
status=$(gcloud compute instances describe "$INSTANCE" \
  --project="$PROJECT" --zone="$ZONE" --format='value(status)')
if [ "$status" != RUNNING ]; then
  gcloud compute instances start "$INSTANCE" \
    --project="$PROJECT" --zone="$ZONE"
fi

exec gcloud compute ssh "$INSTANCE" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --quiet \
  -- -N -L "${LOCAL_PORT}:127.0.0.1:6767"
