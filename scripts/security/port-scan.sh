#!/usr/bin/env bash
# Escaneo de puertos sin dependencias (bash /dev/tcp).
#
# Uso: scripts/security/port-scan.sh <host> [puertos...]
# Ejemplo: scripts/security/port-scan.sh 127.0.0.1 22 80 443 3000 3001 8000
set -uo pipefail

HOST="${1:-127.0.0.1}"
shift || true
PORTS=("$@")
if [[ "${#PORTS[@]}" -eq 0 ]]; then
  PORTS=(22 80 443 3000 3001 5555 6379 6333 6334 8000 8001 4200)
fi

echo "# Port scan ${HOST} — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
for port in "${PORTS[@]}"; do
  if (echo >"/dev/tcp/${HOST}/${port}") >/dev/null 2>&1; then
    echo "- ${port}: OPEN"
  else
    echo "- ${port}: closed/filtered"
  fi
done
