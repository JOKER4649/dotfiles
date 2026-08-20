#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=/opt/omnigent-trial
VERSION=${OMNIGENT_VERSION:-v0.10.0}
BASE_URL="https://raw.githubusercontent.com/omnigent-ai/omnigent/${VERSION}/deploy/docker/docker-compose.yaml"

install -d -m 0755 "$ROOT"
curl -fsSL "$BASE_URL" -o "$ROOT/docker-compose.yaml"
install -m 0644 /tmp/trial-compose.yaml "$ROOT/trial-compose.yaml"

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

for attempt in $(seq 1 60); do
  if curl -fsS -o /dev/null http://127.0.0.1:6767/; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    docker compose -f docker-compose.yaml -f trial-compose.yaml ps
    docker compose -f docker-compose.yaml -f trial-compose.yaml logs --tail=80 omnigent runner
    exit 1
  fi
  sleep 2
done

docker compose -f docker-compose.yaml -f trial-compose.yaml ps
