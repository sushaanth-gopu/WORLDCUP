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
  `CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    simulations INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS model_team_probabilities (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    win_probability REAL NOT NULL,
    final_probability REAL,
    semi_probability REAL,
    rating REAL,
    projected_points INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES model_runs(id) ON DELETE CASCADE
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

export async function getLatestModelSnapshot() {
  await ensureSchema();

  const latestRun = await db.execute({
    sql: 'SELECT id, source, simulations, created_at FROM model_runs ORDER BY created_at DESC LIMIT 1',
  });

  if (!latestRun.rows.length) {
    return {
      status: 200,
      body: {
        snapshot: null,
        teams: teams.map((team) => ({
          teamName: team.name,
          winProbability: team.chance,
          projectedPoints: calculatePayout(team.chance),
        })),
      },
    };
  }

  const run = latestRun.rows[0];
  const probabilities = await db.execute({
    sql: `
      SELECT
        team_name,
        win_probability,
        final_probability,
        semi_probability,
        rating,
        projected_points
      FROM model_team_probabilities
      WHERE run_id = ?
      ORDER BY win_probability DESC
    `,
    args: [run.id],
  });

  return {
    status: 200,
    body: {
      snapshot: {
        id: run.id,
        source: run.source,
        simulations: run.simulations === null ? null : Number(run.simulations),
        createdAt: run.created_at,
      },
      teams: probabilities.rows.map((row) => ({
        teamName: row.team_name,
        winProbability: Number(row.win_probability),
        finalProbability: row.final_probability === null ? null : Number(row.final_probability),
        semiProbability: row.semi_probability === null ? null : Number(row.semi_probability),
        rating: row.rating === null ? null : Number(row.rating),
        projectedPoints: Number(row.projected_points),
      })),
    },
  };
}

export async function publishModelSnapshot({ adminCode, source, simulations, teams: incomingTeams }) {
  await ensureSchema();

  const expectedAdminCode = process.env.ADMIN_MODEL_CODE || process.env.ADMIN_SETTLE_CODE;

  if (expectedAdminCode && adminCode !== expectedAdminCode) {
    return { status: 403, body: { error: 'Model admin code is incorrect.' } };
  }

  if (!Array.isArray(incomingTeams) || incomingTeams.length === 0) {
    return { status: 400, body: { error: 'Send at least one team probability.' } };
  }

  const runId = randomUUID();

  await db.execute({
    sql: 'INSERT INTO model_runs (id, source, simulations) VALUES (?, ?, ?)',
    args: [runId, String(source || 'model'), Number(simulations) || null],
  });

  let savedTeams = 0;

  for (const item of incomingTeams) {
    const teamName = String(item.teamName || item.team || item.name || '').trim();
    const rawWinProbability = Number(
      item.winProbability ?? item.win_prob ?? item.winPct ?? item.win_pct,
    );

    if (!teamName || !Number.isFinite(rawWinProbability)) continue;

    const winProbability = rawWinProbability <= 1 ? rawWinProbability * 100 : rawWinProbability;
    const boundedWinProbability = Math.max(0.1, Math.min(99.9, winProbability));
    const projectedPoints = calculatePayout(Math.max(1, boundedWinProbability));

    await db.execute({
      sql: `
        INSERT INTO model_team_probabilities
          (
            id,
            run_id,
            team_name,
            win_probability,
            final_probability,
            semi_probability,
            rating,
            projected_points
          )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `,
      args: [
        randomUUID(),
        runId,
        teamName,
        boundedWinProbability,
        item.finalProbability ?? item.final_prob ?? item.finalPct ?? item.final_pct ?? null,
        item.semiProbability ?? item.semi_prob ?? item.semiPct ?? item.semi_pct ?? null,
        item.rating ?? item.elo ?? null,
        projectedPoints,
      ],
    });

    savedTeams += 1;
  }

  if (!savedTeams) {
    return { status: 400, body: { error: 'No valid team probabilities were found.' } };
  }

  return {
    status: 200,
    body: {
      snapshot: {
        id: runId,
        source: source || 'model',
        simulations: Number(simulations) || null,
      },
      teamsSaved: savedTeams,
    },
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
