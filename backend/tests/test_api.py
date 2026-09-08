from fastapi.testclient import TestClient

from app.main import app


def test_demo_access_boundaries_end_to_end():
    with TestClient(app) as client:
        hidden = client.post(
            "/api/chat",
            headers={"X-Demo-User": "sales-jkt-1"},
            json={"workspace": "operations", "message": "Status ORD-1002?"},
        )
        assert hidden.status_code == 200
        assert "tidak ditemukan" in hidden.json()["answer"]

        public = client.post(
            "/api/chat",
            headers={"X-Demo-User": "public"},
            json={"workspace": "public", "message": "Stok produk apa yang tersedia?"},
        )
        assert public.status_code == 200
        assert public.json()["route"] == "public_catalog"
        assert "18" not in public.json()["answer"]

        forbidden = client.post(
            "/api/chat",
            headers={"X-Demo-User": "public"},
            json={"workspace": "operations", "message": "Berapa komisi?"},
        )
        assert forbidden.status_code == 403
