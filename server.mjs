import 'dotenv/config';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getHealth,
  getLatestModelSnapshot,
  getUserWithPick,
  loginUser,
  publishModelSnapshot,
  savePick,
  settleWinner,
} from './lib/predicta-api.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 5173);
const isProduction = process.env.NODE_ENV === 'production';

const app = express();
app.use(express.json());

function sendApiResult(response, result) {
  response.status(result.status).json(result.body);
}

app.get('/api/health', async (_request, response, next) => {
  try {
    response.json(await getHealth());
  } catch (error) {
    next(error);
  }
});

app.post('/api/login', async (request, response, next) => {
  try {
    sendApiResult(response, await loginUser(request.body));
  } catch (error) {
    next(error);
  }
});

app.get('/api/users/:id', async (request, response, next) => {
  try {
    const user = await getUserWithPick(request.params.id);

    if (!user) {
      response.status(404).json({ error: 'User not found.' });
      return;
    }

    response.json({ user });
  } catch (error) {
    next(error);
  }
});

app.post('/api/picks', async (request, response, next) => {
  try {
    sendApiResult(response, await savePick(request.body));
  } catch (error) {
    next(error);
  }
});

app.get('/api/model/latest', async (_request, response, next) => {
  try {
    sendApiResult(response, await getLatestModelSnapshot());
  } catch (error) {
    next(error);
  }
});

app.post('/api/model/snapshot', async (request, response, next) => {
  try {
    sendApiResult(response, await publishModelSnapshot(request.body));
  } catch (error) {
    next(error);
  }
});

app.post('/api/settle-winner', async (request, response, next) => {
  try {
    sendApiResult(response, await settleWinner(request.body));
  } catch (error) {
    next(error);
  }
});

app.use((error, _request, response, _next) => {
  console.error(error);
  response.status(500).json({ error: error.message || 'Server error.' });
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
