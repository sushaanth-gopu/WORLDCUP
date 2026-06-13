# 🏆 PREDICTA26 — Setup Guide
### World Cup 2026 Prediction Market — Private Platform for 35 Users

---

## THE BIG PICTURE

You have **3 things to do**, in order:

| Step | What | Time |
|------|------|------|
| 1 | Set up your Supabase database online | ~20 min |
| 2 | Fill in one config file in VS Code | ~2 min |
| 3 | Double-click one file on your computer | ~3 min |

After Step 3, your app opens in the browser automatically.

---

## BEFORE YOU START — Install VS Code (if you haven't already)

You said you already have VS Code — great, skip this. But just in case:
1. Go to **https://code.visualstudio.com**
2. Click the big download button
3. Install it like any normal app

---

## STEP 1 — SET UP YOUR SUPABASE DATABASE

Supabase is the free online service that stores all your users, matches, and trade data. Think of it like your app's brain — it lives on the internet, not on your computer.

### 1A — Create your free Supabase account

1. Open your browser and go to **https://supabase.com**
2. Click **"Start your project"**
3. Sign up — use **"Continue with GitHub"** (easiest) or create an email account
4. Once logged in, you'll see a button that says **"New project"** — click it

### 1B — Create a new project

1. Fill in the form:
   - **Name:** type `predicta26`
   - **Database Password:** something strong like `WorldCup2026!Market` — write this down
   - **Region:** pick whichever is closest to you (EU West is fine for Dubai)
2. Click **"Create new project"**
3. You'll see a spinning loading screen — **wait 2-3 minutes without clicking away**
4. When it stops and you see a dashboard, you're ready

### 1C — Run the database tables

1. Look at the **left sidebar** — find the icon that looks like a **database cylinder**
2. Hover over it until you see **"SQL Editor"** — click it
3. You'll see a big empty text box — click inside it, select all (Ctrl+A / Cmd+A), delete everything
4. Now go to VS Code. Open your `worldcup-predict` folder:
   - In VS Code: File → Open Folder → find and select the `worldcup-predict` folder → click Open
5. In the left panel of VS Code, you'll see all your files listed. Click on the `supabase` folder to expand it
6. Click on **`01_schema.sql`** — the file opens in the main area
7. Select all the text (Ctrl+A / Cmd+A) and copy it (Ctrl+C / Cmd+C)
8. Go back to your browser (Supabase SQL Editor), click in the text box, and paste (Ctrl+V / Cmd+V)
9. Click the green **"Run"** button at the bottom right
10. Wait a few seconds — you should see green text saying **"Success"**
    - Red text is usually fine as long as "Success" appears at the end

### 1D — Run the functions

1. Click the small **"+"** button at the top of the SQL Editor panel to open a new tab
2. Go back to VS Code, click **`02_functions.sql`** in the supabase folder
3. Select all, copy, paste into the new Supabase tab, click **"Run"**
4. Should say "Success"

### 1E — Add the match data

1. Click **"+"** again in Supabase for another new tab
2. In VS Code, click **`03_seed.sql`**
3. Select all, copy, paste into Supabase, click **"Run"**
4. Should say "Success" — this adds all 16 Round of 32 matches

### 1F — Turn off email confirmation

1. In the left sidebar, click the **person/silhouette icon** — that's **"Authentication"**
2. In the sub-menu, click **"Providers"**
3. Click **"Email"** to expand it
4. Find **"Confirm email"** and toggle it **OFF**
5. Click **"Save"**

### 1G — Copy your two secret keys

1. In the left sidebar, click the **gear/cog icon** at the very bottom — **"Project Settings"**
2. Click **"API"** in the sub-menu
3. Copy these two values — paste them into a notes app temporarily:
   - **"Project URL"** — looks like `https://abcdefghijk.supabase.co`
   - **"anon public"** key — the long string starting with `eyJ...`
4. Keep this browser tab open

---

## STEP 2 — FILL IN YOUR CONFIG FILE IN VS CODE

1. Go to VS Code — your `worldcup-predict` folder should already be open from Step 1
2. In the left file panel, find the file called **`.env.example`**
   - If you don't see it, press **Ctrl+Shift+P** (Windows) or **Cmd+Shift+P** (Mac), type "reveal in explorer" and press Enter — then look in the folder that opens
   - Alternatively: in VS Code's top menu, click **View → Explorer** to make sure the file panel is showing
3. Right-click on **`.env.example`** → click **"Copy"**
4. Right-click on an empty space in that same file panel → click **"Paste"**
5. A copy appears called **`.env.example copy`** or similar — click on its name once to rename it
6. Type exactly `.env` and press Enter
7. Click on your new **`.env`** file to open it — you'll see:
   ```
   VITE_SUPABASE_URL=YOUR_SUPABASE_URL_HERE
   VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY_HERE
   ```
8. Click on `YOUR_SUPABASE_URL_HERE` and replace it with your Supabase **Project URL**
9. Click on `YOUR_SUPABASE_ANON_KEY_HERE` and replace it with your Supabase **anon public key**
10. Save the file — **Ctrl+S** (Windows) or **Cmd+S** (Mac)

When done it should look like:
```
VITE_SUPABASE_URL=https://xyzabcdefghijk.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9....(very long)
```

VS Code might show a small popup saying something about environment variables — just dismiss it, that's normal.

---

## STEP 3 — DOUBLE-CLICK THE LAUNCHER

This is the last thing you do. It installs everything and opens the app automatically.

### On Mac:

1. Open Finder and navigate to your `worldcup-predict` folder
2. Find the file called **`START_MAC.command`**
3. **Double-click it**

   The first time, Mac might say *"cannot be opened because it is from an unidentified developer"*:
   - Right-click (or Control+click) on `START_MAC.command`
   - Click **"Open"**
   - Click **"Open"** again in the popup
   - You'll never see this warning again for this file

4. A terminal window opens and automatically:
   - Checks your `.env` is filled in correctly
   - Installs Node.js if you don't have it (opens the download page for you)
   - Installs all the app's packages — takes ~2 minutes the **first time only**, instant after that
   - Opens your browser to `http://localhost:5173`
   - Starts the app

### On Windows:

1. Open File Explorer and navigate to your `worldcup-predict` folder
2. Find the file called **`START_WINDOWS.bat`**
3. **Double-click it**

   Windows might show a blue "Windows protected your PC" popup — click **"More info"** then **"Run anyway"**

4. A black command window opens and does everything automatically

### What success looks like:

Your browser opens to a dark black screen with **"PREDICTA26"** in amber and purple letters, with a login form. That's your app. 🎉

**To stop the app:** click the terminal/command window that opened, press **Ctrl+C**

**To start it again any time:** just double-click the launcher again

---

## STEP 4 — GET YOUR 35 USERS SIGNED UP

For local testing, your link is: **http://localhost:5173**

Each person clicks **"REGISTER"**, picks a username, enters email + password, and automatically gets **1,000 TOK** to start trading with.

To let everyone access it from their own devices at the same time, see the Deployment section at the bottom.

---

## STEP 5 — CONNECT YOUR TEAMMATE'S PYTHON MODEL

Your teammate's Monte Carlo simulation can push probabilities directly into the database.

**Give them this:**

```bash
pip install supabase
```

```python
from supabase import create_client

# Use the Service Role key — NOT the anon key
# Find it: Supabase → Project Settings → API → "service_role" key
supabase = create_client("YOUR_SUPABASE_URL", "YOUR_SERVICE_ROLE_KEY")

# Update a match's model probabilities after each simulation
supabase.table("matches").update({
    "model_prob_a": 0.72,
    "model_prob_b": 0.28
}).eq("id", "PASTE_MATCH_UUID_HERE").execute()

# Mark a match as live when it kicks off
supabase.table("matches").update({
    "status": "live"
}).eq("id", "PASTE_MATCH_UUID_HERE").execute()

# Lock trading 5 minutes before kickoff
supabase.table("matches").update({
    "status": "locked"
}).eq("id", "PASTE_MATCH_UUID_HERE").execute()
```

**To find match UUIDs:**
Supabase dashboard → left sidebar → **Table Editor** → click **"matches"** → copy any value in the `id` column

**⚠️ The Service Role key is powerful — only your teammate uses it in their Python script, never paste it into VS Code or your .env file**

---

## STEP 6 — SETTLE MATCHES AFTER THEY FINISH

After a match ends, go to Supabase → SQL Editor → open a new tab → paste and run:

```sql
-- Team A wins:
SELECT settle_match('PASTE_MATCH_UUID_HERE', 'team_a');

-- Team B wins:
SELECT settle_match('PASTE_MATCH_UUID_HERE', 'team_b');

-- Draw — refunds everyone their original capital:
SELECT settle_match('PASTE_MATCH_UUID_HERE', 'DRAW');
```

This automatically pays all winners 100 TOK per share, handles draws with full refunds, and logs everything.

---

## DEPLOYING — So everyone can access it (not just your computer)

Right now the app only runs on your computer. To share it with all 35 users:

1. Create a free account at **https://vercel.com** — sign in with GitHub
2. Put your project on GitHub:
   - Create a GitHub account at **https://github.com** if you don't have one
   - In VS Code, press **Ctrl+Shift+P** (or Cmd+Shift+P) → type **"Publish to GitHub"** → press Enter
   - Follow the prompts — choose "Private repository"
   - Click "Publish to GitHub" when asked
3. Go to **https://vercel.com** → click **"Add New Project"** → select your GitHub repo
4. Before clicking Deploy, scroll down to **"Environment Variables"** and add both:
   - `VITE_SUPABASE_URL` = your Supabase URL
   - `VITE_SUPABASE_ANON_KEY` = your Supabase anon key
5. Click **"Deploy"**
6. Vercel gives you a link like `https://predicta26.vercel.app` — share this with your group

---

## TROUBLESHOOTING

**The launcher says "Node.js is not installed":**
The launcher opens the download page automatically. Install Node.js from https://nodejs.org (download the LTS version), then double-click the launcher again.

**Browser opens but shows a blank white page:**
In VS Code, check that your `.env` file exists, is named exactly `.env`, and has real Supabase values (not the placeholder text). Save it and double-click the launcher again.

**Launcher closes immediately:**
On Windows: right-click `START_WINDOWS.bat` → "Run as administrator". On Mac: right-click → Open.

**Users can't sign up:**
Supabase → Authentication → Providers → Email → make sure "Confirm email" is toggled OFF.

**Trades return errors:**
In Supabase SQL Editor run `SELECT * FROM matches LIMIT 5;` — if you see nothing, re-run `03_seed.sql`.

---

## QUICK REFERENCE

| Task | How |
|------|-----|
| Start the app | Double-click `START_MAC.command` or `START_WINDOWS.bat` |
| Stop the app | Click the terminal window → press Ctrl+C |
| Restart the app | Double-click the launcher again |
| Edit any file | Open VS Code → File → Open Folder → worldcup-predict |
| Settle a match | Supabase SQL Editor → `SELECT settle_match('uuid', 'team_a');` |
| View all trades | Supabase → Table Editor → ledger |
| View all positions | Supabase → Table Editor → positions |
| View all users | Supabase → Table Editor → users |

---

*PREDICTA26 — Built for 35 power users. FIFA World Cup 2026.*
