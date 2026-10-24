const STREAM_URL = 'https://d3d4yli4hf5bmh.cloudfront.net/hls/live.m3u8';

const $ = (id) => document.getElementById(id);
const audio = $('audio');
const playBtn = $('play');
let hls = null;
let attached = false;

function setState(text) { $('state').textContent = text; }

function showError(msg) {
  $('error').textContent = msg;
  $('error').hidden = !msg;
}

function render(playing) {
  $('icon-play').hidden = playing;
  $('icon-pause').hidden = !playing;
  playBtn.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  $('live').classList.toggle('on', playing);
}

// Attach the stream lazily on first play so we don't hit the CDN until asked.
function attach() {
  if (attached) return Promise.resolve();
  attached = true;

  if (window.Hls && Hls.isSupported()) {
    hls = new Hls({ lowLatencyMode: true });
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (!data.fatal) return;
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        setState('Reconnecting…');
        hls.startLoad();
      } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        hls.recoverMediaError();
      } else {
        showError('The stream failed to load.');
        hls.destroy();
        attached = false;
        render(false);
        setState('Error');
      }
    });
    hls.on(Hls.Events.LEVEL_SWITCHED, (_e, d) => {
      const lvl = hls.levels[d.level] || {};
      const codec = `${lvl.audioCodec || ''} ${(lvl.attrs && lvl.attrs.CODECS) || ''}`.toLowerCase();
      $('stream-quality').textContent = codec.includes('flac') ? 'Stream quality: FLAC / HLS Lossless' : 'Stream quality: AAC / HLS';
    });
    hls.loadSource(STREAM_URL);
    hls.attachMedia(audio);
    return Promise.resolve();
  }

  if (audio.canPlayType('application/vnd.apple.mpegurl')) { // Safari / iOS
    audio.src = STREAM_URL;
    return Promise.resolve();
  }

  attached = false;
  return Promise.reject(new Error('HLS is not supported in this browser.'));
}

playBtn.onclick = async () => {
  showError('');
  if (!audio.paused) return audio.pause();
  playBtn.disabled = true;
  setState('Connecting…');
  try {
    await attach();
    await audio.play();
  } catch (err) {
    showError(err.message || 'Playback could not start.');
    setState('Stopped');
  } finally {
    playBtn.disabled = false;
  }
};

const setVolume = (v) => {
  audio.volume = v;
  $('vol').style.setProperty('--fill', `${v * 100}%`);
};
$('vol').oninput = (e) => setVolume(e.target.value);

audio.onplaying = () => { render(true); setState('Playing'); };
audio.onpause = () => { render(false); setState('Paused'); };
audio.onwaiting = () => { if (!audio.paused) setState('Buffering…'); };

const pad = (n) => String(n).padStart(2, '0');
function fmt(s) {
  s = Math.floor(s) || 0;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
audio.ontimeupdate = () => ($('elapsed').textContent = `${fmt(audio.currentTime)} / Live`);

const COVER_URL = 'https://d3d4yli4hf5bmh.cloudfront.net/cover.jpg';
const META_URL = 'https://d3d4yli4hf5bmh.cloudfront.net/metadatav2.json';
let lastMeta = '';

function renderMeta(m) {
  $('np-title').textContent = (m.title || 'Unknown title') + (m.date ? ` (${m.date})` : '');
  $('np-artist').textContent = m.artist || '';
  $('np-album').textContent = (m.album || '').trim();
  $('np-new').hidden = !m.is_new;
  const cover = $('np-cover');
  cover.alt = [m.album && m.album.trim(), m.artist].filter(Boolean).join(' – ') + ' cover art';
  cover.onload = () => (cover.hidden = false);
  cover.onerror = () => (cover.hidden = true);
  cover.src = `${COVER_URL}?t=${Date.now()}`;
  if (m.bit_depth && m.sample_rate) {
    $('quality').textContent = `Source quality: ${m.bit_depth}-bit / ${m.sample_rate / 1000} kHz`;
  }
  const items = [];
  for (let n = 1; n <= 5; n++) {
    if (!m[`prev_title_${n}`]) continue;
    const li = document.createElement('li');
    li.innerHTML = '<span class="a"></span><span class="t"></span>';
    li.children[0].textContent = m[`prev_artist_${n}`] || '';
    li.children[1].textContent = m[`prev_title_${n}`];
    items.push(li);
  }
  $('rp-list').replaceChildren(...items);
}

async function pollMeta() {
  try {
    const res = await fetch(META_URL, { cache: 'no-store' });
    const text = await res.text();
    if (text !== lastMeta) {
      lastMeta = text;
      const m = JSON.parse(text);
      renderMeta(m);
      loadRatings(m);
    }
  } catch {
    if (!lastMeta) $('np-title').textContent = 'Track info unavailable';
  }
}
pollMeta();
setInterval(pollMeta, 10000);

// --- Ratings -------------------------------------------------------------
const RATINGS_API = '/api/ratings';
let currentSong = null;
let lastRatings = null;
let user = null; // { username } when logged in

function renderRatings(r) {
  lastRatings = r;
  $('count-up').textContent = r.up;
  $('count-down').textContent = r.down;
  const rated = r.mine === 1 || r.mine === -1;
  $('rate-up').classList.toggle('mine', r.mine === 1);
  $('rate-down').classList.toggle('mine', r.mine === -1);
  $('rate-up').disabled = $('rate-down').disabled = false;
  $('rate-up').setAttribute('aria-pressed', r.mine === 1);
  $('rate-down').setAttribute('aria-pressed', r.mine === -1);
  $('rate-undo').hidden = !rated;
  $('rate-msg').textContent = rated ? 'Thanks for rating! You can change it anytime.' : '';
  if (!user && !rated) {
    $('rate-msg').textContent = 'Log in to rate this song.';
  }
}

async function loadRatings(m) {
  currentSong = m.artist && m.title ? { artist: m.artist, title: m.title } : null;
  $('rate-up').disabled = $('rate-down').disabled = true;
  if (!currentSong) return;
  const song = currentSong;
  try {
    const res = await fetch(`${RATINGS_API}?${new URLSearchParams(song)}`);
    if (!res.ok || song !== currentSong) return;
    renderRatings(await res.json());
  } catch {
    $('rate-msg').textContent = 'Ratings unavailable';
  }
}

async function rate(value) {
  const song = currentSong;
  if (!song) return;
  if (!user) return openAuth('login');
  if (lastRatings && lastRatings.mine === value) return; // already your rating
  $('rate-up').disabled = $('rate-down').disabled = true;
  try {
    const res = await fetch(RATINGS_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...song, value }),
    });
    if (res.status === 401) {
      setUser(null);
      openAuth('login');
    } else if (res.ok) {
      const r = await res.json();
      if (song === currentSong) renderRatings(r);
    } else {
      throw new Error();
    }
  } catch {
    if (song === currentSong) {
      $('rate-up').disabled = $('rate-down').disabled = false;
      $('rate-msg').textContent = 'Could not save your rating.';
    }
  }
}

async function undoRating() {
  const song = currentSong;
  if (!song || !user) return;
  $('rate-undo').disabled = true;
  try {
    const res = await fetch(RATINGS_API, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(song),
    });
    if (res.status === 401) {
      setUser(null);
      openAuth('login');
    } else if (res.ok) {
      const r = await res.json();
      if (song === currentSong) renderRatings(r);
    } else {
      throw new Error();
    }
  } catch {
    $('rate-msg').textContent = 'Could not remove your rating.';
  } finally {
    $('rate-undo').disabled = false;
  }
}
$('rate-undo').onclick = undoRating;

document.querySelectorAll('.rate-btn').forEach((b) => (b.onclick = () => rate(Number(b.dataset.value))));

// --- Accounts ------------------------------------------------------------
const dialog = $('auth-dialog');
let authMode = 'login';

async function api(path, body) {
  const res = await fetch(`/api/${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

function setUser(u) {
  user = u;
  $('whoami').hidden = !u;
  $('whoami').textContent = u ? `Signed in as ${u.username}` : '';
  $('auth-open').hidden = !!u;
  $('logout').hidden = !u;
  if (currentSong) loadRatings(currentSong); // refresh "mine" for the new identity
  else if (lastRatings) renderRatings(lastRatings);
}

function openAuth(mode) {
  authMode = mode;
  const reg = mode === 'register';
  $('auth-h').textContent = reg ? 'Register' : 'Log in';
  $('auth-submit').textContent = reg ? 'Register' : 'Log in';
  $('auth-switch').textContent = reg ? 'Have an account? Log in' : 'Need an account? Register';
  $('auth-pass').autocomplete = reg ? 'new-password' : 'current-password';
  $('auth-error').hidden = true;
  if (!dialog.open) dialog.showModal();
  $('auth-user').focus();
}

$('auth-open').onclick = () => openAuth('login');
$('auth-switch').onclick = () => openAuth(authMode === 'login' ? 'register' : 'login');
$('auth-cancel').onclick = () => dialog.close();
$('logout').onclick = async () => {
  try { await api('logout', {}); } catch {}
  setUser(null);
};

$('auth-form').onsubmit = async (e) => {
  e.preventDefault();
  $('auth-submit').disabled = true;
  try {
    const data = await api(authMode, { username: $('auth-user').value, password: $('auth-pass').value });
    $('auth-pass').value = '';
    dialog.close();
    setUser(data.user);
  } catch (err) {
    $('auth-error').textContent = err.message;
    $('auth-error').hidden = false;
  } finally {
    $('auth-submit').disabled = false;
  }
};

api('me').then((d) => setUser(d.user)).catch(() => setUser(null));
