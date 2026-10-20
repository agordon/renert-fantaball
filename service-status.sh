#!/bin/sh

# Run from the project directory, regardless of where the script was called from
cd "$(dirname "$(realpath "$0")")"
. ./service.conf

systemctl status --no-pager "${SERVICE_NAME}.service"
