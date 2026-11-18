#!/usr/bin/env bash
# Comprueba que los .env locales no son legibles por otros usuarios.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FAILED=0

for file in .env services/api/.env mcps/trackflow-mcp/.env; do
  path="${ROOT}/${file}"
  if [[ ! -f "${path}" ]]; then
    echo "- ${file}: no existe (ok)"
    continue
  fi
  perms="$(stat -f '%Lp' "${path}" 2>/dev/null || stat -c '%a' "${path}")"
  if [[ "${perms}" == "600" || "${perms}" == "400" ]]; then
    echo "- ${file}: ${perms} ✅"
  else
    echo "- ${file}: ${perms} ❌ (debe ser 600 o 400)"
    FAILED=1
  fi
done

exit "${FAILED}"
