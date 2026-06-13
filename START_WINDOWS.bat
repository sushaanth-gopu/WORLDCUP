@echo off
chcp 65001 >nul 2>&1
title PREDICTA26 — World Cup Market Launcher

cls
echo.
echo   =====================================================
echo    PREDICTA26 — World Cup 2026 Prediction Market
echo   =====================================================
echo.

:: ── Move to the folder this script lives in ──
cd /d "%~dp0"
echo   Working in: %~dp0
echo.

:: ── Check for .env file ──
if not exist ".env" (
  echo   STOP - You haven't set up your .env file yet!
  echo.
  echo   Before this launcher can work, you need to:
  echo.
  echo   1. Open this folder in File Explorer
  echo   2. Find the file called ".env.example"
  echo   3. Make a copy of it - right-click, Copy, then Paste
  echo   4. Rename the copy from ".env.example" to just ".env"
  echo   5. Open ".env" with Notepad and fill in your Supabase values
  echo   6. Then double-click this launcher again
  echo.
  echo   Full instructions are in SETUP_GUIDE.md
  echo.
  pause
  exit /b 1
)

:: ── Check that .env has real values ──
findstr /c:"YOUR_SUPABASE_URL_HERE" .env >nul 2>&1
if %errorlevel% equ 0 (
  echo   STOP - Your .env file still has placeholder values!
  echo.
  echo   Open the ".env" file with Notepad and replace:
  echo     YOUR_SUPABASE_URL_HERE       with your real Supabase URL
  echo     YOUR_SUPABASE_ANON_KEY_HERE  with your real Supabase anon key
  echo.
  echo   Then double-click this launcher again.
  echo.
  pause
  exit /b 1
)

findstr /c:"YOUR_SUPABASE_ANON_KEY_HERE" .env >nul 2>&1
if %errorlevel% equ 0 (
  echo   STOP - Your .env file still has placeholder values!
  echo.
  echo   Open the ".env" file with Notepad and replace:
  echo     YOUR_SUPABASE_URL_HERE       with your real Supabase URL
  echo     YOUR_SUPABASE_ANON_KEY_HERE  with your real Supabase anon key
  echo.
  echo   Then double-click this launcher again.
  echo.
  pause
  exit /b 1
)

echo   [OK] .env file found and looks good
echo.

:: ── Check for Node.js ──
where node >nul 2>&1
if %errorlevel% neq 0 (
  echo   Node.js is not installed on your computer.
  echo.
  echo   Opening the Node.js download page now...
  start https://nodejs.org/en/download/
  echo.
  echo   1. Download the "Windows Installer (.msi)" - the LTS version
  echo   2. Run the installer, click Next through all steps
  echo   3. IMPORTANT: Check the box "Automatically install necessary tools"
  echo   4. After install finishes, RESTART your computer
  echo   5. Then double-click this launcher again
  echo.
  pause
  exit /b 1
)

for /f "tokens=*" %%i in ('node --version') do set NODE_VER=%%i
echo   [OK] Node.js found: %NODE_VER%
echo.

:: ── Install packages if needed ──
if not exist "node_modules\" (
  echo   Installing packages - this takes 1-3 minutes the first time...
  echo   Lots of text will scroll by - that is completely normal.
  echo.
  call npm install
  if %errorlevel% neq 0 (
    echo.
    echo   Package installation failed.
    echo   Check your internet connection and try again.
    pause
    exit /b 1
  )
  echo.
  echo   [OK] All packages installed successfully
) else (
  echo   [OK] Packages already installed - skipping (fast start)
)

echo.

:: ── Open browser after delay ──
echo   Opening your browser in 3 seconds...
timeout /t 3 /nobreak >nul
start http://localhost:5173

:: ── Start the dev server ──
echo.
echo   =====================================================
echo    PREDICTA26 IS STARTING...
echo   =====================================================
echo.
echo   Your app will open at: http://localhost:5173
echo.
echo   To STOP the app: press Ctrl + C in this window
echo   To RESTART: double-click START_WINDOWS.bat again
echo.
echo   =====================================================
echo.

call npm run dev

echo.
echo   The app has stopped. Double-click START_WINDOWS.bat to restart.
pause
