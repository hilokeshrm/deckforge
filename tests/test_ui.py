from fastapi.testclient import TestClient

from engine.agent import Agent
from ui.server import create_app


def test_ui_end_to_end(cfg, fake_llm):
    agent = Agent(cfg, llm=fake_llm)
    client = TestClient(create_app(cfg, agent))

    assert "DeckForge" in client.get("/").text
    assert client.get("/api/status").status_code == 200

    r = client.post("/api/jobs", data={"action": "create", "deck": "ui-deck", "instructions": "A short pitch"},
                    files=[("files", ("brief.txt", b"We sell rockets.", "text/plain"))])
    jid = r.json()["id"]
    agent.tick()
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "done"

    decks = client.get("/api/decks").json()
    assert decks[0]["name"] == "ui-deck"
    detail = client.get("/api/decks/ui-deck").json()
    assert detail["version"] == 1 and "v001.html" in detail["files"]
    page = client.get("/files/decks/ui-deck/v001.html")
    assert page.status_code == 200 and "<section" in page.text
    assert client.get("/files/decks/ui-deck/../../config.yaml").status_code == 404

    body = detail["deck"]
    body["slides"][0]["title"] = "Edited in the UI"
    jid = client.put("/api/decks/ui-deck", json=body).json()["id"]
    agent.tick()
    assert client.get("/api/decks/ui-deck").json()["deck"]["slides"][0]["title"] == "Edited in the UI"

    r = client.post("/api/templates", data={"name": "Brand X", "primary": "#ff0055"})
    agent.tick()
    names = [t["name"] for t in client.get("/api/templates").json()]
    assert "brand-x" in names
