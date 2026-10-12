# DeckForge setup for a Windows machine with an NVIDIA RTX GPU.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Write-Host "== DeckForge setup ==" -ForegroundColor Cyan

# 1. GPU
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) { nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader }
else { Write-Warning "nvidia-smi not found: install the latest NVIDIA driver, otherwise models run on CPU." }

# 2. Python venv + packages
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "Python 3.10+ is required (https://www.python.org/downloads/)" }
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m playwright install chromium

# 3. Ollama (uses CUDA automatically)
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
  Write-Warning "Ollama not found. Install it from https://ollama.com/download then re-run this script."
} else {
  # GPU-friendly server settings (persisted for the user)
  [Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
  [Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
  Write-Host "Set OLLAMA_FLASH_ATTENTION=1 and OLLAMA_KV_CACHE_TYPE=q8_0 (restart Ollama to apply)."
}

# 4. .env
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env - add API keys there if you want OpenAI/Claude." }

Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe run.py gpu-check     # picks + pulls models for your VRAM, verifies GPU offload"
Write-Host "  .\.venv\Scripts\python.exe -m pytest -q         # offline test suite"
Write-Host "  .\.venv\Scripts\python.exe run.py ui            # open http://127.0.0.1:8000"
