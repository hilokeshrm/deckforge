import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import load_config  # noqa: E402
from engine.schema import Deck  # noqa: E402

SAMPLE = {
    "title": "Q3 Business Review",
    "subtitle": "Results and priorities",
    "slides": [
        {"layout": "title", "title": "Q3 Business Review", "subtitle": "Results and priorities", "notes": "Welcome."},
        {"layout": "section", "title": "Results"},
        {"layout": "stats", "title": "A record quarter",
         "stats": [{"value": "$4.2M", "label": "Revenue"}, {"value": "18%", "label": "Growth"},
                   {"value": "2.9%", "label": "Churn"}]},
        {"layout": "chart", "title": "Revenue grew every month",
         "chart": {"type": "column", "categories": ["Jul", "Aug", "Sep"],
                   "series": [{"name": "Revenue", "values": [1.2, 1.4, 1.6]}], "number_format": "$#M"},
         "bullets": ["September was the best month", "Enterprise drove growth"]},
        {"layout": "chart", "title": "Mix by region",
         "chart": {"type": "doughnut", "categories": ["North", "South", "West"],
                   "series": [{"name": "Share", "values": [50, 30, 20]}]}},
        {"layout": "two_column", "title": "Wins and gaps", "left_title": "Wins", "left": ["Two new markets", "NPS 61"],
         "right_title": "Gaps", "right": ["Hiring behind plan"]},
        {"layout": "table", "title": "By region", "table": {"header": ["Region", "Q2", "Q3"],
                                                            "rows": [["North", "1.0", "1.2"], ["South", "0.8", "0.9"]]}},
        {"layout": "bullets", "title": "Next quarter", "bullets": ["Launch: self-serve plan", "Hire 6 engineers"]},
        {"layout": "quote", "quote": "Best quarter in company history.", "attribution": "CEO"},
        {"layout": "closing", "title": "Thank you", "subtitle": "questions@example.com"},
    ],
}


class FakeLLM:
    """Stands in for the router: deterministic, no network, no GPU."""

    def __init__(self):
        self.calls = []

    def can(self, task):
        return task in ("plan", "edit", "summarize", "brand")

    def status(self):
        return {"fake": {"available": True}}

    def reload(self):
        pass

    def text(self, task, system, prompt, images=None, max_tokens=0):
        self.calls.append(task)
        return "condensed source"

    def structured(self, task, system, prompt, model_cls, images=None, max_tokens=0):
        self.calls.append(task)
        if model_cls is Deck:
            d = copy.deepcopy(SAMPLE)
            if task == "edit":
                d["title"] = "Q3 Business Review (edited)"
                d["slides"][0]["title"] = "Q3 Business Review (edited)"
            return Deck.model_validate(d)
        return model_cls()


@pytest.fixture
def sample_deck():
    return Deck.model_validate(copy.deepcopy(SAMPLE))


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    for key in ("inbox", "done", "work", "decks", "brand_inbox", "templates", "logs"):
        p = tmp_path / key
        p.mkdir()
        c["paths"][key] = p
    c["paths"]["state"] = tmp_path / "state.json"
    c["qa"] = {**c.get("qa", {}), "render_previews": False, "vision_review": False}
    c["render"] = {**c.get("render", {}), "formats": ["html"]}
    c["agent"] = {**c.get("agent", {}), "settle_seconds": 0, "max_attempts": 1}
    return c


@pytest.fixture
def fake_llm():
    return FakeLLM()
