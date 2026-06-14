import 'dotenv/config';
import express   from 'express';
import path      from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getHealth,
  getLatestModelSnapshot,
  getUserWithPick,
  initSchema,
  loginUser,
  publishModelSnapshot,
  registerUser,
  savePick,
  settleWinner,
} from './lib/predicta-api.mjs';

const __dirname  = path.dirname(fileURLToPath(import.meta.url));
const port       = Number(process.env.PORT || 5173);
const isProduction = process.env.NODE_ENV === 'production';

const app = express();
app.use(express.json());

function send(response, result) {
  response.status(result.status).json(result.body);
}

// ── Routes ────────────────────────────────────────────────────────────────────

app.get('/api/health', async (_req, res, next) => {
  try { res.json(await getHealth()); } catch (e) { next(e); }
});

app.post('/api/register', async (req, res, next) => {
  try { send(res, await registerUser(req.body)); } catch (e) { next(e); }
});

app.post('/api/login', async (req, res, next) => {
  try { send(res, await loginUser(req.body)); } catch (e) { next(e); }
});

app.get('/api/users/:id', async (req, res, next) => {
  try {
    const user = await getUserWithPick(req.params.id);
    if (!user) { res.status(404).json({ error: 'User not found.' }); return; }
    res.json({ user });
  } catch (e) { next(e); }
});

app.post('/api/picks', async (req, res, next) => {
  try { send(res, await savePick(req.body)); } catch (e) { next(e); }
});

app.get('/api/model/latest', async (_req, res, next) => {
  try { send(res, await getLatestModelSnapshot()); } catch (e) { next(e); }
});

app.post('/api/model/snapshot', async (req, res, next) => {
  try { send(res, await publishModelSnapshot(req.body)); } catch (e) { next(e); }
});

app.post('/api/settle-winner', async (req, res, next) => {
  try { send(res, await settleWinner(req.body)); } catch (e) { next(e); }
});

// ── Error handler ─────────────────────────────────────────────────────────────

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: err.message || 'Server error.' });
});

// ── Static / Vite ─────────────────────────────────────────────────────────────

if (isProduction) {
  app.use(express.static(path.join(__dirname, 'dist')));
  app.get('*splat', (_req, res) => {
    res.sendFile(path.join(__dirname, 'dist', 'index.html'));
  });
} else {
  const { createServer } = await import('vite');
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'spa' });
  app.use(vite.middlewares);
}

// ── Boot ──────────────────────────────────────────────────────────────────────

await initSchema();
console.log('✓ Database schema ready');

app.listen(port, () => {
  console.log(`PREDICTA26 running at http://localhost:${port}`);
});
