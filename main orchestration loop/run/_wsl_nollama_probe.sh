#!/usr/bin/env bash
set -euo pipefail
NS="$(awk '/nameserver/{print $2; exit}' /etc/resolv.conf)"
GW="$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')"
echo "nameserver=$NS gateway=$GW"
for host in "$NS" "$GW" "127.0.0.1"; do
  for port in 8010 8000; do
    url="http://${host}:${port}/health"
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      echo "OK $url"
      exit 0
    fi
    echo "fail $url"
  done
done
exit 1
