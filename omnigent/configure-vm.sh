#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/opt/omnigent-trial
VERSION=${OMNIGENT_VERSION:-v0.10.0}
BASE_URL="https://raw.githubusercontent.com/omnigent-ai/omnigent/${VERSION}/deploy/docker/docker-compose.yaml"

install -d -m 0755 "$ROOT"
curl -fsSL "$BASE_URL" -o "$ROOT/docker-compose.yaml"
install -m 0644 /tmp/trial-compose.yaml "$ROOT/trial-compose.yaml"
install -m 0644 /tmp/runner-config.yaml "$ROOT/runner-config.yaml"
install -m 0644 /tmp/pi-trial.yaml "$ROOT/pi-trial.yaml"

umask 077
postgres_password=$(cat "$ROOT/secrets/postgres-password")
cat >"$ROOT/.env" <<EOF
COMPOSE_PROJECT_NAME=omnigent-trial
POSTGRES_PASSWORD=${postgres_password}
OMNIGENT_PORT=127.0.0.1:6767
OMNIGENT_IMAGE_TAG=${VERSION}
EOF

cd "$ROOT"
docker compose -f docker-compose.yaml -f trial-compose.yaml config >/dev/null
docker compose -f docker-compose.yaml -f trial-compose.yaml pull
docker compose -f docker-compose.yaml -f trial-compose.yaml up -d
runner_container=$(docker compose -f docker-compose.yaml -f trial-compose.yaml ps -q runner)
if [ -z "$runner_container" ]; then
  docker compose -f docker-compose.yaml -f trial-compose.yaml ps
  exit 1
fi
docker cp /tmp/pi-trial.yaml "${runner_container}:/workspace/pi-trial.yaml"

for attempt in $(seq 1 60); do
  server_container=$(docker compose -f docker-compose.yaml -f trial-compose.yaml ps -q omnigent)
  postgres_container=$(docker compose -f docker-compose.yaml -f trial-compose.yaml ps -q postgres)
  server_health=$(docker inspect --format='{{.State.Health.Status}}' "$server_container" 2>/dev/null || true)
  postgres_health=$(docker inspect --format='{{.State.Health.Status}}' "$postgres_container" 2>/dev/null || true)
  runner_status=$(docker inspect --format='{{.State.Status}}' "$runner_container" 2>/dev/null || true)
  if curl -fsS -o /dev/null http://127.0.0.1:6767/ \
    && [ "$server_health" = healthy ] \
    && [ "$postgres_health" = healthy ] \
    && [ "$runner_status" = running ]; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    docker compose -f docker-compose.yaml -f trial-compose.yaml ps
    docker compose -f docker-compose.yaml -f trial-compose.yaml logs --tail=80 postgres omnigent runner
    exit 1
  fi
  sleep 2
done

docker compose -f docker-compose.yaml -f trial-compose.yaml ps
