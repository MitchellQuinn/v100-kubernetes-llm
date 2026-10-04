#!/bin/sh
# Import an operator-provided archive into K3s's separate containerd image store.
set -eu
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  printf 'Usage: %s IMAGE_ARCHIVE\n' "$0" >&2
  exit 2
fi
exec sudo k3s ctr -n k8s.io images import "$1"
