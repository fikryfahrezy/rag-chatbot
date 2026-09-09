import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.providers import Completion, ModelGateway


def test_demo_access_boundaries_end_to_end(monkeypatch):
    discoverable_model_tag = f"test-model-{uuid4()}"

    async def fake_completion(self, provider, model, system, prompt):
        text = '{"tool":"order"}' if "Return only JSON" in system else prompt
        return Completion(text=text, provider=provider, model=model)

    async def fake_model_list(self, provider):
        return ["qwen3.5:4b-q4_K_M", discoverable_model_tag]

    async def fake_stream(self, provider, model, system, prompt):
        yield "Streamed"
        yield " answer"

    monkeypatch.setattr(ModelGateway, "complete", fake_completion)
    monkeypatch.setattr(ModelGateway, "list_models", fake_model_list)
    monkeypatch.setattr(ModelGateway, "stream", fake_stream)
    with TestClient(app) as client:
        preflight = client.options(
            "/api/users",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-demo-user",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"

        hidden = client.post(
            "/api/chat",
            headers={"X-Demo-User": "sales-jkt-1"},
            json={"workspace": "operations", "message": "Status ORD-1002?"},
        )
        assert hidden.status_code == 200
        assert "tidak ditemukan" in hidden.json()["answer"]

        sales_source = client.get("/api/database-source", headers={"X-Demo-User": "sales-jkt-1"})
        assert sales_source.status_code == 200
        sales_tables = {table["name"]: table for table in sales_source.json()["tables"]}
        assert all(row["sales_id"] == "sales-jkt-1" for row in sales_tables["orders"]["rows"])
        assert all(row["sales_id"] == "sales-jkt-1" for row in sales_tables["commissions"]["rows"])
        assert all(row["warehouse_region"] == "jakarta" for row in sales_tables["inventory"]["rows"])

        public_source = client.get("/api/database-source", headers={"X-Demo-User": "public"})
        assert public_source.status_code == 200
        public_table = public_source.json()["tables"][0]
        assert public_table["columns"] == ["product", "availability"]
        assert all("stock" not in row for row in public_table["rows"])

        document_user_source = client.get(
            "/api/database-source", headers={"X-Demo-User": "employee-jkt"},
        )
        assert document_user_source.status_code == 403

        streamed = client.post(
            "/api/chat/stream",
            headers={"X-Demo-User": "sales-jkt-1"},
            json={"workspace": "operations", "message": "Status ORD-1001?"},
        )
        assert streamed.status_code == 200
        events = [json.loads(line) for line in streamed.text.splitlines()]
        assert "".join(event.get("delta", "") for event in events) == "Streamed answer"
        assert events[-1]["type"] == "done"
        assert events[-1]["route"] == "order"

        public = client.post(
            "/api/chat",
            headers={"X-Demo-User": "public"},
            json={"workspace": "public", "message": "Stok produk apa yang tersedia?"},
        )
        assert public.status_code == 200
        assert public.json()["route"] == "public_catalog"
        assert "18" not in public.json()["answer"]

        public_no_pdf_fallback = client.post(
            "/api/chat",
            headers={"X-Demo-User": "public"},
            json={"workspace": "public", "message": "Apa kebijakan perusahaan?"},
        )
        assert public_no_pdf_fallback.status_code == 200
        assert public_no_pdf_fallback.json()["route"] == "public_catalog"
        assert public_no_pdf_fallback.json()["citations"] == []

        forbidden = client.post(
            "/api/chat",
            headers={"X-Demo-User": "public"},
            json={"workspace": "operations", "message": "Berapa komisi?"},
        )
        assert forbidden.status_code == 403

        wrong_group_source = client.post(
            "/api/chat",
            headers={"X-Demo-User": "sales-jkt-1"},
            json={"workspace": "knowledge", "message": "Show internal documents"},
        )
        assert wrong_group_source.status_code == 403

        public_pdf_upload = client.post(
            "/api/documents",
            headers={"X-Demo-User": "admin"},
            data={"visibility": "public"},
            files={"file": ("public.pdf", b"not parsed", "application/pdf")},
        )
        assert public_pdf_upload.status_code == 422

        unknown_region_upload = client.post(
            "/api/documents",
            headers={"X-Demo-User": "admin"},
            data={"visibility": "region", "region": "j akarta"},
            files={"file": ("regional.pdf", b"not parsed", "application/pdf")},
        )
        assert unknown_region_upload.status_code == 422
        assert unknown_region_upload.json()["detail"] == "Invalid region"

        for workspace in ("operations", "public", "knowledge"):
            admin_access = client.post(
                "/api/chat",
                headers={"X-Demo-User": "admin"},
                json={"workspace": workspace, "message": "Apa informasi yang tersedia?"},
            )
            assert admin_access.status_code == 200

        catalog = client.get("/api/registered-models", headers={"X-Demo-User": "admin"})
        assert catalog.status_code == 200
        assert len(catalog.json()) >= 1

        discovered = client.get("/api/provider-models/ollama", headers={"X-Demo-User": "admin"})
        assert discovered.status_code == 200
        assert discoverable_model_tag in discovered.json()["models"]

        forbidden_catalog = client.get("/api/registered-models", headers={"X-Demo-User": "sales-jkt-1"})
        assert forbidden_catalog.status_code == 403

        unknown = f"not-registered-{uuid4()}"
        unknown_assignment = client.put(
            "/api/models",
            headers={"X-Demo-User": "admin"},
            json={task: {"provider": "ollama", "model": unknown} for task in (
                "database_planner", "database_answer", "pdf_answer",
            )},
        )
        assert unknown_assignment.status_code == 422

        model_name = f"Test model {uuid4()}"
        registered = client.post(
            "/api/registered-models",
            headers={"X-Demo-User": "admin"},
            json={"name": model_name, "provider": "ollama", "model": discoverable_model_tag},
        )
        assert registered.status_code == 201
        removed = client.delete(
            f"/api/registered-models/{registered.json()['id']}",
            headers={"X-Demo-User": "admin"},
        )
        assert removed.status_code == 200
