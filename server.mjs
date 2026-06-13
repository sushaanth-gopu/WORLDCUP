import 'dotenv/config';
import express from 'express';
import { createClient } from '@libsql/client';
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 5173);
const isProduction = process.env.NODE_ENV === 'production';

const teams = [
  { name: 'Argentina', chance: 18 },
  { name: 'France', chance: 17 },
  { name: 'Brazil', chance: 14 },
  { name: 'England', chance: 12 },
  { name: 'Spain', chance: 9 },
  { name: 'Portugal', chance: 8 },
  { name: 'Netherlands', chance: 6 },
  { name: 'Germany', chance: 5 },
  { name: 'Uruguay', chance: 4 },
  { name: 'USA', chance: 3 },
  { name: 'Mexico', chance: 2 },
  { name: 'Japan', chance: 2 },
];

const db = createClient({
  url: process.env.TURSO_DATABASE_URL || 'file:predicta26.db',
  authToken: process.env.TURSO_AUTH_TOKEN,
});

function calculatePayout(chance) {
  return Math.round((100 / chance) * 10);
}

function cleanEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function getTeam(teamName) {
  return teams.find((team) => team.name.toLowerCase() === String(teamName || '').toLowerCase());
}

async function runSchema() {
  const schema = readFileSync(path.join(__dirname, 'db', 'schema.sql'), 'utf8')
    .split(';')
    .map((statement) => statement.trim())
    .filter(Boolean);

  for (const statement of schema) {
    await db.execute(statement);
  }
}

async function getUserWithPick(userId) {
  const result = await db.execute({
    sql: `
      SELECT
        users.id,
        users.display_name,
        users.email,
        users.points_total,
        winner_picks.team_name,
        winner_picks.win_probability,
        winner_picks.projected_points
      FROM users
      LEFT JOIN winner_picks
        ON winner_picks.user_id = users.id
       AND winner_picks.settled = 0
      WHERE users.id = ?
      LIMIT 1
    `,
    args: [userId],
  });

  return result.rows[0] || null;
}

function toUserPayload(row) {
  return {
    id: row.id,
    displayName: row.display_name,
    email: row.email,
    pointsTotal: Number(row.points_total),
    pick: row.team_name
      ? {
          teamName: row.team_name,
          winProbability: Number(row.win_probability),
          projectedPoints: Number(row.projected_points),
        }
      : null,
  };
}

await runSchema();

const app = express();
app.use(express.json());

app.get('/api/health', (_request, response) => {
  response.json({
    ok: true,
    database: process.env.TURSO_DATABASE_URL ? 'turso' : 'local-sqlite',
  });
});

app.post('/api/login', async (request, response) => {
  const displayName = String(request.body.displayName || '').trim();
  const email = cleanEmail(request.body.email);

  if (!displayName || !email || !email.includes('@')) {
    response.status(400).json({ error: 'Enter a display name and valid email.' });
    return;
  }

  const existing = await db.execute({
    sql: 'SELECT id FROM users WHERE email = ? LIMIT 1',
    args: [email],
  });

  const userId = existing.rows[0]?.id || randomUUID();

  if (existing.rows.length) {
    await db.execute({
      sql: `
        UPDATE users
           SET display_name = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
      `,
      args: [displayName, userId],
    });
  } else {
    await db.execute({
      sql: 'INSERT INTO users (id, display_name, email) VALUES (?, ?, ?)',
      args: [userId, displayName, email],
    });
  }

  const user = await getUserWithPick(userId);
  response.json({ user: toUserPayload(user) });
});

app.get('/api/users/:id', async (request, response) => {
  const user = await getUserWithPick(request.params.id);

  if (!user) {
    response.status(404).json({ error: 'User not found.' });
    return;
  }

  response.json({ user: toUserPayload(user) });
});

app.post('/api/picks', async (request, response) => {
  const userId = String(request.body.userId || '').trim();
  const team = getTeam(request.body.teamName);

  if (!userId || !team) {
    response.status(400).json({ error: 'Choose a valid team before saving.' });
    return;
  }

  const user = await getUserWithPick(userId);

  if (!user) {
    response.status(404).json({ error: 'Sign in again before saving a pick.' });
    return;
  }

  await db.execute({
    sql: 'UPDATE winner_picks SET settled = 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND settled = 0',
    args: [userId],
  });

  await db.execute({
    sql: `
      INSERT INTO winner_picks
        (id, user_id, team_name, win_probability, projected_points)
      VALUES (?, ?, ?, ?, ?)
    `,
    args: [randomUUID(), userId, team.name, team.chance, calculatePayout(team.chance)],
  });

  const updatedUser = await getUserWithPick(userId);
  response.json({ user: toUserPayload(updatedUser) });
});

app.post('/api/settle-winner', async (request, response) => {
  const adminCode = process.env.ADMIN_SETTLE_CODE;

  if (adminCode && request.body.adminCode !== adminCode) {
    response.status(403).json({ error: 'Admin code is incorrect.' });
    return;
  }

  const team = getTeam(request.body.teamName);

  if (!team) {
    response.status(400).json({ error: 'Choose a valid winning team.' });
    return;
  }

  const winners = await db.execute({
    sql: 'SELECT id, user_id, projected_points FROM winner_picks WHERE settled = 0 AND team_name = ?',
    args: [team.name],
  });

  for (const winner of winners.rows) {
    await db.execute({
      sql: 'UPDATE users SET points_total = points_total + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
      args: [Number(winner.projected_points), winner.user_id],
    });
    await db.execute({
      sql: 'INSERT INTO points_ledger (id, user_id, amount, reason, team_name) VALUES (?, ?, ?, ?, ?)',
      args: [randomUUID(), winner.user_id, Number(winner.projected_points), 'winner_pick', team.name],
    });
  }

  await db.execute({
    sql: 'UPDATE winner_picks SET settled = 1, updated_at = CURRENT_TIMESTAMP WHERE settled = 0',
  });

  response.json({ winningTeam: team.name, settledPicks: winners.rows.length });
});

if (isProduction) {
  app.use(express.static(path.join(__dirname, 'dist')));
  app.get('*splat', (_request, response) => {
    response.sendFile(path.join(__dirname, 'dist', 'index.html'));
  });
} else {
  const { createServer } = await import('vite');
  const vite = await createServer({
    server: { middlewareMode: true },
    appType: 'spa',
  });

  app.use(vite.middlewares);
}

app.listen(port, () => {
  console.log(`PREDICTA26 is running at http://localhost:${port}`);
});
