import json

from PIL import Image

from engine.agent import Agent, enqueue
from engine.brand import load_brand
from engine.store import DeckStore


def _job(agent, jid):
    return agent.state.data["jobs"][jid]


def test_create_edit_revert_save_export(cfg, fake_llm):
    agent = Agent(cfg, llm=fake_llm)

    jid = enqueue(cfg, {"action": "create", "deck": "q3", "slides": 10},
                  "Quarterly review for the board", [("notes.txt", b"Revenue grew 18% to $4.2M.")])
    assert agent.tick() == 1
    job = _job(agent, jid)
    assert job["status"] == "done", job.get("traceback")
    store = DeckStore(cfg["paths"]["decks"], "q3")
    assert store.versions() == [1]
    assert (store.dir / "v001.html").exists()
    assert (cfg["paths"]["done"] / jid / "result.md").exists()

    jid = enqueue(cfg, {"action": "edit", "deck": "q3"}, "Make the title punchier")
    agent.tick()
    assert _job(agent, jid)["status"] == "done"
    assert store.load().title.endswith("(edited)")

    jid = enqueue(cfg, {"action": "revert", "deck": "q3", "version": 1})
    agent.tick()
    assert _job(agent, jid)["status"] == "done"
    assert store.versions() == [1, 2, 3]
    assert not store.load().title.endswith("(edited)")

    deck = store.load()
    deck.slides[1].title = "Hand edited"
    jid = enqueue(cfg, {"action": "save", "deck": "q3"}, "", [("deck.json", deck.model_dump_json().encode())])
    agent.tick()
    assert _job(agent, jid)["status"] == "done"
    assert store.load().slides[1].title == "Hand edited"

    jid = enqueue(cfg, {"action": "export", "deck": "q3", "formats": ["pptx"]})
    agent.tick()
    assert _job(agent, jid)["status"] == "done"
    assert (store.dir / "v004.pptx").exists()
    assert len(store.read_history()) == 4


def test_failed_job_is_reported(cfg, fake_llm):
    agent = Agent(cfg, llm=fake_llm)
    jid = enqueue(cfg, {"action": "edit", "deck": "does-not-exist"}, "anything")
    agent.tick()
    job = _job(agent, jid)
    assert job["status"] == "failed" and "not found" in job["error"]
    assert "failed" in (cfg["paths"]["done"] / jid / "result.md").read_text(encoding="utf-8")


def test_brand_folder_becomes_template(cfg, fake_llm, tmp_path):
    folder = cfg["paths"]["brand_inbox"] / "Acme"
    folder.mkdir()
    logo = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    for x in range(40, 360):
        for y in range(40, 120):
            logo.putpixel((x, y), (200, 20, 60, 255))
    logo.save(folder / "logo.png")
    (folder / "brand.yaml").write_text("fonts: {heading: Montserrat}\nfooter: Acme Inc.\n", encoding="utf-8")
    agent = Agent(cfg, llm=fake_llm)
    agent.sync_brands()
    brand, tdir = load_brand(cfg["paths"]["templates"], "acme")
    assert brand["name"] == "acme"
    assert brand["colors"]["primary"] != "#1D4ED8"  # came from the red logo
    assert brand["fonts"]["heading"] == "Montserrat" and brand["footer"] == "Acme Inc."
    assert (tdir / "assets" / "logo.png").exists()
    assert (tdir / "preview.html").exists()
    # unchanged folder is not rebuilt
    sig_before = json.loads(cfg["paths"]["state"].read_text())["brands"]["acme"]
    agent.sync_brands()
    assert json.loads(cfg["paths"]["state"].read_text())["brands"]["acme"] == sig_before
