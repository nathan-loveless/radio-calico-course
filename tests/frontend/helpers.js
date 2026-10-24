import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const ROOT = fileURLToPath(new URL('../../public/', import.meta.url));
const HTML = readFileSync(ROOT + 'index.html', 'utf8').replace(/<script\b[^>]*><\/script>/g, '');
const PLAYER_JS = readFileSync(ROOT + 'player.js', 'utf8');

export const META_URL = 'https://d3d4yli4hf5bmh.cloudfront.net/metadatav2.json';
export const SONG = { artist: 'Artist', title: 'Title' };

export const flush = async () => {
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
};

export const reply = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
});

/**
 * Load index.html + player.js (unmodified) into a fresh jsdom window.
 *
 * `routes` maps "METHOD /path" (no query string) to a response, or to a function
 * (url, init) => response | Promise<response>. A route that throws simulates a network error.
 * Unrouted requests reject. Every call is recorded in `calls`.
 */
export async function loadPlayer(routes = {}) {
  const dom = new JSDOM(HTML, { url: 'http://localhost:8080/', runScripts: 'outside-only' });
  const { window } = dom;
  const calls = [];

  window.fetch = async (url, init = {}) => {
    const method = init.method || 'GET';
    const path = String(url).split('?')[0].replace('http://localhost:8080', '');
    calls.push({ method, url: String(url), path, body: init.body ? JSON.parse(init.body) : undefined, headers: init.headers });
    let route = routes[`${method} ${path}`];
    if (route === undefined && path === META_URL.split('?')[0]) route = routes[`GET ${META_URL}`];
    if (route === undefined) throw new Error(`unrouted ${method} ${path}`);
    return typeof route === 'function' ? route(String(url), init) : route;
  };
  window.setInterval = () => 0; // no 10 s metadata poll; tests trigger metadata themselves
  window.HTMLMediaElement.prototype.play = () => Promise.resolve();
  window.HTMLMediaElement.prototype.pause = () => {};
  window.HTMLMediaElement.prototype.load = () => {};
  window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  window.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };

  window.eval(PLAYER_JS);
  await flush();

  const $ = (id) => window.document.getElementById(id);
  return {
    window,
    calls,
    $,
    callsTo: (method, path) => calls.filter((c) => c.method === method && c.path === path),
    click: async (id) => { $(id).click(); await flush(); },
    submitAuth: async (user, pass) => {
      $('auth-user').value = user;
      $('auth-pass').value = pass;
      $('auth-form').dispatchEvent(new window.Event('submit', { cancelable: true, bubbles: true }));
      await flush();
    },
  };
}

/** Standard routes: metadata for SONG plus /api/me and ratings; override per test. */
export function baseRoutes(overrides = {}) {
  return {
    [`GET ${META_URL}`]: reply(200, { ...SONG }),
    'GET /api/me': reply(200, { user: null }),
    'GET /api/ratings': reply(200, { up: 0, down: 0, mine: null }),
    ...overrides,
  };
}
