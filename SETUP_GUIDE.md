# PREDICTA26 Turso Setup Guide

## 1. Create The Database

1. Go to `https://turso.tech`.
2. Create an account or sign in.
3. Create a new database named `predicta26`.
4. Copy the database URL. It looks like:

```bash
libsql://predicta26-your-org.turso.io
```

5. Create an auth token for the database and copy it.

## 2. Add Your App Settings

1. In this project folder, copy `.env.example`.
2. Rename the copy to `.env`.
3. Fill it in like this:

```bash
TURSO_DATABASE_URL=libsql://predicta26-your-org.turso.io
TURSO_AUTH_TOKEN=your_turso_auth_token
ADMIN_SETTLE_CODE=choose-a-private-admin-code
```

Keep `TURSO_AUTH_TOKEN` private. It belongs on the server only, not in browser code.

## 3. Start The App

Install packages:

```bash
npm install
```

Run the app:

```bash
npm run dev
```

Open:

```bash
http://localhost:5173
```

The server creates the Turso tables automatically from `db/schema.sql`.

## 4. What Gets Stored

The app stores:

- user display name and email
- total points
- active winner pick
- that pick's win probability and projected points
- point ledger entries after the winner is settled

## 5. Award Points After The Final

When the World Cup winner is known, run this with the winning team:

```bash
curl -X POST http://localhost:5173/api/settle-winner \
  -H "Content-Type: application/json" \
  -d "{\"teamName\":\"Argentina\",\"adminCode\":\"choose-a-private-admin-code\"}"
```

Every correct user gets the projected points from their saved pick.

## 6. Host On Netlify

1. Put this project on GitHub.
2. Go to `https://netlify.com`.
3. Choose **Add new site**.
4. Choose **Import an existing project**.
5. Pick your GitHub repository.
6. Netlify should read `netlify.toml` automatically. If it asks, use:

```bash
Build command: npm run build
Publish directory: dist
Functions directory: netlify/functions
```

7. Before deploying, add these environment variables in Netlify:

```bash
TURSO_DATABASE_URL=libsql://predicta26-your-org.turso.io
TURSO_AUTH_TOKEN=your_turso_auth_token
ADMIN_SETTLE_CODE=choose-a-private-admin-code
```

8. Click **Deploy**.

Your hosted API will use the same routes as local development:

```bash
https://your-site-name.netlify.app/api/login
https://your-site-name.netlify.app/api/picks
https://your-site-name.netlify.app/api/settle-winner
```
