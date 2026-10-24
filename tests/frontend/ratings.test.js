import { describe, expect, it } from 'vitest';
import { SONG, META_URL, baseRoutes, flush, loadPlayer, reply } from './helpers.js';

const loggedIn = { user: { username: 'alice' } };

describe('loading ratings', () => {
  it('fetches ratings for the current song and renders counts', async () => {
    const p = await loadPlayer(baseRoutes({ 'GET /api/ratings': reply(200, { up: 3, down: 1, mine: null }) }));
    const [call] = p.callsTo('GET', '/api/ratings');
    expect(new URL(call.url, 'http://x').searchParams.get('artist')).toBe('Artist');
    expect(new URL(call.url, 'http://x').searchParams.get('title')).toBe('Title');
    expect(p.$('count-up').textContent).toBe('3');
    expect(p.$('count-down').textContent).toBe('1');
    expect(p.$('rate-up').disabled).toBe(false);
    expect(p.$('rate-down').disabled).toBe(false);
  });

  it('highlights the current user\'s rating and offers undo', async () => {
    const p = await loadPlayer(baseRoutes({
      'GET /api/me': reply(200, loggedIn),
      'GET /api/ratings': reply(200, { up: 1, down: 0, mine: 1 }),
    }));
    expect(p.$('rate-up').classList.contains('mine')).toBe(true);
    expect(p.$('rate-up').getAttribute('aria-pressed')).toBe('true');
    expect(p.$('rate-down').getAttribute('aria-pressed')).toBe('false');
    expect(p.$('rate-undo').hidden).toBe(false);
    expect(p.$('rate-msg').textContent).toContain('Thanks for rating');
  });

  it('asks anonymous listeners to log in', async () => {
    const p = await loadPlayer(baseRoutes());
    expect(p.$('rate-msg').textContent).toBe('Log in to rate this song.');
    expect(p.$('rate-undo').hidden).toBe(true);
  });

  it('does nothing without artist and title', async () => {
    const p = await loadPlayer(baseRoutes({ [`GET ${META_URL}`]: reply(200, { artist: 'Only Artist' }) }));
    expect(p.callsTo('GET', '/api/ratings')).toHaveLength(0);
    expect(p.$('rate-up').disabled).toBe(true);
    expect(p.$('rate-down').disabled).toBe(true);
  });

  it('shows a message when the ratings API fails', async () => {
    const p = await loadPlayer(baseRoutes({ 'GET /api/ratings': () => { throw new Error('offline'); } }));
    expect(p.$('rate-msg').textContent).toBe('Ratings unavailable');
  });

  it('leaves buttons disabled on a non-OK response', async () => {
    const p = await loadPlayer(baseRoutes({ 'GET /api/ratings': reply(500, {}) }));
    expect(p.$('rate-up').disabled).toBe(true);
  });

  it('ignores a slow response for a song that is no longer playing', async () => {
    let release;
    const slow = new Promise((r) => { release = r; });
    let n = 0;
    const p = await loadPlayer(baseRoutes({
      'GET /api/ratings': () => (++n === 1 ? slow : reply(200, { up: 9, down: 0, mine: null })),
    }));
    // First request is still pending; metadata changes to a new song.
    p.window.eval(`loadRatings({ artist: 'Other', title: 'Song' })`);
    await flush();
    expect(p.$('count-up').textContent).toBe('9');
    release(reply(200, { up: 1, down: 1, mine: null }));
    await flush();
    expect(p.$('count-up').textContent).toBe('9');
  });
});

describe('rating a song', () => {
  const setup = (extra = {}) => loadPlayer(baseRoutes({ 'GET /api/me': reply(200, loggedIn), ...extra }));

  it('opens the login dialog instead of posting when logged out', async () => {
    const p = await loadPlayer(baseRoutes());
    await p.click('rate-up');
    expect(p.$('auth-dialog').hasAttribute('open')).toBe(true);
    expect(p.callsTo('POST', '/api/ratings')).toHaveLength(0);
  });

  it('POSTs JSON with the song and value, then renders the response', async () => {
    const p = await setup({ 'POST /api/ratings': reply(200, { up: 1, down: 0, mine: 1 }) });
    await p.click('rate-up');
    const [call] = p.callsTo('POST', '/api/ratings');
    expect(call.body).toEqual({ ...SONG, value: 1 });
    expect(call.headers['Content-Type']).toBe('application/json');
    expect(p.$('count-up').textContent).toBe('1');
    expect(p.$('rate-up').classList.contains('mine')).toBe(true);
    expect(p.$('rate-undo').hidden).toBe(false);
  });

  it('sends -1 for thumbs down', async () => {
    const p = await setup({ 'POST /api/ratings': reply(200, { up: 0, down: 1, mine: -1 }) });
    await p.click('rate-down');
    expect(p.callsTo('POST', '/api/ratings')[0].body.value).toBe(-1);
    expect(p.$('rate-down').classList.contains('mine')).toBe(true);
  });

  it('does not re-send the rating you already have', async () => {
    const p = await setup({ 'GET /api/ratings': reply(200, { up: 1, down: 0, mine: 1 }) });
    await p.click('rate-up');
    expect(p.callsTo('POST', '/api/ratings')).toHaveLength(0);
  });

  it('resets to logged-out and opens login on 401', async () => {
    const p = await setup({ 'POST /api/ratings': reply(401, { error: 'Log in to rate songs' }) });
    expect(p.$('whoami').hidden).toBe(false);
    await p.click('rate-up');
    expect(p.$('whoami').hidden).toBe(true);
    expect(p.$('auth-open').hidden).toBe(false);
    expect(p.$('auth-dialog').hasAttribute('open')).toBe(true);
  });

  it('shows an error and re-enables buttons on failure', async () => {
    const p = await setup({ 'POST /api/ratings': reply(500, {}) });
    await p.click('rate-up');
    expect(p.$('rate-msg').textContent).toBe('Could not save your rating.');
    expect(p.$('rate-up').disabled).toBe(false);
  });

  it('shows an error on a network failure', async () => {
    const p = await setup({ 'POST /api/ratings': () => { throw new Error('offline'); } });
    await p.click('rate-down');
    expect(p.$('rate-msg').textContent).toBe('Could not save your rating.');
  });
});

describe('undoing a rating', () => {
  const rated = { 'GET /api/me': reply(200, loggedIn), 'GET /api/ratings': reply(200, { up: 1, down: 0, mine: 1 }) };

  it('sends DELETE with the song and re-renders', async () => {
    const p = await loadPlayer(baseRoutes({ ...rated, 'DELETE /api/ratings': reply(200, { up: 0, down: 0, mine: null }) }));
    await p.click('rate-undo');
    const [call] = p.callsTo('DELETE', '/api/ratings');
    expect(call.body).toEqual(SONG);
    expect(p.$('count-up').textContent).toBe('0');
    expect(p.$('rate-undo').hidden).toBe(true);
    expect(p.$('rate-up').classList.contains('mine')).toBe(false);
  });

  it('resets to logged-out and opens login on 401', async () => {
    const p = await loadPlayer(baseRoutes({ ...rated, 'DELETE /api/ratings': reply(401, {}) }));
    await p.click('rate-undo');
    expect(p.$('whoami').hidden).toBe(true);
    expect(p.$('auth-dialog').hasAttribute('open')).toBe(true);
  });

  it('shows an error on failure and re-enables the button', async () => {
    const p = await loadPlayer(baseRoutes({ ...rated, 'DELETE /api/ratings': reply(500, {}) }));
    await p.click('rate-undo');
    expect(p.$('rate-msg').textContent).toBe('Could not remove your rating.');
    expect(p.$('rate-undo').disabled).toBe(false);
  });
});
