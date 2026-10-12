# DeckForge

DeckForge is a presentation agent that turns your documents, data and brand kit into **animated HTML presentations**. It can run fully on a local NVIDIA RTX GPU (through Ollama), or use OpenAI or Claude. You can also choose a different provider for each task.

- **Input formats:** PDF (scanned PDFs are OCR'd), Word, PowerPoint, Excel, CSV, Markdown, text, HTML, URLs, images, and audio or video (transcribed on the GPU).
- **Brand templates:** drop in a logo, colours, fonts, images, a sample `.pptx` or a guidelines PDF, and DeckForge saves them as a reusable template.
- **Output:** each deck is a single self-contained `.html` file with:
  - slide transitions and staggered element entrances
  - charts that draw themselves and numbers that count up
  - keyboard, click and swipe navigation, fullscreen, and speaker notes (press `N`)
  - print-to-PDF

  You can also export an editable `.pptx` or a PDF.
- **Agent loop:** DeckForge watches `inbox/` and `brand-inbox/`. Every change you request creates a new version, and you can restore any earlier one.
- **Visual QA:** slides are rendered to images and reviewed by a vision model, and the problems it finds are fixed automatically.
- **Web UI:** create, edit, restyle, compare versions, manage brands and pick models, all from the browser.

```
inputs ─► ingest ─► (condense) ─► plan (LLM → deck JSON) ─► render HTML (+pptx/pdf) ─► screenshot ─► vision review ─► fix ─► vNNN.html
brand kit ─► template builder ─► design/templates/<brand>/brand.json + preview.html
```

## Setup (Windows + RTX)

1. Install the latest **NVIDIA driver**, **Python 3.10+**, and **Ollama** (https://ollama.com/download). Ollama uses CUDA automatically.
2. Run the setup script from this folder:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup.ps1
   ```
   It creates a virtual environment, installs the requirements and Chromium (used for screenshots and PDF export), and sets these Ollama GPU flags: `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`.
3. Restart Ollama, then run:
   ```powershell
   .\.venv\Scripts\python.exe run.py gpu-check
   ```
   This reads your VRAM, picks and downloads the right models, loads them, and reports what percentage of each model is on the GPU. Anything below 100% means part of the model is running on the CPU, which is slow. The check tells you what to change.
4. Run the tests. They are offline and need no GPU or LLM:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```
5. Start the UI and agent, then open http://127.0.0.1:8000:
   ```powershell
   .\.venv\Scripts\python.exe run.py ui
   ```

On Linux, run the same steps by hand: `python -m venv .venv`, `pip install -r requirements.txt`, `playwright install chromium`, then `ollama serve`.

### Local models by VRAM (`text_model: auto`)

| VRAM | Text (planning, writing) | Vision (OCR, captions, QA) |
|---|---|---|
| 24 GB+ (3090/4090/5090) | `qwen3:32b` | `gemma3:27b` |
| 16 GB (4060 Ti 16G / 4080 / 5080) | `qwen3:14b` | `gemma3:12b` |
| 12 GB (3060 / 4070) | `qwen3:8b` | `gemma3:12b` |
| 8 GB | `qwen3:8b` | `gemma3:4b` |

To override, set `llm.ollama.text_model` and `vision_model` in `config.yaml` or on the Settings page. On cards with less than 16 GB, setting `OLLAMA_MAX_LOADED_MODELS=1` stops Ollama from holding the text and vision models in VRAM at the same time.

### OpenAI and Claude

Put your keys in `.env` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). In `config.yaml` → `llm.routing`, or on the Settings page, choose which provider handles each task. For example, you can keep summarising and QA on the local GPU and send the planning and editing steps to Claude:

```yaml
routing:
  plan: anthropic
  edit: anthropic
```

If a provider fails or has no key, DeckForge falls back through `fallback_order`. The Claude provider uses `claude-opus-5-5` with server-side refusal fallback turned on (`refusal_fallback: true`).

## Using it

### Web UI
| Page | What it does |
|---|---|
| **New deck** | Drop files, write a brief, then choose a template, slide count and extra exports |
| **Decks** | Watch a deck play, step through slides, present full screen, or download HTML, PPTX or PDF |
| **Change** tab | Describe a change in plain words ("slide 3 → chart", "add a risks slide") and optionally attach new files |
| **Restyle** tab | Apply a different brand template |
| **JSON** tab | Edit text or data by hand. This creates a new version without calling the LLM |
| **History** tab | Restore any earlier version |
| **Brands** | Upload a logo, colours, fonts, images, a sample deck or guidelines, and see a live preview of the template |
| **Queue** | Live status and logs of every job |
| **Settings** | Choose a provider per task, set models, toggle QA, and run a GPU check |

### Dropping files into folders
- **New deck:** drop a document into `inbox/`, or drop a folder containing `request.md` and your files. See `examples/create-request.md`.
- **Change a deck:** drop a `.md` file with `action: edit` and `deck: <name>` (see `examples/edit-request.md`). Other actions are `restyle` (with `template:`), `revert` (with `version:`), `export` (with `formats: [pptx, pdf]`) and `brand`.
- **New brand:** create a folder `brand-inbox/<name>/` with a logo, images, a sample `.pptx` and/or a guidelines PDF, plus an optional `brand.yaml` (see `examples/brand.yaml`). DeckForge rebuilds the template whenever the folder changes.
- **Results:** finished decks go to `decks/<name>/vNNN.html`, and a report for each job goes to `done/<job>/result.md`.

### Command line
```powershell
python run.py make report.pdf sales.xlsx --brief "Q3 board update" --template acme --slides 12 --pptx
python run.py edit q3-review "Slide 4: make it a line chart"
python run.py brand .\my-brand --name acme
python run.py watch        # agent loop only, no UI
python run.py providers    # which LLMs are reachable
```

### Presenting
Open `decks/<name>/vNNN.html` in any browser. It works offline and has no dependencies.

| Key | Action |
|---|---|
| `→` `Space` `Enter` | Next slide |
| `←` | Previous slide |
| `F` | Fullscreen |
| `N` | Speaker notes |
| `Ctrl+P` | PDF (one slide per page) |

Add `#5` to the URL to open at slide 5.

## Layouts

`title`, `section`, `bullets`, `two_column`, `chart` (column, bar, line, pie, doughnut), `table`, `stats` (animated counters), `image` (full screen with a slow zoom), `image_text` (image reveal), `quote`, `closing`.

## Project layout
```
engine/
  agent.py          inbox loop, request parsing, versions, QA loop
  planner.py        prompts: plan / edit / condense / review
  llm/              ollama (GPU), openai, anthropic providers + router (routing, JSON validation, fallback)
  ingest/           readers for every input format, OCR + image captions
  brand/            template builder, colour extraction, pptx theme reader
  render/           html_renderer (animated decks), svg_charts, pptx_renderer
  qa/               screenshots (Playwright), contact sheets, static checks
  gpu.py            VRAM detection, model choice, offload check
ui/                 FastAPI server + single-page app
tests/              offline test suite (fake LLM)
```
