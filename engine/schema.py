"""Data models shared by the planner (LLM output), renderer and UI."""
from __future__ import annotations

from typing import List, Literal, Optional, get_args

from pydantic import BaseModel, Field

Layout = Literal[
    "title", "section", "bullets", "two_column", "chart", "table",
    "stats", "image", "image_text", "quote", "closing",
]
LAYOUTS: tuple = get_args(Layout)


class Series(BaseModel):
    name: str
    values: List[float]


class ChartSpec(BaseModel):
    type: Literal["column", "bar", "line", "pie", "doughnut"] = "column"
    categories: List[str]
    series: List[Series]
    number_format: Optional[str] = None


class TableSpec(BaseModel):
    header: List[str]
    rows: List[List[str]]


class Stat(BaseModel):
    value: str
    label: str


class Slide(BaseModel):
    layout: Layout = "bullets"
    title: str = ""
    subtitle: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)
    left_title: Optional[str] = None
    left: List[str] = Field(default_factory=list)
    right_title: Optional[str] = None
    right: List[str] = Field(default_factory=list)
    chart: Optional[ChartSpec] = None
    table: Optional[TableSpec] = None
    stats: List[Stat] = Field(default_factory=list)
    image: Optional[str] = Field(None, description="exact filename from the ASSETS list")
    quote: Optional[str] = None
    attribution: Optional[str] = None
    notes: str = Field("", description="speaker notes")


class Deck(BaseModel):
    title: str
    subtitle: Optional[str] = None
    template: str = "default"
    slides: List[Slide]


class BrandPatch(BaseModel):
    """What the LLM may extract from a written style guide."""
    colors: dict = Field(default_factory=dict, description="role -> hex, roles: primary, accent, accent2, background, text")
    fonts: dict = Field(default_factory=dict, description="heading / body font family names")
    tone: Optional[str] = None
    footer: Optional[str] = None


class ReviewIssue(BaseModel):
    slide: int
    problem: str
    fix: str


class Review(BaseModel):
    issues: List[ReviewIssue] = Field(default_factory=list)
