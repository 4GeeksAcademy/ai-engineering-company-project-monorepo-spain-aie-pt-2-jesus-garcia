#!/usr/bin/env bash
# Verifica el baseline de endurecimiento y emite Markdown reproducible.
#
# Uso:
#   sudo bash scripts/security/hardening/50-verify-baseline.sh > docs/.../after.md
#
# Devuelve exit 1 si algún check crítico falla.
set -uo pipefail

OPS_USER="${OPS_USER:-trackflow-ops}"
ROOT="${TRACKFLOW_ROOT:-/srv/trackflow}"
FAILED=0

check() {
  local label="$1"; shift
  local output
  if output="$("$@" 2>&1)"; then
    echo "- ✅ **${label}**: \`${output}\`"
  else
    echo "- ❌ **${label}**: \`${output}\`"
    FAILED=1
  fi
}

echo "# Verificación de endurecimiento — $(hostname) — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

echo "## SSH"
SSHD_OUTPUT="$(sshd -T 2>/dev/null || true)"
echo "- \`PermitRootLogin\`: \`$(grep -i '^permitrootlogin' <<<"${SSHD_OUTPUT}" || echo 'no disponible')\`"
echo "- \`PasswordAuthentication\`: \`$(grep -i '^passwordauthentication' <<<"${SSHD_OUTPUT}" || echo 'no disponible')\`"
echo "- \`AllowUsers\`: \`$(grep -i '^allowusers' <<<"${SSHD_OUTPUT}" || echo 'no disponible')\`"
if grep -qi '^permitrootlogin no' <<<"${SSHD_OUTPUT}"; then
  echo "- ✅ root SSH deshabilitado"
else
  echo "- ❌ root SSH no está deshabilitado"
  FAILED=1
fi
if grep -qi '^passwordauthentication no' <<<"${SSHD_OUTPUT}"; then
  echo "- ✅ autenticación por contraseña deshabilitada"
else
  echo "- ❌ autenticación por contraseña sigue activa"
  FAILED=1
fi

echo
echo "## Usuario de operaciones"
if id "${OPS_USER}" >/dev/null 2>&1; then
  echo "- ✅ \`${OPS_USER}\` existe: \`$(id "${OPS_USER}")\`"
else
  echo "- ❌ \`${OPS_USER}\` no existe"
  FAILED=1
fi
if [[ "$(id -u "${OPS_USER}" 2>/dev/null || echo 0)" != "0" ]]; then
  echo "- ✅ \`${OPS_USER}\` no es root"
else
  echo "- ❌ \`${OPS_USER}\` es root o no existe"
  FAILED=1
fi

echo
echo "## Permisos"
for path in "${ROOT}/app" "${ROOT}/logs" "${ROOT}/data" "${ROOT}/secrets"; do
  if [[ -e "${path}" ]]; then
    echo "- \`$(stat -c '%a %U:%G %n' "${path}")\`"
    if [[ "${path}" == "${ROOT}/secrets" && "$(stat -c '%a' "${path}")" != "700" ]]; then
      echo "  - ❌ secrets debería ser 700"
      FAILED=1
    fi
  else
    echo "- ❌ falta \`${path}\`"
    FAILED=1
  fi
done
if find "${ROOT}" -perm -o=r 2>/dev/null | grep -q .; then
  echo "- ❌ hay archivos legibles por otros en ${ROOT}"
  find "${ROOT}" -perm -o=r 2>/dev/null | head -10
  FAILED=1
else
  echo "- ✅ sin archivos world-readable en ${ROOT}"
fi

echo
echo "## Firewall"
if command -v ufw >/dev/null 2>&1; then
  ufw status verbose | sed 's/^/    /'
else
  echo "- ❌ ufw no disponible"
  FAILED=1
fi

echo
echo "## Puertos en escucha"
ss -lntp | sed 's/^/    /'

echo
echo "## Docker"
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Ports}}' | sed 's/^/    /'
else
  echo "- docker no disponible"
fi

echo
echo "## Resultado"
if [[ "${FAILED}" -eq 0 ]]; then
  echo "✅ Todos los checks críticos pasan."
else
  echo "❌ Hay checks críticos fallando."
fi
exit "${FAILED}"
