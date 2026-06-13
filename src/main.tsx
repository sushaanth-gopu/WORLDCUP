import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Team = {
  name: string;
  region: string;
  chance: number;
  rating: number;
  form: string;
};

type User = {
  id: string;
  displayName: string;
  email: string;
  pointsTotal: number;
  pick: {
    teamName: string;
    winProbability: number;
    projectedPoints: number;
  } | null;
};

const teams: Team[] = [
  { name: 'Argentina', region: 'CONMEBOL', chance: 18, rating: 94, form: 'Elite attack' },
  { name: 'France', region: 'UEFA', chance: 17, rating: 93, form: 'Deep squad' },
  { name: 'Brazil', region: 'CONMEBOL', chance: 14, rating: 91, form: 'High ceiling' },
  { name: 'England', region: 'UEFA', chance: 12, rating: 89, form: 'Balanced core' },
  { name: 'Spain', region: 'UEFA', chance: 9, rating: 86, form: 'Possession edge' },
  { name: 'Portugal', region: 'UEFA', chance: 8, rating: 85, form: 'Clinical finishers' },
  { name: 'Netherlands', region: 'UEFA', chance: 6, rating: 82, form: 'Compact shape' },
  { name: 'Germany', region: 'UEFA', chance: 5, rating: 80, form: 'Tournament DNA' },
  { name: 'Uruguay', region: 'CONMEBOL', chance: 4, rating: 77, form: 'Pressing power' },
  { name: 'USA', region: 'CONCACAF', chance: 3, rating: 72, form: 'Home lift' },
  { name: 'Mexico', region: 'CONCACAF', chance: 2, rating: 68, form: 'Crowd energy' },
  { name: 'Japan', region: 'AFC', chance: 2, rating: 67, form: 'Upset threat' },
];

function calculatePayout(chance: number) {
  return Math.round((100 / chance) * 10);
}

async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error || 'Something went wrong.');
  }

  return payload;
}

function App() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [user, setUser] = useState<User | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<Team>(teams[0]);
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState('');

  const sortedTeams = useMemo(() => [...teams].sort((a, b) => b.chance - a.chance), []);
  const projectedPoints = calculatePayout(selectedTeam.chance);

  useEffect(() => {
    const savedUserId = window.localStorage.getItem('predicta26_user_id');

    if (!savedUserId) return;

    apiRequest<{ user: User }>(`/api/users/${savedUserId}`)
      .then(({ user: restoredUser }) => {
        setUser(restoredUser);
        setName(restoredUser.displayName);
        setEmail(restoredUser.email);

        if (restoredUser.pick) {
          const team = teams.find((item) => item.name === restoredUser.pick?.teamName);
          if (team) setSelectedTeam(team);
        }
      })
      .catch(() => window.localStorage.removeItem('predicta26_user_id'));
  }, []);

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !email.trim()) return;

    setIsBusy(true);
    setMessage('');

    try {
      const { user: loggedInUser } = await apiRequest<{ user: User }>('/api/login', {
        method: 'POST',
        body: JSON.stringify({ displayName: name, email }),
      });

      setUser(loggedInUser);
      window.localStorage.setItem('predicta26_user_id', loggedInUser.id);

      if (loggedInUser.pick) {
        const team = teams.find((item) => item.name === loggedInUser.pick?.teamName);
        if (team) setSelectedTeam(team);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Login failed.');
    } finally {
      setIsBusy(false);
    }
  }

  async function handlePick(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) return;

    setIsBusy(true);
    setMessage('');

    try {
      const { user: updatedUser } = await apiRequest<{ user: User }>('/api/picks', {
        method: 'POST',
        body: JSON.stringify({ userId: user.id, teamName: selectedTeam.name }),
      });

      setUser(updatedUser);
      setMessage(
        `Pick saved: ${selectedTeam.name} for ${calculatePayout(selectedTeam.chance)} points.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save pick.');
    } finally {
      setIsBusy(false);
    }
  }

  if (!user) {
    return (
      <main className="login-screen">
        <section className="login-panel" aria-labelledby="login-title">
          <p className="eyebrow">Private World Cup 2026 Pool</p>
          <h1 id="login-title">Predict the winner. Beat the market.</h1>
          <p className="intro">
            Favorites pay fewer points. Long shots pay more. Sign in to lock a team and see
            the reward before the tournament starts.
          </p>

          <form className="login-form" onSubmit={handleLogin}>
            <label>
              Display name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Alex Morgan"
                autoComplete="name"
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </label>
            <button className="primary-button" type="submit" disabled={isBusy}>
              {isBusy ? 'Entering...' : 'Enter Pool'}
            </button>
            {message && <p className="form-message">{message}</p>}
          </form>
        </section>
      </main>
    );
  }

  return (
    <>
      <header className="app-header">
        <div>
          <p className="eyebrow">PREDICTA26</p>
          <h1>Winner Pick Market</h1>
        </div>
        <div className="profile-badge">{user.displayName}</div>
      </header>

      <main className="dashboard">
        <section className="summary-grid" aria-label="Pool summary">
          <article>
            <span>Favorite</span>
            <strong>Argentina</strong>
          </article>
          <article>
            <span>Highest Return</span>
            <strong>Japan / Mexico</strong>
          </article>
          <article>
            <span>Your Pick</span>
            <strong>{user.pick ? user.pick.teamName : 'Not saved'}</strong>
          </article>
          <article>
            <span>Total Points</span>
            <strong>{user.pointsTotal}</strong>
          </article>
        </section>

        <section className="pick-layout">
          <form className="pick-panel" onSubmit={handlePick}>
            <div>
              <p className="eyebrow">Choose Champion</p>
              <h2>{selectedTeam.name}</h2>
              <p className="intro">
                {selectedTeam.chance}% win probability. If they win, this pick returns{' '}
                <strong>{projectedPoints} points</strong>.
              </p>
            </div>

            <label>
              Winning team
              <select
                value={selectedTeam.name}
                onChange={(event) => {
                  const team = teams.find((item) => item.name === event.target.value);
                  if (team) setSelectedTeam(team);
                }}
              >
                {sortedTeams.map((team) => (
                  <option key={team.name} value={team.name}>
                    {team.name} - {team.chance}% chance - {calculatePayout(team.chance)} pts
                  </option>
                ))}
              </select>
            </label>

            <div className="payout-card">
              <span>Potential Return</span>
              <strong>{projectedPoints}</strong>
              <small>points if {selectedTeam.name} wins</small>
            </div>

            <button className="primary-button" type="submit" disabled={isBusy}>
              {isBusy ? 'Saving...' : 'Save Pick'}
            </button>

            {message && <p className="saved-message">{message}</p>}
            {user.pick && !message && (
              <p className="saved-message">
                Current database pick: {user.pick.teamName} for {user.pick.projectedPoints} points.
              </p>
            )}
          </form>

          <section className="team-board" aria-label="Team odds board">
            {sortedTeams.map((team) => (
              <button
                className={`team-row ${selectedTeam.name === team.name ? 'active' : ''}`}
                key={team.name}
                onClick={() => setSelectedTeam(team)}
                type="button"
              >
                <span>
                  <strong>{team.name}</strong>
                  <small>{team.region} · {team.form}</small>
                </span>
                <span className="odds">
                  {team.chance}%
                  <small>{calculatePayout(team.chance)} pts</small>
                </span>
              </button>
            ))}
          </section>
        </section>
      </main>
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
