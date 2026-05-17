#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/phillipsburg-radio/PhillipsburgRadio-iOS"
INSTALL_PARENT="$(dirname "$INSTALL_DIR")"
ENV_DIR="/etc/phillipsburg-radio"
ENV_FILE="$ENV_DIR/resolver.env"
SERVICE_FILE="/etc/systemd/system/phillipsburg-radio-resolver.service"
TIMER_FILE="/etc/systemd/system/phillipsburg-radio-resolver.timer"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this with sudo:"
  echo "sudo bash pi/install_on_pi.sh"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Installing Phillipsburg Radio resolver from:"
echo "$REPO_ROOT"

mkdir -p "$INSTALL_PARENT" "$INSTALL_DIR" "$ENV_DIR"

tar \
  --exclude=".git" \
  --exclude="build" \
  --exclude="DerivedData" \
  --exclude="current-feed.json" \
  -C "$REPO_ROOT" \
  -cf - . | tar -C "$INSTALL_DIR" -xf -

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 600 "$INSTALL_DIR/pi/broadcastify-resolver.env.example" "$ENV_FILE"
  echo "Created private config file:"
  echo "$ENV_FILE"
else
  chmod 600 "$ENV_FILE"
  echo "Private config already exists:"
  echo "$ENV_FILE"
fi

install -m 644 "$INSTALL_DIR/pi/systemd/phillipsburg-radio-resolver.service" "$SERVICE_FILE"
install -m 644 "$INSTALL_DIR/pi/systemd/phillipsburg-radio-resolver.timer" "$TIMER_FILE"

systemctl daemon-reload
systemctl enable phillipsburg-radio-resolver.timer

echo
echo "Install complete."
echo
echo "Next:"
echo "1. Edit $ENV_FILE"
echo "2. Test with:"
echo "   sudo systemctl start phillipsburg-radio-resolver.service"
echo "3. Check logs with:"
echo "   journalctl -u phillipsburg-radio-resolver.service -n 80 --no-pager"
echo "4. Start automatic refresh with:"
echo "   sudo systemctl start phillipsburg-radio-resolver.timer"
