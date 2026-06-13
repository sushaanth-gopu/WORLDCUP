#!/bin/bash

# ─────────────────────────────────────────────────────────
# PREDICTA26 — Mac Auto-Launcher
# Double-click this file to install everything and start the app
# ─────────────────────────────────────────────────────────

# Make terminal window stay open and visible
osascript -e 'tell application "Terminal" to activate' 2>/dev/null

clear
echo ""
echo "  ██████╗ ██████╗ ███████╗██████╗ ██╗ ██████╗████████╗ █████╗ ██████╗  ██████╗  ██████╗ "
echo "  ██╔══██╗██╔══██╗██╔════╝██╔══██╗██║██╔════╝╚══██╔══╝██╔══██╗╚════██╗██╔════╝ ╚════██╗"
echo "  ██████╔╝██████╔╝█████╗  ██║  ██║██║██║        ██║   ███████║ █████╔╝███████╗  █████╔╝"
echo "  ██╔═══╝ ██╔══██╗██╔══╝  ██║  ██║██║██║        ██║   ██╔══██║██╔═══╝ ██╔═══██╗██╔═══╝ "
echo "  ██║     ██║  ██║███████╗██████╔╝██║╚██████╗   ██║   ██║  ██║███████╗╚██████╔╝███████╗"
echo "  ╚═╝     ╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝ ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚══════╝"
echo ""
echo "  World Cup 2026 — Private Prediction Market"
echo "  ─────────────────────────────────────────────────────────"
echo ""

# ── Step 1: Move to the folder this script lives in ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "  📂 Working in: $SCRIPT_DIR"
echo ""

# ── Step 2: Check for .env file ──
if [ ! -f ".env" ]; then
  echo "  ⚠️  STOP — You haven't set up your .env file yet!"
  echo ""
  echo "  Before this launcher can work, you need to:"
  echo ""
  echo "  1. Open this folder in Finder"
  echo "  2. Find the file called '.env.example'"
  echo "  3. Make a copy of it and rename the copy to just '.env'"
  echo "  4. Open '.env' with TextEdit and fill in your two Supabase values"
  echo "  5. Then double-click this launcher again"
  echo ""
  echo "  (Full instructions are in SETUP_GUIDE.md)"
  echo ""
  read -p "  Press Enter to close..."
  exit 1
fi

# ── Step 3: Check that .env actually has real values ──
if grep -q "YOUR_SUPABASE_URL_HERE" .env || grep -q "YOUR_SUPABASE_ANON_KEY_HERE" .env; then
  echo "  ⚠️  STOP — Your .env file still has placeholder values!"
  echo ""
  echo "  Open the '.env' file and replace:"
  echo "    YOUR_SUPABASE_URL_HERE     → with your real Supabase project URL"
  echo "    YOUR_SUPABASE_ANON_KEY_HERE → with your real Supabase anon key"
  echo ""
  echo "  Then double-click this launcher again."
  echo ""
  read -p "  Press Enter to close..."
  exit 1
fi

echo "  ✓ .env file found and looks good"
echo ""

# ── Step 4: Check for Node.js ──
if ! command -v node &> /dev/null; then
  echo "  ⚠️  Node.js is not installed on your Mac."
  echo ""
  echo "  Opening the Node.js download page for you now..."
  open "https://nodejs.org/en/download/"
  echo ""
  echo "  1. Download the 'macOS Installer (.pkg)' — the LTS version"
  echo "  2. Install it (double-click the .pkg, follow the steps)"
  echo "  3. Then double-click this launcher again"
  echo ""
  read -p "  Press Enter to close..."
  exit 1
fi

NODE_VERSION=$(node --version)
echo "  ✓ Node.js found: $NODE_VERSION"
echo ""

# ── Step 5: Check for npm ──
if ! command -v npm &> /dev/null; then
  echo "  ✗ npm not found. Please reinstall Node.js from https://nodejs.org"
  read -p "  Press Enter to close..."
  exit 1
fi

# ── Step 6: Install packages (only if node_modules doesn't exist or is outdated) ──
if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
  echo "  📦 Installing packages (this takes 1-3 minutes the first time)..."
  echo "     Lots of text will scroll — that's completely normal."
  echo ""
  npm install
  if [ $? -ne 0 ]; then
    echo ""
    echo "  ✗ Package installation failed."
    echo "  Try running 'npm install' manually in Terminal, or check your internet connection."
    read -p "  Press Enter to close..."
    exit 1
  fi
  echo ""
  echo "  ✓ All packages installed successfully"
else
  echo "  ✓ Packages already installed — skipping (fast start)"
fi

echo ""

# ── Step 7: Open browser after a short delay ──
echo "  🌐 Opening your browser in 3 seconds..."
(sleep 3 && open "http://localhost:5173") &

# ── Step 8: Start the dev server ──
echo ""
echo "  ─────────────────────────────────────────────────────────"
echo "  🚀 PREDICTA26 IS STARTING..."
echo "  ─────────────────────────────────────────────────────────"
echo ""
echo "  Your app will open at: http://localhost:5173"
echo ""
echo "  To stop the app: press Ctrl + C in this window"
echo "  To restart: just double-click START_MAC.command again"
echo ""
echo "  ─────────────────────────────────────────────────────────"
echo ""

npm run dev
