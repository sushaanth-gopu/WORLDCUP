# PREDICTA26

World Cup 2026 winner pool with database-backed login, team picks, and weighted points.

Favorites return fewer points. Underdogs return more points. User accounts, saved picks,
and awarded points are stored in Turso.

## Setup

1. Create a Turso database.
2. Copy `.env.example` to `.env`.
3. Fill in:

```bash
TURSO_DATABASE_URL=libsql://your-database-name-your-org.turso.io
TURSO_AUTH_TOKEN=your_turso_auth_token
ADMIN_SETTLE_CODE=choose-a-private-admin-code
```

4. Install and run:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

The server creates the needed tables automatically from `db/schema.sql`.

## Host On Netlify

1. Push this project to GitHub.
2. In Netlify, choose **Add new site** then **Import an existing project**.
3. Connect the GitHub repo.
4. Use these settings:

```bash
Build command: npm run build
Publish directory: dist
Functions directory: netlify/functions
```

5. Add these Netlify environment variables:

```bash
TURSO_DATABASE_URL=libsql://your-database-name-your-org.turso.io
TURSO_AUTH_TOKEN=your_turso_auth_token
ADMIN_SETTLE_CODE=choose-a-private-admin-code
ADMIN_MODEL_CODE=choose-a-private-model-code
```

6. Deploy.

The `netlify.toml` file already routes `/api/*` to the Netlify Function and all other
browser routes to the Vite app.

## Stored Data

- `users`: display name, email, total points
- `winner_picks`: each user's active winning-team pick and projected payout
- `points_ledger`: point awards after settlement
- `model_runs`: every published model snapshot
- `model_team_probabilities`: live win probabilities and payouts from the model

## Model API

The Python model should pull live match data itself, run the simulation, then publish
the latest probabilities to the hosted app:

```bash
PREDICTA_API_BASE_URL=https://your-site-name.netlify.app \
ADMIN_MODEL_CODE=choose-a-private-model-code \
MODEL_SIMULATIONS=20000 \
python model/publish_snapshot.py
```

The frontend reads:

```bash
GET /api/model/latest
```

The model publishes:

```bash
POST /api/model/snapshot
```

Example payload:

```json
{
  "adminCode": "choose-a-private-model-code",
  "source": "python-model",
  "simulations": 20000,
  "teams": [
    {
      "teamName": "France",
      "winProbability": 17.4,
      "finalProbability": 29.1,
      "semiProbability": 44.8,
      "rating": 1842.5
    }
  ]
}
```

## Settle The Winner

When the World Cup winner is known, call:

```bash
curl -X POST https://your-site-name.netlify.app/api/settle-winner \
  -H "Content-Type: application/json" \
  -d "{\"teamName\":\"Argentina\",\"adminCode\":\"choose-a-private-admin-code\"}"
```

The server awards each correct pick its stored projected points and marks all open picks
as settled.
