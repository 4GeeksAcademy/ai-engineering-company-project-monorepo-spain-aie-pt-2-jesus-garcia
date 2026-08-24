import pytest

from database import get_db


@pytest.fixture(autouse=True)
def _clean_incidents():
    db = get_db()
    table = db.table("incidents")
    table.truncate()
    db.close()
    yield
    db = get_db()
    db.table("incidents").truncate()
    db.close()


def _create(client, auth_headers, **overrides):
    payload = {
        "title": "Paquete extraviado",
        "description": "El paquete no aparece en tránsito.",
        "origin": "customer",
        "branch": "la_warehouse",
        "category": "lost_parcel",
    }
    payload.update(overrides)
    return client.post("/api/incidents", headers=auth_headers, json=payload)


class TestCreate:
    def test_create_default_status_open(self, client, auth_headers):
        res = _create(client, auth_headers)
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "open"
        assert body["title"] == "Paquete extraviado"
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_create_with_explicit_status(self, client, auth_headers):
        res = _create(client, auth_headers, status="in_progress")
        assert res.status_code == 201
        assert res.json()["status"] == "in_progress"

    def test_create_missing_field_returns_400(self, client, auth_headers):
        res = _create(client, auth_headers, title="")
        assert res.status_code == 400
        assert "title" in res.json()["detail"]

    def test_create_missing_description_returns_400(self, client, auth_headers):
        res = _create(client, auth_headers, description="")
        assert res.status_code == 400
        assert "description" in res.json()["detail"]

    def test_create_invalid_category_returns_400(self, client, auth_headers):
        res = _create(client, auth_headers, category="bad_category")
        assert res.status_code == 400
        assert "category" in res.json()["detail"]

    def test_create_invalid_origin_returns_400(self, client, auth_headers):
        res = _create(client, auth_headers, origin="alien")
        assert res.status_code == 400
        assert "origin" in res.json()["detail"]

    def test_create_invalid_branch_returns_400(self, client, auth_headers):
        res = _create(client, auth_headers, branch="moon_base")
        assert res.status_code == 400
        assert "branch" in res.json()["detail"]

    def test_create_invalid_status_returns_400(self, client, auth_headers):
        res = _create(client, auth_headers, status="closed")
        assert res.status_code == 400
        assert "status" in res.json()["detail"]


class TestList:
    def test_list_empty_db_returns_200(self, client, auth_headers):
        res = client.get("/api/incidents", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_and_filters(self, client, auth_headers):
        _create(client, auth_headers, category="lost_parcel", branch="la_warehouse")
        _create(client, auth_headers, category="carrier_issue", branch="la_warehouse")
        _create(client, auth_headers, category="lost_parcel", branch="zaragoza_warehouse")

        all_res = client.get("/api/incidents", headers=auth_headers).json()
        assert len(all_res) == 3

        by_cat = client.get("/api/incidents", headers=auth_headers, params={"category": "lost_parcel"}).json()
        assert len(by_cat) == 2

        by_branch = client.get("/api/incidents", headers=auth_headers, params={"branch": "la_warehouse"}).json()
        assert len(by_branch) == 2

        combined = client.get(
            "/api/incidents",
            headers=auth_headers,
            params={"category": "lost_parcel", "branch": "la_warehouse"},
        ).json()
        assert len(combined) == 1


class TestGet:
    def test_get_by_id(self, client, auth_headers):
        created = _create(client, auth_headers).json()
        res = client.get(f"/api/incidents/{created['id']}", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]

    def test_get_missing_returns_404(self, client, auth_headers):
        res = client.get("/api/incidents/99999", headers=auth_headers)
        assert res.status_code == 404


class TestTransitions:
    def test_open_to_in_progress(self, client, auth_headers):
        iid = _create(client, auth_headers).json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "in_progress"})
        assert res.status_code == 200
        assert res.json()["status"] == "in_progress"

    def test_in_progress_to_resolved(self, client, auth_headers):
        iid = _create(client, auth_headers, status="in_progress").json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "resolved"})
        assert res.status_code == 200
        assert res.json()["status"] == "resolved"

    def test_invalid_transition_returns_400(self, client, auth_headers):
        iid = _create(client, auth_headers).json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "resolved"})
        assert res.status_code == 400
        assert "Transición inválida" in res.json()["detail"]

    def test_in_progress_to_open(self, client, auth_headers):
        iid = _create(client, auth_headers, status="in_progress").json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "open"})
        assert res.status_code == 200
        assert res.json()["status"] == "open"

    def test_resolved_to_in_progress(self, client, auth_headers):
        iid = _create(client, auth_headers, status="resolved").json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "in_progress"})
        assert res.status_code == 200
        assert res.json()["status"] == "in_progress"

    def test_in_progress_to_discarded(self, client, auth_headers):
        iid = _create(client, auth_headers, status="in_progress").json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "discarded"})
        assert res.status_code == 200
        assert res.json()["status"] == "discarded"

    def test_final_status_cannot_change(self, client, auth_headers):
        iid = _create(client, auth_headers, status="discarded").json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "open"})
        assert res.status_code == 400
        assert "estado final" in res.json()["detail"]

    def test_discarded_cannot_change(self, client, auth_headers):
        iid = _create(client, auth_headers, status="discarded").json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "open"})
        assert res.status_code == 400

    def test_transition_missing_incident_returns_404(self, client, auth_headers):
        res = client.patch("/api/incidents/99999/status", headers=auth_headers, json={"status": "in_progress"})
        assert res.status_code == 404

    def test_transition_invalid_status_returns_400(self, client, auth_headers):
        iid = _create(client, auth_headers).json()["id"]
        res = client.patch(f"/api/incidents/{iid}/status", headers=auth_headers, json={"status": "closed"})
        assert res.status_code == 400
        assert "status" in res.json()["detail"]


class TestSummary:
    def test_summary_empty_db_zeroes(self, client, auth_headers):
        res = client.get("/api/incidents/summary", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert sum(body["by_status"].values()) == 0
        assert sum(body["by_category"].values()) == 0
        assert sum(body["by_origin"].values()) == 0
        assert sum(body["by_branch"].values()) == 0

    def test_summary_counts(self, client, auth_headers):
        _create(client, auth_headers, category="lost_parcel", status="open")
        _create(client, auth_headers, category="lost_parcel", status="resolved")
        _create(client, auth_headers, category="carrier_issue", status="in_progress")
        body = client.get("/api/incidents/summary", headers=auth_headers).json()

        assert body["by_status"]["open"] == 1
        assert body["by_status"]["resolved"] == 1
        assert body["by_status"]["in_progress"] == 1
        assert body["by_category"]["lost_parcel"] == 2
        assert body["by_category"]["carrier_issue"] == 1
        assert body["by_origin"]["customer"] == 3
        assert body["by_branch"]["la_warehouse"] == 3
