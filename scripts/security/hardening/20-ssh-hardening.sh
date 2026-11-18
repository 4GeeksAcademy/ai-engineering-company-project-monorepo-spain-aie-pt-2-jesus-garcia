#!/usr/bin/env bash
# Instala y valida la configuración SSH endurecida.
# No cierra la sesión actual: primero valida con `sshd -t`.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este script como root." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="/etc/ssh/sshd_config.d/99-trackflow-hardening.conf"

install -d -m 755 /etc/ssh/sshd_config.d
install -m 644 "${SCRIPT_DIR}/sshd_trackflow.conf" "${TARGET}"

# Asegura que sshd_config incluye el directorio drop-in.
if ! grep -Eq '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config; then
  printf '\nInclude /etc/ssh/sshd_config.d/*.conf\n' >> /etc/ssh/sshd_config
fi

sshd -t

if systemctl list-unit-files | grep -q '^ssh\.service'; then
  systemctl reload ssh
else
  systemctl reload sshd
fi

echo "SSH endurecido. Comprueba en OTRA sesión antes de cerrar esta:"
echo "  ssh -o PreferredAuthentications=password root@\$(hostname -I | awk '{print \$1}')"
echo "  sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|allowusers'"
