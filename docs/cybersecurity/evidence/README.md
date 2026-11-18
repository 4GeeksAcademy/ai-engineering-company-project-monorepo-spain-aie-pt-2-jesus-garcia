# Evidencia de ciberseguridad

Índice de capturas **antes/después** para la auditoría OWASP y el endurecimiento
del servidor. Todo es reproducible con los comandos de abajo; no se guardan
secretos ni tokens.

## 00-baseline — antes de corregir

| Archivo | Qué demuestra |
|---|---|
| `git.txt` | commit y estado del repo al iniciar |
| `authz-matrix.md` | `telemetry/report` 200 anónimo; inventario/memoria 200 con rol `user`; auto-registro 201; `client_id` ajeno 201 |
| `secret-permissions.txt` | `.env` en `644` (legible por terceros) |
| `compose-ports.txt` | puertos publicados en `0.0.0.0` |
| `npm-audit-backoffice.json` / `website.json` | vulnerabilidades high/critical iniciales |
| `pip-audit.txt` | `python-jose` / `ecdsa` vulnerables |

## 10-fixes — después de corregir

| Archivo | Qué demuestra |
|---|---|
| `authz-matrix.md` | telemetry anónimo 401, `user` 403; inventario/memoria 403; `client_id` ajeno 403 |
| `docker-ports-and-users.txt` | todos los puertos en `127.0.0.1`; Redis sin publicar; UID 10001/1000 no root |
| `hardening-config.txt` | `sshd -t` válido; UFW solo 22/80/443; compose sin `0.0.0.0`; Dockerfiles con `USER` |
| `secret-permissions.txt` | `.env` en `600` |
| `security-headers.txt` | CSP, `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` en web/backoffice/API |
| `npm-audit-*.json` | 0 vulnerabilidades de producción |
| `pip-audit.txt` | `No known vulnerabilities found` |
| `port-scan.txt` | puertos internos en loopback |

## Regenerar

```bash
# 1. Matriz de autorización
cd services/api
source venv/bin/activate
python ../../scripts/security/authz_matrix.py \
  > ../../docs/cybersecurity/evidence/10-fixes/authz-matrix.md

# 2. Tests
pytest -q

# 3. Dependencias
pip-audit -r requirements.txt | tee ../../docs/cybersecurity/evidence/10-fixes/pip-audit.txt
npm audit --json --omit=dev --prefix ../../uis/backoffice \
  > ../../docs/cybersecurity/evidence/10-fixes/npm-audit-backoffice.json
npm audit --json --omit=dev --prefix ../../uis/website \
  > ../../docs/cybersecurity/evidence/10-fixes/npm-audit-website.json

# 4. Hardening (sin host real)
cd ../..
bash scripts/security/hardening/test-hardening.sh \
  | tee docs/cybersecurity/evidence/10-fixes/hardening-config.txt
bash scripts/security/check-secret-permissions.sh \
  | tee docs/cybersecurity/evidence/10-fixes/secret-permissions.txt

# 5. Docker
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
docker compose exec -T services id
docker compose exec -T uis id

# 6. Cabeceras
curl -sI http://127.0.0.1:3000/ | grep -iE 'content-security|x-content-type|x-frame|referrer|permissions'
curl -sI http://127.0.0.1:3001/login | grep -iE 'content-security|x-content-type|x-frame|referrer|permissions'
```

> En un host real, añadir la salida de
> `scripts/security/hardening/50-verify-baseline.sh` (SSH, UFW, permisos y
> puertos) como `server-baseline.md`.
