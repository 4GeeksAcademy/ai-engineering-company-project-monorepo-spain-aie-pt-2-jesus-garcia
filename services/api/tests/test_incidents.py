from .conftest import upload


class TestAnalyzeEndpoint:
    def test_valid_csv_returns_summary(self, client, sample_csv_bytes):
        response = upload(client, sample_csv_bytes)
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert data["valid"] == 5
        assert data["invalid"] == 0
        assert data["by_status"] == {"abierto": 2, "cerrado": 2, "descartado": 1}
        assert data["by_category"] == {
            "seguimiento": 1,
            "devolución": 1,
            "consulta_general": 1,
            "incidencia": 2,
        }
        assert data["avg_satisfaction_cerrados"] == 8.5
        assert data["invalid_reasons"] == {}

    def test_missing_file_field_returns_422(self, client):
        response = client.post("/api/incidents/analyze")
        assert response.status_code == 422

    def test_empty_file_returns_400(self, client, empty_csv_bytes):
        response = upload(client, empty_csv_bytes)
        assert response.status_code == 400
        assert response.json()["detail"] == "El archivo está vacío."

    def test_invalid_columns_returns_400(self, client, invalid_header_csv_bytes):
        response = upload(client, invalid_header_csv_bytes)
        assert response.status_code == 400
        assert "formato incorrecto" in response.json()["detail"].lower()
        assert "customer_id" in response.json()["detail"]

    def test_invalid_records_are_counted(self, client):
        bad = (
            "customer_id,first_name,last_name,email,phone,department,status,category,satisfaction_score,created_at\n"
            "CUST-1,Ana,Martínez,no-email,+34 600 000000,Experiencia del cliente,abierto,seguimiento,,2025-01-01\n"
            "CUST-2,Pedro,Pérez,pedro@correo.es,+34 600 000001,Experiencia del cliente,cerrado,devolución,5,2025-01-02\n"
        ).encode("utf-8")
        response = upload(client, bad)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["valid"] == 1
        assert data["invalid"] == 1
        assert data["by_category"]["devolución"] == 1
        assert data["invalid_reasons"] == {"invalid_email": 1}


class TestExportEndpoint:
    def test_export_without_previous_analysis_returns_404(self, client):
        response = client.get("/api/incidents/results/export")
        assert response.status_code == 404
        assert "no hay análisis" in response.json()["detail"].lower()

    def test_export_after_analysis_returns_csv(self, client, sample_csv_bytes):
        analyze = upload(client, sample_csv_bytes)
        assert analyze.status_code == 200

        response = client.get("/api/incidents/results/export")
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

    def test_state_is_reset_between_tests(self, client):
        response = client.get("/api/incidents/results/export")
        assert response.status_code == 404
