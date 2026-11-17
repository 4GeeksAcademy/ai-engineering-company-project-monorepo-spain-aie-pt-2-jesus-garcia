#!/usr/bin/env bash
# Permisos explícitos de carpetas para separar código, logs, datos y secretos.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este script como root." >&2
  exit 1
fi

OPS_USER="${OPS_USER:-trackflow-ops}"
OPS_GROUP="${OPS_GROUP:-trackflow}"
ROOT="${TRACKFLOW_ROOT:-/srv/trackflow}"

install -d -m 750 -o "${OPS_USER}" -g "${OPS_GROUP}" "${ROOT}/app"
install -d -m 750 -o "${OPS_USER}" -g "${OPS_GROUP}" "${ROOT}/logs"
install -d -m 750 -o "${OPS_USER}" -g "${OPS_GROUP}" "${ROOT}/data"
install -d -m 700 -o root -g root "${ROOT}/secrets"

# Secretos: solo root. El despliegue los inyecta como variables de entorno.
find "${ROOT}/secrets" -type f -exec chmod 600 {} \;
find "${ROOT}/secrets" -type f -exec chown root:root {} \;

# .env locales del repo (si existen) nunca legibles por otros usuarios.
for env_file in .env services/api/.env mcps/trackflow-mcp/.env; do
  if [[ -f "${env_file}" ]]; then
    chmod 600 "${env_file}"
  fi
done

echo "Permisos aplicados:"
stat -c '%a %U:%G %n' "${ROOT}" "${ROOT}/app" "${ROOT}/logs" "${ROOT}/data" "${ROOT}/secrets"
