#!/bin/sh

# Run the development server (Flask's built-in server), on localhost only.
# Usage: ./run-server-dev.sh [PORT]
# Always runs in debug mode (auto-reloader + debugger), whatever FLASK_DEBUG says in .env.
# The fake login user still comes from the .env file (see .env.development.example)

cd "$(dirname "$(realpath "$0")")"

HOST="127.0.0.1"
PORT="${1:-5010}"

exec python3 -m flask --app app --debug run --host "$HOST" --port "$PORT"
