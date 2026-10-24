-- Applied on every app start; use "create table if not exists".
create table if not exists tracks (
  id       integer primary key,
  title    text not null,
  artist   text not null,
  album    text,
  duration real,                   -- seconds
  filename text not null unique,   -- file inside public/media/
  added_at text not null default (datetime('now'))
);

-- One row per (song, listener); the primary key enforces one rating per listener per song.
create table if not exists ratings (
  song_key   text not null,
  voter      text not null,
  artist     text not null,
  title      text not null,
  value      integer not null check (value in (1, -1)),
  created_at text not null default (datetime('now')),
  primary key (song_key, voter)
);

create table if not exists users (
  id            integer primary key,
  username      text not null unique collate nocase,
  password_hash text not null,
  created_at    text not null default (datetime('now'))
);
