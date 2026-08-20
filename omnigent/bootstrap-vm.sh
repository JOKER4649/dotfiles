#!/usr/bin/env bash
set -Eeuo pipefail

install -d -m 0755 /opt/omnigent-trial

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl docker.io docker-compose-v2 openssl
systemctl enable --now docker

for attempt in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Docker daemon did not become ready" >&2
    exit 1
  fi
  sleep 2
done

install -d -m 0700 /opt/omnigent-trial/secrets
if [ ! -s /opt/omnigent-trial/secrets/postgres-password ]; then
  umask 077
  openssl rand -hex 32 > /opt/omnigent-trial/secrets/postgres-password
fi

# 试用 VM 自动停止，避免忘记关闭造成持续费用。
systemctl stop omnigent-trial-auto-stop.timer 2>/dev/null || true
systemctl disable omnigent-trial-auto-stop.timer 2>/dev/null || true
cat >/etc/systemd/system/omnigent-trial-auto-stop.service <<'UNIT'
[Unit]
Description=停止临时 OmniGent 试用 VM

[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl poweroff
UNIT
cat >/etc/systemd/system/omnigent-trial-auto-stop.timer <<'UNIT'
[Unit]
Description=六小时后自动停止临时 OmniGent 试用 VM

[Timer]
OnBootSec=6h
Unit=omnigent-trial-auto-stop.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now omnigent-trial-auto-stop.timer

echo "OmniGent VM Bootstrap 完成"
