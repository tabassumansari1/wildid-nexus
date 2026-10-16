#!/bin/sh
# Bring Pugmark back on the preview port. Idempotent.
if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8080/; then
  exit 0
fi
cd /workspace/pugmark
nohup python3 manage.py runserver 0.0.0.0:8080 --noreload > /tmp/pugmark-dev.log 2>&1 &
i=0
while [ "$i" -lt 25 ]; do
  if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8080/; then
    exit 0
  fi
  i=$((i + 1))
  sleep 0.3
done
echo "Pugmark did not start" >&2
exit 1
