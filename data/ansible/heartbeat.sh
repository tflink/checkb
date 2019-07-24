#!/usr/bin/env bash

# print usage
if [ "$1" = '--help' ] || [ "$1" = '-h' ]; then
    echo \
"This is a helper script that prints heart beat into a file until the process \
is killed. This helps with tasks that should run for at least some minimum \
time before they're killed by a watchdog for inactivity. The heartbeat log \
simulates activity for a specified time."
    echo
    echo "Usage: $0 start FILE INTERVAL KEEPALIVE"
    echo "Start heartbeat logging into FILE every INTERVAL seconds for " \
         "KEEPALIVE seconds"
    echo "Usage: $0 stop FILE"
    echo "Stop heartbeat logging into FILE"
    exit 1
fi

ACTION="$1"
FILE="$2"
INTERVAL="$3"
KEEPALIVE="$4"

function start {
  echo "PID: $$" >> "$FILE"
  LAST_BEAT=0
  while [ "$SECONDS" -lt "$KEEPALIVE" ]; do
    if [ "$((SECONDS - LAST_BEAT))" -ge "$INTERVAL" ]; then
      LAST_BEAT=$SECONDS
      echo "Alive for $SECONDS seconds" >> "$FILE"
    fi
    sleep 1
  done
  echo -e "Lived $SECONDS seconds\nTIMED OUT" >> "$FILE"
}

function stop {
  if [ -e "$FILE" ]; then
    if [ "`tail -n1 "$FILE"`" != "TIMED OUT" ]; then
      kill -9 "`grep PID "$FILE" | tail -n 1 | cut -d ' ' -f 2`"
      echo "Terminating heartbeat" >> "$FILE"
    fi
  fi
}

case "$ACTION" in
  start)
    start ;;
  stop)
    stop ;;
  *)
    echo 'Invalid action. See --help'
    exit 1
    ;;
esac
