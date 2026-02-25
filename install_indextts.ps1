# ============================================
# IndexTTS2 Installation Script
# ============================================
Write-Host "=== Installing IndexTTS2 ===" -ForegroundColor Cyan

# Step 1: Install uv package manager
Write-Host "`n[1/4] Installing uv package manager..." -ForegroundColor Yellow
pip install -U uv

# Step 2: Clone IndexTTS2 repo
Write-Host "`n[2/4] Cloning IndexTTS2 repository..." -ForegroundColor Yellow
if (Test-Path "third_party/index-tts") {
    Write-Host "  Already cloned, pulling latest..." -ForegroundColor Gray
    git -C third_party/index-tts pull
} else {
    New-Item -ItemType Directory -Force -Path "third_party" | Out-Null
    git clone https://github.com/index-tts/index-tts.git third_party/index-tts
}

# Step 3: Install dependencies via uv
Write-Host "`n[3/4] Installing IndexTTS2 dependencies..." -ForegroundColor Yellow
Push-Location third_party/index-tts
uv sync --all-extras
Pop-Location

# Step 4: Download model checkpoints
Write-Host "`n[4/4] Downloading IndexTTS2 model checkpoints..." -ForegroundColor Yellow
Push-Location third_party/index-tts
pip install "huggingface_hub[cli]"
huggingface-cli download IndexTeam/IndexTTS-2 --local-dir=checkpoints
Pop-Location

Write-Host "`n=== IndexTTS2 Installation Complete! ===" -ForegroundColor Green
Write-Host "Test with: python -c `"import sys; sys.path.insert(0,'third_party/index-tts'); print('IndexTTS2 path OK')`""
