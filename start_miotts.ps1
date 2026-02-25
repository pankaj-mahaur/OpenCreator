$ErrorActionPreference = "Stop"

Write-Host "Starting MioTTS 2.6B Environment..." -ForegroundColor Cyan

# 1. Pull the model via Ollama
$Model = "hf.co/Aratako/MioTTS-GGUF:MioTTS-2.6B-Q4_K_M.gguf"
Write-Host "Ensuring model is pulled: $Model"
ollama pull $Model

# 2. Start Ollama Server for MioTTS
Write-Host "Starting Ollama backend on port 8100..."
$env:OLLAMA_HOST = "localhost:8100"
$OllamaProcess = Start-Process -FilePath "ollama" -ArgumentList "serve" -PassThru -NoNewWindow

# 2b. Install Dependencies
Write-Host "Ensuring dependencies are installed..."

# 1. Install MioCodec (Critical dependency)
Write-Host "   - Installing MioCodec..."
python -m pip install git+https://github.com/Aratako/MioCodec.git

# 2. Install other dependencies manually to avoid build issues with pyproject.toml
Write-Host "   - Installing server dependencies..."
python -m pip install "fastapi>=0.111.0" "gradio>=4.0.0" "httpx>=0.27.0" g2p_en nltk soundfile "transformers<5" "uvicorn>=0.30.0" ninja accelerate

# 3. Try installing pyopenjtalk (might fail on Windows, but needed for JP)
try {
    python -m pip install pyopenjtalk
} catch {
    Write-Host "   ⚠️  pyopenjtalk failed to install (needed for Japanese, optional for English)" -ForegroundColor Yellow
}

# 4. We skip 'pip install -e .' and just use PYTHONPATH below


# Wait for Ollama to be ready
Start-Sleep -Seconds 5

# 3. Start MioTTS API Server
Write-Host "Starting Speech Synthesis API on port 5100..."
$env:PYTHONPATH = "third_party/MioTTS-Inference"

# Start the API server in a separate process
$ServerArgs = "third_party/MioTTS-Inference/run_server.py --port 5100 --llm-base-url http://localhost:8100/v1"
Start-Process -FilePath "python" -ArgumentList $ServerArgs -NoNewWindow

Write-Host "Services started!"
Write-Host "   - Ollama (MioTTS): http://localhost:8100"
Write-Host "   - TTS API:         http://localhost:5100"
Write-Host "   - Health Check:    http://localhost:5100/health"
Write-Host ""
Write-Host "Window will close if you press a key. Keep this running!"
Read-Host "Press Enter to exit (this will stop the services)..."

Stop-Process -Id $OllamaProcess.Id -ErrorAction SilentlyContinue
