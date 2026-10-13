"""End-to-end API tests: FastAPI -> AgentService -> ADK Runner -> tools -> SQLite."""

from __future__ import annotations

import json

USER = "test-user"


def test_health_paths_avoid_cloud_run_reserved_z_suffix(client):
    # Cloud Run's front end swallows paths ending in "z" on run.app URLs, so the
    # externally used routes must not end in z; the z-aliases stay for local use.
    for path in ("/health", "/ready", "/healthz", "/readyz"):
        assert client.get(path).status_code == 200, path
    assert "/health" in client.get("/openapi.json").json()["paths"]
    assert "/healthz" not in client.get("/openapi.json").json()["paths"]


def test_health_and_ready(client):
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["checks"]["retail_db"] == "ok"
    assert r.json()["checks"]["session_db"] == "ok"


def test_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Northwind Market" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_list_agents(client):
    agents = {a["key"]: a for a in client.get("/api/v1/agents").json()}
    assert set(agents) == {"coordinator", "catalog", "orders", "returns", "support"}
    assert agents["coordinator"]["sub_agents"] == ["catalog_agent", "order_agent", "returns_agent", "support_agent"]
    assert "search_products" in agents["catalog"]["tools"]


def test_chat_routes_to_catalog_and_calls_tool(client):
    r = client.post("/api/v1/chat", json={"message": "show me headphones", "user_id": USER})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "retail_coordinator" in body["agents"] and "catalog_agent" in body["agents"]
    names = [t["name"] for t in body["tool_calls"]]
    assert names == ["transfer_to_agent", "search_products"]
    assert "search_products" in body["reply"] and "status=success" in body["reply"]


def test_chat_routes_to_returns(client):
    body = client.post("/api/v1/chat", json={"message": "I want a refund", "user_id": USER}).json()
    assert "returns_agent" in body["agents"]
    assert "check_return_eligibility" in [t["name"] for t in body["tool_calls"]]


def test_session_persists_and_lists(client):
    first = client.post("/api/v1/chat", json={"message": "where is my order", "user_id": USER, "customer_id": "CUST-002"}).json()
    sid = first["session_id"]
    client.post("/api/v1/chat", json={"message": "shipping policy?", "user_id": USER, "session_id": sid})

    detail = client.get(f"/api/v1/sessions/{sid}", params={"user_id": USER}).json()
    assert detail["state"]["customer_id"] == "CUST-002"
    user_msgs = [m["text"] for m in detail["messages"] if m["role"] == "user"]
    assert user_msgs == ["where is my order", "shipping policy?"]

    listed = client.get("/api/v1/sessions", params={"user_id": USER}).json()
    assert [s["session_id"] for s in listed] == [sid]
    assert listed[0]["title"] == "where is my order"

    assert client.delete(f"/api/v1/sessions/{sid}", params={"user_id": USER}).status_code == 204
    assert client.get(f"/api/v1/sessions/{sid}", params={"user_id": USER}).status_code == 404


def test_stream_emits_events(client):
    with client.stream("POST", "/api/v1/chat/stream", json={"message": "headphones please", "user_id": USER}) as r:
        assert r.status_code == 200
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    types_ = [e["type"] for e in events]
    assert types_[0] == "session" and types_[-1] == "done"
    assert "delta" in types_ and "final" in types_
    assert {"agent": "catalog_agent", "type": "agent"} in [{"agent": e.get("agent"), "type": e["type"]} for e in events]


def test_direct_specialist_api(client):
    body = client.post("/api/v1/agents/support/chat", json={"message": "shipping?", "user_id": USER}).json()
    assert body["agents"] == ["support_agent"]
    assert body["tool_calls"][0]["name"] == "get_store_policy"
    assert client.post("/api/v1/agents/nope/chat", json={"message": "x", "user_id": USER}).status_code == 404


def test_validation(client):
    assert client.post("/api/v1/chat", json={"message": "", "user_id": USER}).status_code == 422
    assert client.post("/api/v1/chat", json={"message": "hi", "user_id": "bad id!"}).status_code == 422


def test_data_endpoints(client):
    assert len(client.get("/api/v1/customers").json()) == 3
    assert client.get("/api/v1/products/ELEC-1001").json()["brand"] == "Aurora"
    assert client.get("/api/v1/products/NOPE").status_code == 404
    assert client.get("/api/v1/products", params={"category": "home"}).json()["count"] == 3


def test_llm_provider_error_maps_to_502(client, monkeypatch):
    from app.services import agent_service

    class FakeLiteLlmError(Exception):
        pass

    FakeLiteLlmError.__module__ = "litellm.exceptions"

    async def boom(*args, **kwargs):
        raise FakeLiteLlmError("auth failed")
        yield  # pragma: no cover

    svc = client.app.state.agent_service
    monkeypatch.setattr(svc.runners["coordinator"], "run_async", boom)
    r = client.post("/api/v1/chat", json={"message": "hi", "user_id": USER})
    assert r.status_code == 502
    assert agent_service.UpstreamLLMError
