#!/bin/sh
# Start Pulse as the unprivileged "pulse" user.
#
# Volumes and bind mounts can be owned by root, which the pulse user couldn't
# write to. When started as root, fix the data directory's ownership
# first, then drop privileges for good before running Pulse.
set -eu

data_dir="${PULSE_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$data_dir"
  chown -R pulse:pulse "$data_dir"
  # setpriv keeps root's environment; give the pulse user its own home.
  HOME=/home/pulse exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"
fi

exec "$@"
