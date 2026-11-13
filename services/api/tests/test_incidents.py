import uuid

from .conftest import upload


class TestAnalyzeEndpoint:
    def test_valid_csv_is_enqueued_and_returns_202(
        self, client, sample_csv_bytes, auth_headers, enqueued_tasks
    ):
        response = upload(client, sample_csv_bytes, auth_headers)

        assert response.status_code == 202
        task_id = response.json()["task_id"]
        assert uuid.UUID(task_id)

        assert len(enqueued_tasks) == 1
        call = enqueued_tasks[0]
        assert call["task_id"] == task_id
        assert call["kwargs"]["filename"] == "COMPANY.csv"
        assert call["kwargs"]["path"].endswith(f"{task_id}.csv")

    def test_missing_file_field_returns_422(self, client, auth_headers):
        response = client.post("/api/incidents/analyze", headers=auth_headers)
        assert response.status_code == 422

    def test_empty_file_returns_400(
        self, client, empty_csv_bytes, auth_headers, enqueued_tasks
    ):
        response = upload(client, empty_csv_bytes, auth_headers)
        assert response.status_code == 400
        assert response.json()["detail"] == "El archivo está vacío."
        assert enqueued_tasks == []

    def test_invalid_columns_returns_400(
        self, client, invalid_header_csv_bytes, auth_headers, enqueued_tasks
    ):
        response = upload(client, invalid_header_csv_bytes, auth_headers)
        assert response.status_code == 400
        assert "formato incorrecto" in response.json()["detail"].lower()
        assert "customer_id" in response.json()["detail"]
        assert enqueued_tasks == []

    def test_analyze_without_auth_returns_401(self, client, sample_csv_bytes):
        response = upload(client, sample_csv_bytes, {})
        assert response.status_code == 401

    def test_enqueue_failure_returns_503_and_removes_file(
        self, client, sample_csv_bytes, auth_headers, monkeypatch, _isolate_uploads
    ):
        from app.routes import incidents as incidents_route

        def boom(*args, **kwargs):
            raise RuntimeError("redis down")

        monkeypatch.setattr(
            incidents_route.analyze_incidents_csv, "apply_async", boom
        )

        response = upload(client, sample_csv_bytes, auth_headers)

        assert response.status_code == 503
        assert list(_isolate_uploads.glob("*.csv")) == []


class TestExportEndpoint:
    def test_export_without_previous_analysis_returns_404(
        self, client, auth_headers
    ):
        response = client.get(
            "/api/incidents/results/export", headers=auth_headers
        )
        assert response.status_code == 404
        assert "no hay análisis" in response.json()["detail"].lower()

    def test_export_after_sync_analysis_returns_csv(
        self, client, sample_csv_bytes, auth_headers
    ):
        from app.incidents import service

        service.analyze_upload(sample_csv_bytes)

        response = client.get(
            "/api/incidents/results/export", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]

        body = response.text
        assert "metrica,valor" in body
        assert "total_registros,5" in body
        assert "registros_validos,5" in body
        assert "satisfaccion_media_cerrados,8.5" in body
        assert "categoria_incidencia,2" in body
        assert "categoria_seguimiento,1" in body

    def test_export_with_task_id_reads_celery_result(
        self, client, auth_headers, monkeypatch
    ):
        from app.routes import incidents as incidents_route

        class FakeResult:
            state = "SUCCESS"
            result = {
                "total": 5,
                "valid": 5,
                "invalid": 0,
                "by_status": {"abierto": 2, "cerrado": 2, "descartado": 1},
                "by_category": {"incidencia": 2},
                "avg_satisfaction_cerrados": 8.5,
                "invalid_reasons": {},
            }

        monkeypatch.setattr(
            incidents_route,
            "AsyncResult",
            lambda task_id, app: FakeResult(),
        )

        response = client.get(
            "/api/incidents/results/export?task_id=abc",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "total_registros,5" in response.text

    def test_export_with_unfinished_task_returns_409(
        self, client, auth_headers, monkeypatch
    ):
        from app.routes import incidents as incidents_route

        class FakeResult:
            state = "STARTED"
            result = None

        monkeypatch.setattr(
            incidents_route,
            "AsyncResult",
            lambda task_id, app: FakeResult(),
        )

        response = client.get(
            "/api/incidents/results/export?task_id=abc",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_state_is_reset_between_tests(self, client, auth_headers):
        response = client.get(
            "/api/incidents/results/export", headers=auth_headers
        )
        assert response.status_code == 404

    def test_export_without_auth_returns_401(self, client):
        response = client.get("/api/incidents/results/export")
        assert response.status_code == 401
