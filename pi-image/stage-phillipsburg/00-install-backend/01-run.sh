#!/bin/bash -e

install -d "${ROOTFS_DIR}/opt/phillipsburg-radio/backend"
install -d "${ROOTFS_DIR}/etc/systemd/system"
install -d "${ROOTFS_DIR}/var/lib/phillipsburg-radio"
install -d "${ROOTFS_DIR}/boot/firmware"

install -m 0755 "files/backend/broadcastify_api_backend.py" \
  "${ROOTFS_DIR}/opt/phillipsburg-radio/backend/broadcastify_api_backend.py"

install -m 0755 "files/backend/phillipsburg_radio_server.py" \
  "${ROOTFS_DIR}/opt/phillipsburg-radio/backend/phillipsburg_radio_server.py"

install -m 0644 "files/systemd/phillipsburg-radio-backend.service" \
  "${ROOTFS_DIR}/etc/systemd/system/phillipsburg-radio-backend.service"

install -m 0644 "files/systemd/phillipsburg-radio-backend.timer" \
  "${ROOTFS_DIR}/etc/systemd/system/phillipsburg-radio-backend.timer"

install -m 0644 "files/systemd/phillipsburg-radio-server.service" \
  "${ROOTFS_DIR}/etc/systemd/system/phillipsburg-radio-server.service"

install -m 0644 "files/boot/phillipsburg-radio.env" \
  "${ROOTFS_DIR}/boot/firmware/phillipsburg-radio.env"

on_chroot <<'EOF'
systemctl enable phillipsburg-radio-backend.timer
systemctl enable phillipsburg-radio-server.service
systemctl enable ssh
EOF
