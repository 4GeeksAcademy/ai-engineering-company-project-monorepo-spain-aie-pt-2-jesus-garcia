#!/usr/bin/env bash
# Firewall base de TrackFlow.
#
# - Deniega todo lo entrante salvo SSH (ops) y HTTP/HTTPS.
# - Docker publica puertos saltándose UFW: además de bindear a 127.0.0.1 en
#   compose, se bloquean explícitamente los puertos internos en DOCKER-USER.
#
# Variables:
#   SSH_PORT          (default: 22)
#   SSH_ALLOW_FROM    CIDR de administración (recomendado). Si está vacío,
#                     se usa `ufw limit` sobre el puerto SSH.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este script como root." >&2
  exit 1
fi

SSH_PORT="${SSH_PORT:-22}"
SSH_ALLOW_FROM="${SSH_ALLOW_FROM:-}"

ufw --force default deny incoming
ufw --force default allow outgoing

if [[ -n "${SSH_ALLOW_FROM}" ]]; then
  ufw allow from "${SSH_ALLOW_FROM}" to any port "${SSH_PORT}" proto tcp
else
  ufw limit "${SSH_PORT}/tcp"
fi

ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

# Puertos que nunca deben ser accesibles desde fuera, aunque un compose los
# publique por error. Se añaden a DOCKER-USER si Docker está presente.
if command -v iptables >/dev/null 2>&1 && iptables -L DOCKER-USER >/dev/null 2>&1; then
  for port in 6379 6333 6334 5555 8000 8001 3000 3001 4200; do
    if ! iptables -C DOCKER-USER -p tcp --dport "${port}" -j DROP 2>/dev/null; then
      iptables -I DOCKER-USER 1 -p tcp --dport "${port}" -j DROP
    fi
    if ! iptables -C DOCKER-USER -p udp --dport "${port}" -j DROP 2>/dev/null; then
      iptables -I DOCKER-USER 1 -p udp --dport "${port}" -j DROP
    fi
  done
  echo "Reglas DOCKER-USER aplicadas para puertos internos."
else
  echo "Docker/iptables no disponible: se omite DOCKER-USER (revisar en el host)."
fi
