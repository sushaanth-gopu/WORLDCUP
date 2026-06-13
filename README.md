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

## Stored Data

- `users`: display name, email, total points
- `winner_picks`: each user's active winning-team pick and projected payout
- `points_ledger`: point awards after settlement

## Settle The Winner

When the World Cup winner is known, call:

```bash
curl -X POST http://localhost:5173/api/settle-winner \
  -H "Content-Type: application/json" \
  -d "{\"teamName\":\"Argentina\",\"adminCode\":\"choose-a-private-admin-code\"}"
```

The server awards each correct pick its stored projected points and marks all open picks
as settled.
