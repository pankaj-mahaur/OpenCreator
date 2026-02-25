@echo off
echo ============================================
echo  Sovereign Instagram Agent - Full Setup
echo ============================================
echo.

echo [1/5] Installing remaining pip packages...
pip install ddgs faster-whisper instagrapi boto3 pydub
echo.

echo [2/5] Installing uv package manager...
pip install -U uv
echo.

echo [3/5] Cloning IndexTTS2...
if not exist "third_party" mkdir third_party
if not exist "third_party\index-tts" (
    git clone https://github.com/index-tts/index-tts.git third_party\index-tts
) else (
    echo   Already cloned, pulling latest...
    git -C third_party\index-tts pull
)
echo.

echo [4/5] Installing IndexTTS2 dependencies via uv...
cd third_party\index-tts
uv sync --all-extras
cd ..\..
echo.

echo [5/5] Downloading IndexTTS2 model checkpoints...
pip install "huggingface_hub[cli]"
cd third_party\index-tts
huggingface-cli download IndexTeam/IndexTTS-2 --local-dir=checkpoints
cd ..\..
echo.

echo ============================================
echo  Verifying installation...
echo ============================================
python _diagnose.py
echo.
echo ============================================
echo  SETUP COMPLETE!
echo ============================================
echo.
echo Next steps:
echo   1. Record voice sample: voice_samples\my_voice.wav
echo   2. Add your photo: assets\my_photo.png
echo   3. Test: python main.py --topic "AI news" --dry-run
echo.
pause
