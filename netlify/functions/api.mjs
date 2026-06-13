import {
  getHealth,
  getUserWithPick,
  loginUser,
  savePick,
  settleWinner,
} from '../../lib/predicta-api.mjs';

function json(statusCode, body) {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  };
}

function parseBody(event) {
  if (!event.body) return {};

  try {
    return JSON.parse(event.body);
  } catch {
    return {};
  }
}

function getApiPath(event) {
  const pathname = new URL(event.rawUrl || `https://local.test${event.path}`).pathname;

  return pathname
    .replace(/^\/\.netlify\/functions\/api/, '')
    .replace(/^\/api/, '') || '/health';
}

export async function handler(event) {
  try {
    const method = event.httpMethod.toUpperCase();
    const apiPath = getApiPath(event);
    const body = parseBody(event);

    if (method === 'GET' && apiPath === '/health') {
      return json(200, await getHealth());
    }

    if (method === 'POST' && apiPath === '/login') {
      const result = await loginUser(body);
      return json(result.status, result.body);
    }

    if (method === 'POST' && apiPath === '/picks') {
      const result = await savePick(body);
      return json(result.status, result.body);
    }

    if (method === 'POST' && apiPath === '/settle-winner') {
      const result = await settleWinner(body);
      return json(result.status, result.body);
    }

    const userMatch = apiPath.match(/^\/users\/([^/]+)$/);

    if (method === 'GET' && userMatch) {
      const user = await getUserWithPick(userMatch[1]);

      if (!user) {
        return json(404, { error: 'User not found.' });
      }

      return json(200, { user });
    }

    return json(404, { error: 'API route not found.' });
  } catch (error) {
    return json(500, { error: error.message || 'Server error.' });
  }
}
