#!/usr/bin/env bash
# Resolve a NoLlama OpenAI base URL reachable from WSL2 (Windows-hosted server).
wsl_resolve_nollama_url() {
  if [[ -n "${NOLLAMA_OPENAI_BASE_URL:-}" ]]; then
    echo "$NOLLAMA_OPENAI_BASE_URL"
    return 0
  fi
  local candidates=()
  if [[ -f /etc/resolv.conf ]]; then
    local ns
    ns="$(awk '/nameserver/{print $2; exit}' /etc/resolv.conf)"
    [[ -n "$ns" ]] && candidates+=("$ns")
  fi
  local gw
  gw="$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')"
  [[ -n "$gw" ]] && candidates+=("$gw")
  candidates+=("host.docker.internal" "127.0.0.1")
  local host port
  for host in "${candidates[@]}"; do
    for port in 8010 8000; do
      if curl -fsS --max-time 2 "http://${host}:${port}/health" >/dev/null 2>&1; then
        echo "http://${host}:${port}/v1"
        return 0
      fi
    done
  done
  return 1
}
