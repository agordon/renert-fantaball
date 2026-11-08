#!/bin/sh
# Daily NBA data sync (schedule window, missing box scores, corrections, fantasy scores, league scoring).
# Safe to run from cron / a systemd timer: a database lock allows only ONE sync to run at a time,
# so overlapping runs or several web workers can never duplicate the work.
cd "$(dirname "$(realpath "$0")")/.."
PYTHON="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python
exec "$PYTHON" -m flask --app app nba daily
