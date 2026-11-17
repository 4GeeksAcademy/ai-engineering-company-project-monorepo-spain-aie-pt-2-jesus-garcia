#!/usr/bin/env bash
# Valida la configuración de endurecimiento sin necesidad de un host Linux.
#
# - `sshd -t -f` dentro de un contenedor Debian.
# - `bash -n` de todos los scripts.
# - Comprobación estática de UFW (solo 22/80/443) y de compose (sin puertos
#   publicados en 0.0.0.0).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HARDENING="${REPO_ROOT}/scripts/security/hardening"

echo "## Sintaxis de scripts"
for script in "${HARDENING}"/*.sh "${REPO_ROOT}"/scripts/security/*.sh; do
  bash -n "${script}"
  echo "- ✅ ${script#"${REPO_ROOT}/"}"
done

echo
echo "## sshd -t (contenedor)"
docker run --rm \
  -v "${HARDENING}/sshd_trackflow.conf:/tmp/sshd_trackflow.conf:ro" \
  debian:bookworm-slim \
  sh -c 'mkdir -p /run/sshd && apt-get update -qq >/dev/null && apt-get install -y -qq openssh-server >/dev/null && sshd -t -f /tmp/sshd_trackflow.conf'
echo "- ✅ configuración sshd válida"

echo
echo "## UFW: puertos permitidos"
if grep -Eq 'ufw allow 80/tcp' "${HARDENING}/30-firewall.sh" \
  && grep -Eq 'ufw allow 443/tcp' "${HARDENING}/30-firewall.sh" \
  && { grep -Eq 'ufw limit .*SSH_PORT|ufw allow from .*SSH_PORT' "${HARDENING}/30-firewall.sh"; }; then
  echo "- ✅ solo 22 (ops), 80 y 443"
else
  echo "- ❌ revisar reglas UFW"
  exit 1
fi

echo
echo "## Compose: puertos publicados solo en loopback"
if grep -E '^[[:space:]]+- "[0-9]+:[0-9]+"' "${REPO_ROOT}/docker-compose.yml"; then
  echo "- ❌ hay puertos publicados en 0.0.0.0"
  exit 1
fi
echo "- ✅ todos los puertos usan 127.0.0.1"

echo
echo "## Dockerfiles: usuario no-root"
grep -Eq '^USER appuser' "${REPO_ROOT}/services/Dockerfile" \
  && echo "- ✅ services: USER appuser" \
  || { echo "- ❌ services sin USER no-root"; exit 1; }
grep -Eq '^USER node' "${REPO_ROOT}/uis/Dockerfile" \
  && echo "- ✅ uis: USER node" \
  || { echo "- ❌ uis sin USER no-root"; exit 1; }

echo
echo "✅ Hardening validado."
