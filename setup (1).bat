@echo off
setlocal
echo ============================================
echo  Music Downloader - Dependency Setup
echo ============================================
echo.

REM ── Python packages ─────────────────────────────────────────
echo [1/4] Installing/upgrading Python packages...
python -m pip install --upgrade --quiet --break-system-packages customtkinter spotdl yt-dlp
if errorlevel 1 (
    python -m pip install --upgrade --quiet customtkinter spotdl yt-dlp
)
echo     Done.
echo.

REM ── ffmpeg (needed for audio conversion) ────────────────────
echo [2/4] Checking ffmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo     Not found. Installing via winget...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
) else (
    echo     Already installed.
)
echo.

REM ── deno (needed for YouTube JS challenge solving) ──────────
echo [3/4] Checking deno...
where deno >nul 2>&1
if errorlevel 1 (
    echo     Not found. Installing...
    powershell -NoProfile -Command "irm https://deno.land/install.ps1 | iex"
) else (
    echo     Already installed.
)
echo.

REM ── PATH refresh notice ──────────────────────────────────────
echo [4/4] Verifying...
echo.
echo ============================================
echo  IMPORTANT: Close this window and open a
echo  NEW terminal before running the app, so
echo  PATH changes (ffmpeg/deno) take effect.
echo ============================================
echo.
echo Optional (for Spotify to work reliably):
echo   1. Create an app at https://developer.spotify.com/dashboard
echo   2. Set these env vars (replace with your values):
echo      setx SPOTIPY_CLIENT_ID "your_client_id"
echo      setx SPOTIPY_CLIENT_SECRET "your_client_secret"
echo.
pause
