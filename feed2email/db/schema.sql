CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    recipient TEXT,
    dedup_key TEXT NOT NULL DEFAULT 'id' CHECK(dedup_key IN ('id', 'link', 'title')),
    format TEXT NOT NULL DEFAULT 'text' CHECK(format IN ('text', 'html')),
    item_date INTEGER NOT NULL DEFAULT 0 CHECK(item_date IN (0, 1)),
    paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
) STRICT;

CREATE TABLE IF NOT EXISTS seen_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    dedup_value TEXT NOT NULL,
    url TEXT,
    seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
    UNIQUE(feed_id, dedup_value)
) STRICT;

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
