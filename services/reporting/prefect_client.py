"""Cliente HTTP mínimo contra la API de Prefect.

La API no importa Prefect: solo habla con su API REST. Si Prefect no está
disponible, el endpoint de disparo devuelve 503 y la programación semanal sigue
intacta.
"""

from __future__ import annotations

import os

import httpx

DEPLOYMENT_NAME = "weekly-prod"


class PrefectUnavailable(RuntimeError):
    """No se pudo contactar con Prefect o el deployment no existe."""


def _api_url() -> str:
    return os.getenv("PREFECT_API_URL", "http://localhost:4200/api").rstrip("/")


def _headers() -> dict[str, str]:
    key = os.getenv("PREFECT_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def trigger_weekly_flow(
    week_start=None,
    lookback_weeks: int | None = None,
) -> dict:
    """Crea un flow run del deployment semanal y devuelve sus identificadores."""

    parameters: dict = {}
    if week_start is not None:
        parameters["week_start"] = week_start.isoformat()
    if lookback_weeks is not None:
        parameters["lookback_weeks"] = lookback_weeks

    url = _api_url()
    try:
        with httpx.Client(timeout=5.0, headers=_headers()) as client:
            deployments = client.get(
                f"{url}/deployments", params={"name": DEPLOYMENT_NAME}
            )
            deployments.raise_for_status()
            payload = deployments.json()
            items = payload if isinstance(payload, list) else payload.get("items", [])
            if not items:
                raise PrefectUnavailable(
                    f"Deployment '{DEPLOYMENT_NAME}' no encontrado."
                )
            deployment_id = items[0]["id"]
            created = client.post(
                f"{url}/deployments/{deployment_id}/create_flow_run",
                json={"parameters": parameters},
            )
            created.raise_for_status()
            flow_run = created.json()
    except PrefectUnavailable:
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise PrefectUnavailable(str(exc)) from exc

    flow_run_id = flow_run.get("id")
    return {
        "run_id": flow_run_id,
        "flow_run_id": flow_run_id,
        "status": "scheduled",
    }
