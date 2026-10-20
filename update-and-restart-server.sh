#!/bin/sh

set -e

# Run from the project directory, regardless of where the script was called from
cd "$(dirname "$(realpath "$0")")"
. ./service.conf

./service-stop.sh

./backup-database-before-upgrade.sh

git pull origin main

./service-start.sh

./service-status.sh
