import { describe, expect, it } from 'vitest';
import { baseRoutes, loadPlayer, reply } from './helpers.js';

const alice = { user: { username: 'alice' } };

describe('session state', () => {
  it('shows the signed-in UI when /api/me returns a user', async () => {
    const p = await loadPlayer(baseRoutes({ 'GET /api/me': reply(200, alice) }));
    expect(p.$('whoami').textContent).toBe('Signed in as alice');
    expect(p.$('logout').hidden).toBe(false);
    expect(p.$('auth-open').hidden).toBe(true);
  });

  it('shows the logged-out UI when /api/me fails', async () => {
    const p = await loadPlayer(baseRoutes({ 'GET /api/me': () => { throw new Error('offline'); } }));
    expect(p.$('whoami').hidden).toBe(true);
    expect(p.$('auth-open').hidden).toBe(false);
  });
});

describe('auth dialog', () => {
  it('opens in login mode and switches to register', async () => {
    const p = await loadPlayer(baseRoutes());
    await p.click('auth-open');
    expect(p.$('auth-h').textContent).toBe('Log in');
    await p.click('auth-switch');
    expect(p.$('auth-h').textContent).toBe('Register');
    expect(p.$('auth-pass').autocomplete).toBe('new-password');
  });

  it('logs in, closes the dialog, and refreshes ratings for the new user', async () => {
    let ratings = { up: 1, down: 0, mine: null };
    const p = await loadPlayer(baseRoutes({
      'POST /api/login': reply(200, alice),
      'GET /api/ratings': () => reply(200, ratings),
    }));
    await p.click('auth-open');
    ratings = { up: 1, down: 0, mine: 1 };
    await p.submitAuth('alice', 'correct-horse');
    expect(p.callsTo('POST', '/api/login')[0].body).toEqual({ username: 'alice', password: 'correct-horse' });
    expect(p.$('auth-dialog').hasAttribute('open')).toBe(false);
    expect(p.$('whoami').textContent).toBe('Signed in as alice');
    expect(p.$('rate-up').classList.contains('mine')).toBe(true);
    expect(p.$('auth-pass').value).toBe('');
  });

  it('registers via /api/register in register mode', async () => {
    const p = await loadPlayer(baseRoutes({ 'POST /api/register': reply(201, alice) }));
    await p.click('auth-open');
    await p.click('auth-switch');
    await p.submitAuth('alice', 'correct-horse');
    expect(p.callsTo('POST', '/api/register')).toHaveLength(1);
    expect(p.$('whoami').textContent).toBe('Signed in as alice');
  });

  it('shows the server error and keeps the dialog open on failure', async () => {
    const p = await loadPlayer(baseRoutes({ 'POST /api/login': reply(401, { error: 'Incorrect username or password' }) }));
    await p.click('auth-open');
    await p.submitAuth('alice', 'wrong-password');
    expect(p.$('auth-error').hidden).toBe(false);
    expect(p.$('auth-error').textContent).toBe('Incorrect username or password');
    expect(p.$('auth-dialog').hasAttribute('open')).toBe(true);
    expect(p.$('auth-submit').disabled).toBe(false);
  });

  it('cancel closes the dialog', async () => {
    const p = await loadPlayer(baseRoutes());
    await p.click('auth-open');
    await p.click('auth-cancel');
    expect(p.$('auth-dialog').hasAttribute('open')).toBe(false);
  });
});

describe('logout', () => {
  it('posts to /api/logout, resets the UI, and reloads ratings as anonymous', async () => {
    let me = alice;
    const p = await loadPlayer(baseRoutes({
      'GET /api/me': () => reply(200, me),
      'POST /api/logout': () => { me = { user: null }; return reply(200, { user: null }); },
      'GET /api/ratings': () => reply(200, { up: 1, down: 0, mine: me.user ? 1 : null }),
    }));
    expect(p.$('rate-up').classList.contains('mine')).toBe(true);
    await p.click('logout');
    expect(p.callsTo('POST', '/api/logout')).toHaveLength(1);
    expect(p.$('whoami').hidden).toBe(true);
    expect(p.$('auth-open').hidden).toBe(false);
    expect(p.$('rate-up').classList.contains('mine')).toBe(false);
    expect(p.$('rate-msg').textContent).toBe('Log in to rate this song.');
  });
});
