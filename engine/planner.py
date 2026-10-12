"""LLM prompts: source material -> Deck JSON, change requests -> updated Deck JSON."""
from __future__ import annotations

from .schema import Deck, Review
from .util import log

LAYOUT_GUIDE = """Available slide layouts (field "layout"):
- title: first slide. title + subtitle.
- section: divider between parts of a longer deck. title (+ optional subtitle).
- bullets: title + 3-6 bullets. May set "image" to show a picture beside the text.
- two_column: comparisons (before/after, pros/cons, option A/B). left_title + left[], right_title + right[].
- chart: numeric data. chart = {type: column|bar|line|pie|doughnut, categories[], series[{name, values[]}], number_format?}.
  Values must be numbers taken from the source; one value per category. number_format is a template like "$#M" or "#%".
  Optional bullets[] (2-3 takeaways) appear beside the chart.
- table: compact tabular data. table = {header[], rows[[...]]}, max 7 columns x 10 rows.
- stats: 2-4 headline numbers. stats = [{value: "42%", label: "short label"}]. Numbers animate, so keep values numeric-looking.
- image: full-screen picture with the title over it. image = exact filename from ASSETS.
- image_text: picture left, title + bullets right. image = exact filename from ASSETS.
- quote: quote + attribution (only real quotes from the source).
- closing: last slide (thank you / next steps / contact). title + subtitle, optional bullets.

Writing rules:
- The output is an animated HTML presentation: slides should be visual and light on text.
- One idea per slide. Titles are short (max ~8 words) and state the takeaway, not just the topic.
- Bullets: max 6 per slide, max ~14 words each, parallel phrasing, no trailing full stops.
  "Label: detail" style is welcome - the label is highlighted.
- Never invent facts, numbers, quotes, names or dates. No data in the source -> no chart/stats.
- Only use images listed under ASSETS, by exact filename. Skip logos and tiny icons.
- Vary the layouts so consecutive slides look different. Prefer stats/chart/table/two_column over plain bullets when the content fits.
- notes: 2-4 sentences the presenter can say on each slide.
- Write in the language of the source unless the request says otherwise."""

SYSTEM_PLAN = "You are a senior presentation designer and editor who turns source material into clear, well-structured slide decks.\n\n" + LAYOUT_GUIDE
SYSTEM_EDIT = "You are a senior presentation designer who revises existing slide decks precisely.\n\n" + LAYOUT_GUIDE


def condense(llm, text: str, limit: int, chunk: int) -> str:
    """Summarise long sources chunk by chunk (map-reduce) until they fit the planner's budget."""
    rounds = 0
    while len(text) > limit and rounds < 3:
        rounds += 1
        pieces = [text[i:i + chunk] for i in range(0, len(text), chunk)]
        log.info("source is %d chars: condensing %d chunk(s) (round %d)", len(text), len(pieces), rounds)
        target = max(150, int(limit / len(pieces) / 6))  # words per chunk summary
        out = []
        for k, piece in enumerate(pieces, 1):
            out.append(llm.text(
                "summarize",
                "You condense documents for a presentation writer. Keep every number, name, date, "
                "quote, table and conclusion; drop filler. Use Markdown headings and bullets.",
                f"Condense part {k}/{len(pieces)} to at most {target} words:\n\n{piece}",
                max_tokens=2500,
            ))
        text = "\n\n".join(out)
    return text[:limit]


def plan_deck(llm, source: str, assets_block: str, brand: dict, request: dict, cfg: dict) -> Deck:
    ing = cfg.get("ingest", {})
    source = condense(llm, source, int(ing.get("max_source_chars", 24000)), int(ing.get("chunk_chars", 10000)))
    defaults = cfg.get("defaults", {})
    n = request.get("slides") or defaults.get("slides", 10)
    prompt = f"""REQUEST:
{request.get('instructions') or 'Create a presentation from the source material.'}

TARGET: about {n} slides. Audience: {request.get('audience') or defaults.get('audience', 'general audience')}.
Tone of voice: {brand.get('tone', 'clear and concise')}.
Template: {brand.get('name', 'default')}

ASSETS (images you may use):
{assets_block}

SOURCE MATERIAL:
<<<
{source or '(no documents - use the request text above as the content)'}
>>>

Create the deck. Start with a title slide and end with a closing slide."""
    deck = llm.structured("plan", SYSTEM_PLAN, prompt, Deck, max_tokens=16000)
    deck.template = brand.get("name", "default")
    return deck


def edit_deck(llm, deck: Deck, instruction: str, assets_block: str, extra_source: str = "") -> Deck:
    prompt = f"""CURRENT DECK (JSON):
{deck.model_dump_json(indent=1, exclude_none=True)}

ASSETS (images you may use):
{assets_block}
{('NEW SOURCE MATERIAL:' + chr(10) + '<<<' + chr(10) + extra_source[:20000] + chr(10) + '>>>') if extra_source.strip() else ''}

CHANGE REQUEST:
{instruction}

Apply the change request. Slide numbers in the request are 1-based. Keep everything that the
request doesn't mention exactly as it is (same text, order and layouts). Return the complete updated deck."""
    new = llm.structured("edit", SYSTEM_EDIT, prompt, Deck, max_tokens=16000)
    new.template = deck.template
    return new


def review_slides(llm, sheets: list[tuple[int, object]]) -> Review:
    """Vision QA on contact sheets [(first_slide_number, png_path)]."""
    issues = []
    for start, sheet in sheets:
        r = llm.structured(
            "review",
            "You are a meticulous presentation QA reviewer.",
            f"These are rendered slides; the red number on each thumbnail is the slide number (starting at {start}). "
            "List only real visual problems: text cut off or overflowing, overlapping elements, unreadable contrast, "
            "empty or unbalanced slides, too much text, badly cropped images. For each give the slide number, the "
            "problem, and a concrete content fix (e.g. 'shorten bullet 3', 'split into two slides', "
            "'use two_column layout'). If everything looks fine return {\"issues\": []}.",
            Review,
            images=[sheet],
            max_tokens=2000,
        )
        issues += r.issues
    return Review(issues=issues)


def fix_instruction(review: Review) -> str:
    return "Fix these problems found in visual QA:\n" + "\n".join(
        f"- slide {i.slide}: {i.problem} -> {i.fix}" for i in review.issues)
