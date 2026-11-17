# Endurecimiento del servidor — TrackFlow

**Alcance:** host Linux que ejecuta el stack Docker Compose de TrackFlow (API
`services`, workers Celery, Redis, Qdrant, MCP, frontends y reverse proxy).

**Estado:** scripts y configuración versionados y validados en local/contenedor.
La aplicación en un host real (SSH, UFW, permisos) queda como runbook
reproducible porque este repositorio no incluye un host de producción.

---

## 1. Modelo de acceso

| Elemento | Decisión |
|---|---|
| Usuario de operaciones | `trackflow-ops` (no root) |
| Acceso SSH | Solo clave pública, sin contraseña |
| Root SSH | Deshabilitado (`PermitRootLogin no`) |
| Usuarios permitidos | `AllowUsers trackflow-ops` |
| Sudo | Solo `systemctl` de unidades `trackflow-*`, `journalctl` y `docker compose` |
| Puertos externos | `22/tcp` (ops), `80/tcp`, `443/tcp` |
| Puertos internos | Redis, Qdrant, Flower, MCP, Prefect y apps bindeados a `127.0.0.1` o solo red Docker |

---

## 2. Artefactos

```
scripts/security/
  hardening/
    10-ops-user.sh            # usuario, grupo, clave SSH, sudoers mínimo
    20-ssh-hardening.sh       # drop-in sshd + validación + reload
    sshd_trackflow.conf       # configuración SSH endurecida
    30-firewall.sh            # UFW + reglas DOCKER-USER
    40-folder-permissions.sh  # /srv/trackflow/{app,logs,data,secrets}
    50-verify-baseline.sh     # verificación reproducible (Markdown + exit code)
    test-hardening.sh         # valida configs sin host real (contenedor Debian)
  check-secret-permissions.sh # .env en 600
  port-scan.sh                # escaneo sin dependencias
docker-compose.hardened.yml   # overlay de producción (no-root, read-only, tmpfs)
```

---

## 3. Runbook de aplicación (host Linux)

> **Orden importante:** crear el usuario y probar la clave en **otra sesión**
> antes de deshabilitar root/contraseña.

```bash
# 0. Como root, desde el repo
cd /srv/trackflow/app
export OPS_SSH_KEY=/root/.ssh/id_ed25519.pub

# 1. Usuario de operaciones
sudo bash scripts/security/hardening/10-ops-user.sh

# 2. Probar login en otra terminal
ssh trackflow-ops@<host> 'id && sudo -l'

# 3. SSH endurecido (valida con sshd -t antes de recargar)
sudo bash scripts/security/hardening/20-ssh-hardening.sh

# 4. Permisos de carpetas y secretos
sudo bash scripts/security/hardening/40-folder-permissions.sh

# 5. Firewall
export SSH_ALLOW_FROM="203.0.113.0/24"   # CIDR de administración (recomendado)
sudo bash scripts/security/hardening/30-firewall.sh

# 6. Verificación y evidencia
sudo bash scripts/security/hardening/50-verify-baseline.sh \
  | tee docs/cybersecurity/evidence/10-fixes/server-baseline.md
```

### Docker: por qué hay dos capas

Docker publica puertos saltándose UFW. Por eso:

1. `docker-compose.yml` bindea todos los puertos a `127.0.0.1` y Redis no se
   publica al host.
2. `30-firewall.sh` añade reglas `DOCKER-USER` que bloquean explícitamente
   `6379`, `6333`, `6334`, `5555`, `8000`, `8001`, `3000`, `3001` y `4200`
   desde interfaces externas.
3. En producción, solo el reverse proxy expone `80/443`.

### Producción: overlay endurecido

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.hardened.yml up -d
```

El overlay:

- ejecuta `services`, `worker`, `flower` y `mcp` como UID `10001` (no root);
- ejecuta `uis` como `node` (UID 1000);
- quita `--reload` de la API;
- monta `/tmp` como `tmpfs` y `read_only` en API/worker;
- mantiene `no-new-privileges` y `cap_drop: ALL`.

**Requisito en Linux:** los bind mounts de datos deben pertenecer al UID/GID
configurado:

```bash
sudo chown -R "${TRACKFLOW_UID:-10001}:${TRACKFLOW_GID:-10001}" data
```

Si los volúmenes `ui-next-*` o `task-uploads` se crearon antes del cambio,
recréalos una vez (`docker compose down` + `docker volume rm ...`).

---

## 4. Permisos de carpetas

| Ruta | Modo | Dueño | Uso |
|---|---|---|---|
| `/srv/trackflow/app` | `750` | `trackflow-ops:trackflow` | despliegue/código |
| `/srv/trackflow/logs` | `750` | `trackflow-ops:trackflow` | logs |
| `/srv/trackflow/data` | `750` | `trackflow-ops:trackflow` | uploads/artefactos |
| `/srv/trackflow/secrets` | `700` | `root:root` | `.env`, claves |
| `secrets/*.env` | `600` | `root:root` | secretos |

Los `.env` del repo también se fuerzan a `600`:

```bash
bash scripts/security/check-secret-permissions.sh
# - .env: 600 ✅
# - services/api/.env: 600 ✅
# - mcps/trackflow-mcp/.env: 600 ✅
```

---

## 5. Verificación (criterios de evaluación)

```bash
# SSH
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|allowusers'
# permitrootlogin no
# passwordauthentication no
# allowusers trackflow-ops

# Usuario
id trackflow-ops

# Permisos
stat -c '%a %U:%G %n' /srv/trackflow/{app,logs,data,secrets}
find /srv/trackflow -perm -o=r

# Firewall y puertos
sudo ufw status verbose
sudo ss -lntp
docker ps --format 'table {{.Names}}\t{{.Ports}}'
nmap -Pn -p- <host>        # esperado: 22, 80, 443

# Contenedores no-root
docker compose exec -T services id   # uid=10001(appuser)
docker compose exec -T uis id        # uid=1000(node)
```

Evidencia local ya capturada:

- `docs/cybersecurity/evidence/10-fixes/hardening-config.txt`
- `docs/cybersecurity/evidence/10-fixes/docker-ports-and-users.txt`
- `docs/cybersecurity/evidence/10-fixes/secret-permissions.txt`
- `docs/cybersecurity/evidence/10-fixes/security-headers.txt`

---

## 6. Limitaciones y pendientes

- **No hay host Linux de producción en el repo.** `50-verify-baseline.sh` debe
  ejecutarse en el host real para dejar la evidencia definitiva de SSH/UFW.
- **Tags de imágenes Docker** (`uv:latest`, `python:3.14-slim`, `node:22-alpine`)
  siguen siendo flotantes; el siguiente paso es fijarlos por digest.
- **Rotación de secretos reales** (Resend, LLM, Auth0, Supabase) es una tarea
  de operaciones; el repo solo garantiza que no haya valores por defecto y que
  los archivos locales estén en `600`.
- **DOCKER-USER** requiere `iptables`/`nftables` en el host; el script lo omite
  con aviso si Docker no está presente.
