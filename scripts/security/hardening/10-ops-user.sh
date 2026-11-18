#!/usr/bin/env bash
# Crea el usuario de operaciones no-root de TrackFlow.
#
# Requisitos: ejecutar como root en un host Linux.
# Variables:
#   OPS_USER       (default: trackflow-ops)
#   OPS_SSH_KEY    ruta a la clave pública autorizada (default: ~/.ssh/id_ed25519.pub)
#   OPS_PUBLIC_KEY contenido literal de la clave (alternativa a OPS_SSH_KEY)
#
# Idempotente: si el usuario ya existe, solo asegura grupo, shell y clave.
set -euo pipefail

OPS_USER="${OPS_USER:-trackflow-ops}"
OPS_GROUP="${OPS_GROUP:-trackflow}"
OPS_HOME="${OPS_HOME:-/home/${OPS_USER}}"
OPS_SSH_KEY="${OPS_SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este script como root." >&2
  exit 1
fi

if ! getent group "${OPS_GROUP}" >/dev/null; then
  groupadd --system "${OPS_GROUP}"
fi

if ! id "${OPS_USER}" >/dev/null 2>&1; then
  useradd \
    --create-home \
    --home-dir "${OPS_HOME}" \
    --shell /bin/bash \
    --gid "${OPS_GROUP}" \
    "${OPS_USER}"
  # Sin contraseña: solo clave pública.
  passwd -l "${OPS_USER}" >/dev/null
fi

install -d -m 700 -o "${OPS_USER}" -g "${OPS_GROUP}" "${OPS_HOME}/.ssh"

PUBLIC_KEY="${OPS_PUBLIC_KEY:-}"
if [[ -z "${PUBLIC_KEY}" && -f "${OPS_SSH_KEY}" ]]; then
  PUBLIC_KEY="$(cat "${OPS_SSH_KEY}")"
fi
if [[ -z "${PUBLIC_KEY}" ]]; then
  echo "No se encontró clave pública (${OPS_SSH_KEY})." >&2
  echo "Exporta OPS_SSH_KEY o OPS_PUBLIC_KEY." >&2
  exit 1
fi

AUTHORIZED="${OPS_HOME}/.ssh/authorized_keys"
touch "${AUTHORIZED}"
chmod 600 "${AUTHORIZED}"
chown "${OPS_USER}:${OPS_GROUP}" "${AUTHORIZED}"
if ! grep -qxF "${PUBLIC_KEY}" "${AUTHORIZED}"; then
  printf '%s\n' "${PUBLIC_KEY}" >> "${AUTHORIZED}"
fi

# Sudo mínimo: gestionar el stack y reiniciar unidades de TrackFlow.
cat > /etc/sudoers.d/90-trackflow-ops <<'SUDOERS'
# TrackFlow ops: sin shell root interactiva, solo operaciones del stack.
trackflow-ops ALL=(root) /usr/bin/systemctl restart trackflow-*, \
  /usr/bin/systemctl status trackflow-*, \
  /usr/bin/journalctl -u trackflow-*, \
  /usr/bin/docker compose *
SUDOERS
chmod 440 /etc/sudoers.d/90-trackflow-ops

echo "Usuario ${OPS_USER} listo (grupo ${OPS_GROUP})."
