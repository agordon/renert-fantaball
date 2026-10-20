#!/bin/sh

set -e

# Run from the project directory, regardless of where the script was called from
cd "$(dirname "$(realpath "$0")")"
. ./service.conf

cp instance/database.db "instance/database-$(date +%F-%H%M%S)-before-upgrade.db"
