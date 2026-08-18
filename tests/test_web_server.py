import asyncio
from aiohttp.test_utils import TestClient, TestServer
from dct.web.server import create_app
from dct.core.registry import ServerRegistry


def test_web_server_endpoints():
    async def _test():
        registry = ServerRegistry()
        app = create_app(registry)
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()

        try:
            # 1. Test GET /
            res = await client.get("/")
            assert res.status == 200
            text = await res.text()
            assert "DCT-AGENT" in text

            # 2. Test GET /api/status
            res = await client.get("/api/status")
            assert res.status == 200
            data = await res.json()
            assert "agent_mode" in data
            assert "session_mode" in data

            # 3. Test GET /api/servers
            res = await client.get("/api/servers")
            assert res.status == 200
            data = await res.json()
            assert "servers" in data

            # 4. Test POST /api/toggle_agent
            res = await client.post("/api/toggle_agent", json={"enabled": True})
            assert res.status == 200
            data = await res.json()
            assert data["agent_mode"] is True

            # 5. Test POST /api/toggle_plan
            res = await client.post("/api/toggle_plan", json={"mode": "plan"})
            assert res.status == 200
            data = await res.json()
            assert data["session_mode"] == "plan"

            # 6. Test Task API
            res = await client.post(
                "/api/tasks/create",
                json={"subject": "Test Web Task", "description": "Verify API"},
            )
            assert res.status == 200
            task_data = await res.json()
            assert task_data["ok"] is True
            assert task_data["task"]["subject"] == "Test Web Task"
            task_id = task_data["task"]["id"]

            res = await client.post(
                "/api/tasks/update",
                json={"task_id": task_id, "status": "completed"},
            )
            assert res.status == 200
            update_data = await res.json()
            assert update_data["task"]["status"] == "completed"

            # 7. Test GET /api/sessions
            res = await client.get("/api/sessions")
            assert res.status == 200
            sess_data = await res.json()
            assert "sessions" in sess_data

            # 8. Test POST /api/clear
            res = await client.post("/api/clear")
            assert res.status == 200
            clear_data = await res.json()
            assert clear_data["ok"] is True
        finally:
            await client.close()

    asyncio.run(_test())

