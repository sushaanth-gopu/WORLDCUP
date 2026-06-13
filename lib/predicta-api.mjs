import { createClient } from '@libsql/client';
import { randomUUID } from 'node:crypto';

export const teams = [
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

const schema = [
  `CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    points_total INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS winner_picks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    win_probability INTEGER NOT NULL,
    projected_points INTEGER NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  )`,
  `CREATE UNIQUE INDEX IF NOT EXISTS winner_picks_one_active_per_user
    ON winner_picks(user_id)
    WHERE settled = 0`,
  `CREATE TABLE IF NOT EXISTS points_ledger (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    team_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  )`,
];

const db = createClient({
  url: process.env.TURSO_DATABASE_URL || 'file:predicta26.db',
  authToken: process.env.TURSO_AUTH_TOKEN,
});

let schemaPromise;

export function calculatePayout(chance) {
  return Math.round((100 / chance) * 10);
}

export function getTeam(teamName) {
  return teams.find((team) => team.name.toLowerCase() === String(teamName || '').toLowerCase());
}

function cleanEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function requireDatabaseConfig() {
  const isLocalFile = !process.env.TURSO_DATABASE_URL;

  if (process.env.NETLIFY && isLocalFile) {
    throw new Error('Missing TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in Netlify environment variables.');
  }
}

async function ensureSchema() {
  requireDatabaseConfig();
  schemaPromise ||= Promise.all(schema.map((statement) => db.execute(statement)));
  await schemaPromise;
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

export async function getHealth() {
  await ensureSchema();

  return {
    ok: true,
    database: process.env.TURSO_DATABASE_URL ? 'turso' : 'local-sqlite',
  };
}

export async function getUserWithPick(userId) {
  await ensureSchema();

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

  return result.rows[0] ? toUserPayload(result.rows[0]) : null;
}

export async function loginUser({ displayName, email }) {
  await ensureSchema();

  const cleanName = String(displayName || '').trim();
  const cleanUserEmail = cleanEmail(email);

  if (!cleanName || !cleanUserEmail || !cleanUserEmail.includes('@')) {
    return { status: 400, body: { error: 'Enter a display name and valid email.' } };
  }

  const existing = await db.execute({
    sql: 'SELECT id FROM users WHERE email = ? LIMIT 1',
    args: [cleanUserEmail],
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
      args: [cleanName, userId],
    });
  } else {
    await db.execute({
      sql: 'INSERT INTO users (id, display_name, email) VALUES (?, ?, ?)',
      args: [userId, cleanName, cleanUserEmail],
    });
  }

  return { status: 200, body: { user: await getUserWithPick(userId) } };
}

export async function savePick({ userId, teamName }) {
  await ensureSchema();

  const cleanUserId = String(userId || '').trim();
  const team = getTeam(teamName);

  if (!cleanUserId || !team) {
    return { status: 400, body: { error: 'Choose a valid team before saving.' } };
  }

  const user = await getUserWithPick(cleanUserId);

  if (!user) {
    return { status: 404, body: { error: 'Sign in again before saving a pick.' } };
  }

  await db.execute({
    sql: 'UPDATE winner_picks SET settled = 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND settled = 0',
    args: [cleanUserId],
  });

  await db.execute({
    sql: `
      INSERT INTO winner_picks
        (id, user_id, team_name, win_probability, projected_points)
      VALUES (?, ?, ?, ?, ?)
    `,
    args: [randomUUID(), cleanUserId, team.name, team.chance, calculatePayout(team.chance)],
  });

  return { status: 200, body: { user: await getUserWithPick(cleanUserId) } };
}

export async function settleWinner({ teamName, adminCode }) {
  await ensureSchema();

  const expectedAdminCode = process.env.ADMIN_SETTLE_CODE;

  if (expectedAdminCode && adminCode !== expectedAdminCode) {
    return { status: 403, body: { error: 'Admin code is incorrect.' } };
  }

  const team = getTeam(teamName);

  if (!team) {
    return { status: 400, body: { error: 'Choose a valid winning team.' } };
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

  return { status: 200, body: { winningTeam: team.name, settledPicks: winners.rows.length } };
}
