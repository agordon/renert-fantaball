#!/bin/sh

mkdir -p run logs instance

NAME="project-name"

PID="run/${NAME}.pid"
SOCKET="run/${NAME}.socket"

exec \
 setpriv --nnp \
   gunicorn3 \
       --workers 1 \
       --capture-output \
       --pid "$PID" \
       -n "$NAME" \
       -b "unix://$SOCKET" --umask 000 \
       --access-logfile "logs/access.log" \
       --error-logfile "logs/error.log" \
       app:app
